"""AMR tool: log_action - Log an agent action under an active mandate."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import aiosqlite

from amr.config import settings
from amr.crypto.chain import compute_hash
from amr.db.engine import (
    get_action_token_link,
    get_db,
    get_issued_token,
    get_last_action_hash,
    init_db,
)
from amr.delegation import is_revoked, is_suspended, load_ancestors
from amr.tools.check_action_token import _decode

# A JWS of an action token is a few hundred characters; anything far larger is refused
# before any decoding.
MAX_TOKEN_LENGTH = 8192


def _token_refusal(reason: str, detail: str | None = None) -> str:
    body: dict[str, Any] = {
        "error": f"Action token refused ({reason})" + (f": {detail}" if detail else ""),
        "reason": reason,
    }
    return json.dumps(body)


async def _check_token(
    db: aiosqlite.Connection, token: str, mandate_id: str, agent_id: str
) -> tuple[dict[str, str] | None, str | None]:
    """Check an action token for logging. Returns (link fields, refusal JSON).

    The token must be one this registry signed and issued (signature, iss, exp, nbf,
    record in issued_tokens), for this very mandate and its agent, and not already used
    to log another action. The mandate and its chain are checked by log_action itself.
    """
    if len(token) > MAX_TOKEN_LENGTH:
        return None, _token_refusal("malformed", "token too long")
    claims, reason, detail = _decode(token, None)
    if claims is None:
        return None, _token_refusal(reason, detail)
    jti = str(claims["jti"])
    record = await get_issued_token(db, jti)
    if record is None:
        return None, _token_refusal("unknown_token")
    if (
        record["mandate_id"] != str(claims["amr_mandate_id"])
        or record["action_hash"] != claims["amr_action_hash"]
        or record["audience"] != claims["aud"]
        or record["agent_id"] != claims["sub"]
    ):
        return None, _token_refusal("token_record_mismatch")
    if record["mandate_id"] != mandate_id:
        return None, _token_refusal(
            "token_mandate_mismatch", "the token was issued under another mandate"
        )
    if record["agent_id"] != agent_id:
        return None, _token_refusal("agent_mismatch")
    if await get_action_token_link(db, jti) is not None:
        return None, _token_refusal(
            "token_already_used", "this token already covers a logged action"
        )
    return {"jti": jti, "action_hash": record["action_hash"]}, None


async def log_action(
    mandate_id: str,
    action: str,
    evidence: str = "",
    result: str = "",
    action_token: str | None = None,
) -> str:
    """Log an action performed by an AI agent under an active mandate for audit and compliance.

    Each action log entry is cryptographically linked to the previous action (SHA-256 chain),
    creating a tamper-evident audit trail. The mandate must be active, not revoked and
    not expired; for a sub-mandate, so must every mandate above it in the delegation
    chain (revoking or letting expire a parent stops the logging of its whole branch).

    Args:
        mandate_id: UUID of the mandate under which the action was performed.
                    Example: "550e8400-e29b-41d4-a716-446655440000"
        action: Description of the action that was performed.
                Example: "Generated investment recommendation for Product X"
        evidence: Optional supporting evidence or reference for the action.
                  Example: "email:msg_abc123" or "document:report_2026_042.pdf"
        result: Optional outcome or result of the action.
                Example: "Delivered" or "Rejected by client" or "Pending review"
        action_token: Optional compact JWS returned by issue_action_token for this
                action. When given, the action is logged only if the token is one this
                registry issued, still within its validity window, for this mandate
                and its agent, and not already used for another logged action; the
                token's jti and action hash are then sealed into the entry. Required
                for every action when the operator sets
                AMR_REQUIRE_ACTION_TOKEN_FOR_LOG=true.

    Returns:
        JSON string with keys: status, action_id, mandate_id, action, chain_hash, and
        token_jti when a token covers the action.
        On error (invalid mandate): {"error": "..."}; when a mandate above a
        sub-mandate breaks the chain, also "reason" (parent_mandate_revoked,
        parent_mandate_expired, parent_mandate_<status>, parent_mandate_not_found or
        delegation_chain_too_deep) and "refused_by" (the mandate that broke it, or null).
        A refused token gives "error" and "reason": action_token_required, malformed,
        wrong_algorithm, key_mismatch, bad_signature, wrong_issuer, token_expired,
        token_not_yet_valid, missing_claim, unknown_token, token_record_mismatch,
        token_mandate_mismatch, agent_mismatch or token_already_used.
    """
    db = None
    try:
        # Validate mandate_id format
        try:
            UUID(mandate_id)
        except ValueError:
            return json.dumps(
                {
                    "error": f"Invalid mandate_id format: '{mandate_id}'",
                    "code": "invalid_input",
                    "field": "mandate_id",
                }
            )

        if action_token is None and settings.require_action_token_for_log:
            return _token_refusal(
                "action_token_required",
                "this registry logs only actions covered by an action token",
            )

        now = datetime.now(UTC)

        await init_db(settings.db_path)
        db = await get_db(settings.db_path)

        # Verify mandate exists, is active, and not expired
        cursor = await db.execute(
            """
            SELECT id, agent_id, status, expires_at, parent_mandate_id
            FROM mandates
            WHERE id = ?
            """,
            (mandate_id,),
        )
        mandate_row = await cursor.fetchone()

        if mandate_row is None:
            return json.dumps(
                {
                    "error": f"Mandate '{mandate_id}' not found",
                    "code": "mandate_not_found",
                    "field": "mandate_id",
                }
            )

        if mandate_row["status"] != "active":
            return json.dumps(
                {
                    "error": (
                        f"Mandate '{mandate_id}' is not active "
                        f"(status: {mandate_row['status']})"
                    ),
                    "code": f"mandate_status_{mandate_row['status']}",
                }
            )

        if await is_revoked(db, mandate_row["id"]):
            return json.dumps(
                {
                    "error": f"Mandate '{mandate_id}' is not active (status: revoked)",
                    "code": "mandate_status_revoked",
                }
            )

        if await is_suspended(db, mandate_row["id"]):
            return json.dumps(
                {
                    "error": f"Mandate '{mandate_id}' is not active (status: suspended)",
                    "code": "mandate_status_suspended",
                }
            )

        expires_at_str = mandate_row["expires_at"]
        # Handle both offset-aware and naive datetimes stored in DB
        if expires_at_str.endswith("+00:00") or expires_at_str.endswith("Z"):
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        else:
            expires_at = datetime.fromisoformat(expires_at_str).replace(tzinfo=UTC)

        if now > expires_at:
            return json.dumps(
                {
                    "error": f"Mandate '{mandate_id}' has expired at {expires_at_str}",
                    "code": "mandate_expired",
                }
            )

        # A sub-mandate is only in force while every mandate above it is.
        _, refusal = await load_ancestors(db, mandate_row["parent_mandate_id"], now)
        if refusal is not None:
            return json.dumps(
                {
                    "error": (
                        f"Mandate '{mandate_id}' is not in force: "
                        f"delegation chain broken ({refusal.reason})"
                    ),
                    "reason": refusal.reason,
                    "refused_by": refusal.refused_by,
                }
            )

        agent_id = mandate_row["agent_id"]
        action_id = str(__import__("uuid").uuid4())

        link: dict[str, str] | None = None
        if action_token is not None:
            link, refusal_json = await _check_token(db, action_token, mandate_id, agent_id)
            if refusal_json is not None:
                return refusal_json

        # Chain to the last action for this mandate (or mandate hash if first action)
        previous_hash = await get_last_action_hash(db, mandate_id)

        hash_data = {
            "id": action_id,
            "mandate_id": mandate_id,
            "agent_id": agent_id,
            "action": action,
            "evidence": evidence,
            "result": result,
            "timestamp": now.isoformat(),
        }
        if link is not None:
            # Only covered actions carry these keys: an action logged without a token
            # hashes exactly as before (same fields as get_proof lists for it).
            hash_data["action_token_jti"] = link["jti"]
            hash_data["action_token_action_hash"] = link["action_hash"]
        chain_hash = compute_hash(hash_data, previous_hash)

        await db.execute(
            """
            INSERT INTO action_logs
              (id, mandate_id, agent_id, action, evidence, result, timestamp, chain_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action_id,
                mandate_id,
                agent_id,
                action,
                evidence,
                result,
                now.isoformat(),
                chain_hash,
            ),
        )
        if link is not None:
            # Same transaction as the action; the UNIQUE jti refuses a second use even
            # when two calls race past the check above.
            try:
                await db.execute(
                    """
                    INSERT INTO action_log_tokens (action_id, jti, mandate_id, action_hash)
                    VALUES (?, ?, ?, ?)
                    """,
                    (action_id, link["jti"], mandate_id, link["action_hash"]),
                )
            except aiosqlite.IntegrityError:
                # Another call used this token first: nothing of this one is committed.
                await db.rollback()
                return _token_refusal(
                    "token_already_used", "this token already covers a logged action"
                )
        await db.commit()

        body: dict[str, Any] = {
            "status": "logged",
            "action_id": action_id,
            "mandate_id": mandate_id,
            "action": action,
            "chain_hash": chain_hash,
        }
        if link is not None:
            body["token_jti"] = link["jti"]
        return json.dumps(body)

    except Exception as exc:
        return json.dumps({"error": str(exc)})

    finally:
        if db is not None:
            await db.close()
