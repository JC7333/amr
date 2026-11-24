"""AMR tool: record_action_receipt - the receiver leaves a receipt for an action token.

The registry knows that it authorized an action (issued_tokens) and what the agent says
it did (log_action). Neither says what happened on the receiving side. A receipt is the
receiver's own line: it received this token and executed the action, or refused it and
why, and, if it wants, the SHA-256 of what it received. The proof of a mandate then shows
three separate lines for each action (authorization, agent's declaration, receiver's
receipt) and which one is missing.

A receipt is declared by the receiver; it is not signed. It records what the receiver
says it did, not that the content was right or that the action really took place.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import aiosqlite
from pydantic import ValidationError

from amr.config import settings
from amr.crypto.chain import compute_hash
from amr.db.engine import get_action_token_link, get_db, get_issued_token, init_db
from amr.models.token import RecordReceiptRequest
from amr.tool_errors import validation_field
from amr.tools.check_action_token import _decode

# A receiver may record its receipt after the token expired (it acted inside the
# window, then wrote the receipt), but not indefinitely: past this delay after exp, the
# receipt is refused.
RECEIPT_LATE_WINDOW = timedelta(days=7)

_INSERT_RECEIPT = """
INSERT INTO action_receipts (
    jti, mandate_id, agent_id, action_hash, audience, outcome, refusal_reason,
    received_content_sha256, recorded_at, chain_hash
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_FIELD_OF_REASON = {
    "wrong_audience": "audience",
    "malformed": "token",
    "wrong_algorithm": "token",
    "key_mismatch": "token",
    "bad_signature": "token",
    "wrong_issuer": "token",
    "missing_claim": "token",
    "token_not_yet_valid": "token",
}


def _error(code: str, message: str, field: str | None = None, **extra: Any) -> str:
    body: dict[str, Any] = {"error": message, "code": code, "field": field}
    body.update({key: value for key, value in extra.items() if value is not None})
    return json.dumps(body)


def receipt_hash_data(receipt: dict[str, Any], mandate_chain_hash: str) -> dict[str, Any]:
    """The fields sealed in a receipt's chain_hash, from its stored row."""
    return {
        "jti": receipt["jti"],
        "mandate_id": receipt["mandate_id"],
        "mandate_chain_hash": mandate_chain_hash,
        "agent_id": receipt["agent_id"],
        "action_hash": receipt["action_hash"],
        "audience": receipt["audience"],
        "outcome": receipt["outcome"],
        "refusal_reason": receipt["refusal_reason"],
        "received_content_sha256": receipt["received_content_sha256"],
        "recorded_at": receipt["recorded_at"],
    }


def receipt_hash_valid(
    receipt: dict[str, Any], mandate_chain_hash: str, previous_hash: str
) -> bool:
    """Recompute a receipt's chain_hash from its row and the previous receipt's hash."""
    try:
        expected = compute_hash(receipt_hash_data(receipt, mandate_chain_hash), previous_hash)
    except (TypeError, ValueError, KeyError):
        return False
    return expected == receipt["chain_hash"]


async def get_last_receipt_hash(db: aiosqlite.Connection) -> str:
    """The chain_hash of the last receipt recorded in the registry, or "" if none."""
    cursor = await db.execute(
        "SELECT chain_hash FROM action_receipts ORDER BY rowid DESC LIMIT 1"
    )
    row = await cursor.fetchone()
    return row["chain_hash"] if row is not None else ""


async def mandate_receipts(
    db: aiosqlite.Connection, mandate_id: str
) -> list[tuple[dict[str, Any], str]]:
    """Every receipt recorded under one mandate, oldest first, each with the chain_hash
    of the receipt recorded just before it in the whole registry ("" for the first)."""
    cursor = await db.execute(
        "SELECT rowid AS position, jti, mandate_id, agent_id, action_hash, audience, "
        "outcome, refusal_reason, received_content_sha256, recorded_at, chain_hash "
        "FROM action_receipts WHERE mandate_id = ? ORDER BY rowid ASC",
        (mandate_id,),
    )
    found: list[tuple[dict[str, Any], str]] = []
    for row in await cursor.fetchall():
        previous = await db.execute(
            "SELECT chain_hash FROM action_receipts WHERE rowid < ? "
            "ORDER BY rowid DESC LIMIT 1",
            (row["position"],),
        )
        before = await previous.fetchone()
        receipt = dict(row)
        receipt.pop("position")
        found.append((receipt, before["chain_hash"] if before is not None else ""))
    return found


async def record_action_receipt(
    token: str,
    audience: str,
    outcome: str,
    refusal_reason: str | None = None,
    received_content_sha256: str | None = None,
) -> str:
    """Leave the receiver's receipt for an action token: executed, or refused and why.

    For the system that received an agent's action (a patient record, an ERP, a
    payment service), once it has dealt with it. The registry already knows that it
    authorized the action (the token) and what the agent declared (log_action); the
    receipt adds the receiver's own line, so get_proof shows, for each action, the
    authorization, the agent's declaration and the receiver's receipt, and which one is
    missing.

    The token must be one this registry signed and issued, addressed to you (audience
    equals its aud). One receipt per token: a second one is refused. A token past its
    exp is accepted for 7 days after it (you acted in time and record afterwards). A
    token whose mandate was withdrawn or has expired since is accepted too: a refusal
    because of the withdrawal is exactly what to record, and the proof shows the
    withdrawal next to it. The receipt is chained (SHA-256) and seals the mandate hash
    and the token's action hash.

    What a receipt is not: it is what the receiver declares it did, not proof that the
    content was right or that the action took place. It is not signed: anyone who holds
    the token and can call this tool on the same registry can record it, so expose this
    tool to the receiver only (profile receiver), never to the agent.

    Args:
        token: The compact JWS the agent presented (from issue_action_token).
        audience: Who you are; must equal the token's aud.
        outcome: "executed" (you carried out the action) or "refused" (you did not).
        refusal_reason: Why you refused (1 to 500 characters). Required with
            "refused", not accepted with "executed".
        received_content_sha256: Optional SHA-256 (64 lowercase hex) of what you
            received, e.g. the note written into the record.

    Returns:
        JSON string. Recorded: {status: "recorded", jti, mandate_id, agent_id, outcome,
        refusal_reason (only when refused), received_content_sha256 (when given),
        recorded_at, chain_hash, agent_declaration_action_id (the action log entry the
        agent logged with this token, or null if it has not logged it yet)}.
        Refused: {error, code, field}; code is invalid_input, malformed,
        wrong_algorithm, key_mismatch, bad_signature, wrong_issuer, wrong_audience,
        token_not_yet_valid, missing_claim, receipt_too_late, registry_unavailable,
        unknown_token, token_record_mismatch, receipt_already_recorded or
        internal_error.
    """
    db = None
    try:
        try:
            req = RecordReceiptRequest(
                token=token,
                audience=audience,
                outcome=outcome,  # type: ignore[arg-type]
                refusal_reason=refusal_reason,
                received_content_sha256=received_content_sha256,
            )
        except ValidationError as exc:
            first = exc.errors()[0]
            return _error(
                "invalid_input", f"Invalid input: {first['msg']}", validation_field(exc)
            )
        now = datetime.now(UTC)

        claims, reason, detail = _decode(req.token, req.audience, verify_exp=False)
        if claims is None:
            message = f"Action token refused ({reason})" + (f": {detail}" if detail else "")
            return _error(reason, message, _FIELD_OF_REASON.get(reason))
        jti = str(claims["jti"])
        mandate_id = str(claims["amr_mandate_id"])
        expired_at = datetime.fromtimestamp(int(claims["exp"]), UTC)
        if now > expired_at + RECEIPT_LATE_WINDOW:
            return _error(
                "receipt_too_late",
                "the token expired more than 7 days ago: no receipt is recorded for it",
                "token",
                jti=jti,
                mandate_id=mandate_id,
            )

        # Never create a registry here: a receipt for a registry that does not exist
        # cannot name a token it issued.
        if not settings.db_path.resolve().is_file():
            return _error(
                "registry_unavailable",
                "no registry database at the configured path",
                jti=jti,
                mandate_id=mandate_id,
            )
        await init_db(settings.db_path)
        db = await get_db(settings.db_path)

        # One write transaction from these reads to the insert, so two concurrent
        # receipts cannot chain to the same previous receipt hash.
        await db.execute("BEGIN IMMEDIATE")
        record = await get_issued_token(db, jti)
        if record is None:
            return _error(
                "unknown_token", "this registry did not issue this token", "token", jti=jti
            )
        if (
            record["mandate_id"] != mandate_id
            or record["action_hash"] != claims["amr_action_hash"]
            or record["audience"] != claims["aud"]
            or record["agent_id"] != claims["sub"]
        ):
            return _error(
                "token_record_mismatch",
                "the token does not match the registry's record of it",
                "token",
                jti=jti,
            )
        cursor = await db.execute("SELECT 1 FROM action_receipts WHERE jti = ?", (jti,))
        if await cursor.fetchone() is not None:
            return _error(
                "receipt_already_recorded",
                "a receipt is already recorded for this token",
                "token",
                jti=jti,
            )
        cursor = await db.execute("SELECT chain_hash FROM mandates WHERE id = ?", (mandate_id,))
        mandate = await cursor.fetchone()
        if mandate is None:
            return _error("mandate_not_found", f"Mandate '{mandate_id}' not found", jti=jti)

        receipt = {
            "jti": jti,
            "mandate_id": mandate_id,
            "agent_id": record["agent_id"],
            "action_hash": record["action_hash"],
            "audience": record["audience"],
            "outcome": req.outcome,
            "refusal_reason": req.refusal_reason or "",
            "received_content_sha256": req.received_content_sha256,
            "recorded_at": now.isoformat(),
        }
        chain_hash = compute_hash(
            receipt_hash_data(receipt, mandate["chain_hash"]), await get_last_receipt_hash(db)
        )
        try:
            await db.execute(
                _INSERT_RECEIPT,
                (
                    receipt["jti"],
                    receipt["mandate_id"],
                    receipt["agent_id"],
                    receipt["action_hash"],
                    receipt["audience"],
                    receipt["outcome"],
                    receipt["refusal_reason"],
                    receipt["received_content_sha256"],
                    receipt["recorded_at"],
                    chain_hash,
                ),
            )
        except aiosqlite.IntegrityError:
            await db.rollback()
            return _error(
                "receipt_already_recorded",
                "a receipt is already recorded for this token",
                "token",
                jti=jti,
            )
        await db.commit()

        link = await get_action_token_link(db, jti)
        body: dict[str, Any] = {
            "status": "recorded",
            "jti": jti,
            "mandate_id": mandate_id,
            "agent_id": receipt["agent_id"],
            "outcome": receipt["outcome"],
        }
        if req.outcome == "refused":
            body["refusal_reason"] = receipt["refusal_reason"]
        if receipt["received_content_sha256"] is not None:
            body["received_content_sha256"] = receipt["received_content_sha256"]
        body.update(
            {
                "recorded_at": receipt["recorded_at"],
                "chain_hash": chain_hash,
                "agent_declaration_action_id": link["action_id"] if link else None,
            }
        )
        return json.dumps(body)

    except Exception as exc:
        return _error("internal_error", str(exc))

    finally:
        if db is not None:
            await db.close()
