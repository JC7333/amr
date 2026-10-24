"""AMR tool: export_insurer_dossier - Signed dossier of a mandate over a period."""

import json
from datetime import UTC, datetime
from typing import Any

import aiosqlite
from pydantic import ValidationError

from amr.config import settings
from amr.crypto.signing import get_key_id, load_signing_key
from amr.db.engine import get_db, init_db
from amr.delegation import MAX_DELEGATION_DEPTH, is_expired, load_ancestors
from amr.models.dossier import InsurerDossierRequest
from amr.proof.insurer_dossier import (
    DOSSIER_VERSION,
    dossier_digest,
    render_html,
    sign_dossier,
)
from amr.tools.get_proof import get_proof

# Bounds the export of a very wide delegation tree; the dossier says when it is cut.
MAX_SUB_MANDATES = 500

LIMITS = (
    "Facts recorded by this registry, signed with the registry key: the signature "
    "proves what the registry stated at generation time, not that its database "
    "was never altered before.",
    "Refused token requests are not recorded by this registry version: the dossier "
    "lists the tokens issued, not the actions that were blocked.",
    "Actions are logged by the agent's operator: an action that was never logged does not appear.",
    "The principal is identified by the key it registered; the registry does not "
    "check who registered that key.",
    "The legal basis is the one declared when the mandate was created; the registry "
    "does not assess it.",
    "The dossier is read in several steps, not in one database transaction: a "
    "change recorded while it is generated may appear only in part.",
    "If the period omits sub-mandates (sub_mandates_truncated), their events and "
    "tokens are omitted too.",
    "Obtain the registry public key out of band to verify the signature.",
)


def _aware(moment: str) -> datetime:
    parsed = datetime.fromisoformat(moment)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _in_period(moment: str, start: datetime, end: datetime) -> bool:
    return start <= _aware(moment) <= end


def _own_refusal(status: str, expires_at: str, now: datetime) -> str | None:
    if status != "active":
        return f"mandate_{status}"
    if is_expired(expires_at, now):
        return "mandate_expired"
    return None


async def _proof(mandate_id: str) -> dict[str, Any]:
    proof = json.loads(await get_proof(mandate_id))
    if "error" in proof:
        raise LookupError(proof["error"])
    return proof


def _integrity(proof: dict[str, Any]) -> dict[str, Any]:
    chain = proof["chain_integrity"]
    actions = proof["actions"]
    signature = proof["mandate"]["principal_signature"]
    return {
        "actions_chain_valid": chain["actions_chain_valid"],
        "principal_signature_valid": chain["principal_signature_valid"],
        "revocation_signature_valid": chain.get("revocation_signature_valid"),
        "principal_key_id": signature["key_id"] if signature else None,
        "chain_head": actions[-1]["chain_hash"] if actions else proof["mandate"]["chain_hash"],
        "total_actions": chain["total_actions"],
    }


async def _sub_mandates(
    db: aiosqlite.Connection,
    root_id: str,
    root_in_force: bool,
    start: datetime,
    end: datetime,
    now: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Walk the delegation tree below the root, breadth first.

    Returns the sub-mandates, their events in the period, and whether the list
    was truncated (MAX_SUB_MANDATES or MAX_DELEGATION_DEPTH reached).
    """
    subs: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    truncated = False
    frontier: list[tuple[str, bool]] = [(root_id, root_in_force)]
    depth = 0
    while frontier:
        depth += 1
        next_frontier: list[tuple[str, bool]] = []
        for parent_id, parent_in_force in frontier:
            cursor = await db.execute(
                "SELECT id FROM mandates WHERE parent_mandate_id = ? ORDER BY created_at ASC",
                (parent_id,),
            )
            children = [row["id"] for row in await cursor.fetchall()]
            if children and depth > MAX_DELEGATION_DEPTH:
                truncated = True
                continue
            for child_id in children:
                if len(subs) >= MAX_SUB_MANDATES:
                    truncated = True
                    break
                proof = await _proof(child_id)
                mandate = proof["mandate"]
                reason = _own_refusal(mandate["status"], mandate["expires_at"], now)
                if reason is None and not parent_in_force:
                    reason = "parent_mandate_not_in_force"
                in_force = reason is None
                subs.append(
                    {
                        "id": mandate["id"],
                        "parent_mandate_id": mandate["parent_mandate_id"],
                        "depth": depth,
                        "principal_id": mandate["principal_id"],
                        "agent_id": mandate["agent_id"],
                        "scope": mandate["scope"],
                        "created_at": mandate["created_at"],
                        "expires_at": mandate["expires_at"],
                        "perimeter": mandate["perimeter"],
                        "status": {
                            "stored_status": mandate.get("stored_status", mandate["status"]),
                            "in_force": in_force,
                            "not_in_force_reason": reason,
                        },
                        "integrity": _integrity(proof),
                        "actions_in_period": sum(
                            1 for a in proof["actions"] if _in_period(a["timestamp"], start, end)
                        ),
                    }
                )
                events.extend(
                    ev for ev in proof["events"] if _in_period(ev["timestamp"], start, end)
                )
                next_frontier.append((child_id, in_force))
        frontier = next_frontier
    return subs, events, truncated


async def export_insurer_dossier(
    mandate_id: str,
    period_start: str | None = None,
    period_end: str | None = None,
    format: str = "json",  # noqa: A002
) -> str:
    """Export a signed insurer dossier for a mandate over a period.

    The dossier puts in one signed document what an insurer or an auditor asks
    about an AI agent: who granted the mandate, its perimeter (allowed and forbidden
    action types, right to delegate, amount limit), whether it is in force or cut
    (status, expiry, broken delegation chain), its sub-mandates, the status events,
    actions and action tokens of the period, and the integrity checks (action log
    chain, principal signature). Facts from the registry only, plus a fixed list of
    the dossier's limits. Read-only: nothing is written to the registry.

    The dossier is signed with the registry's Ed25519 key as a JWS (EdDSA) whose
    payload is the canonical JSON of the dossier. Verify it offline with
    amr.proof.insurer_dossier.verify_dossier and the registry public key obtained
    out of band.

    Args:
        mandate_id: UUID of the mandate to export.
                    Example: "550e8400-e29b-41d4-a716-446655440000"
        period_start: Optional ISO 8601 start of the period (naive = UTC).
                      Defaults to the mandate's creation. Example: "2026-10-01T00:00:00Z"
        period_end: Optional ISO 8601 end of the period (naive = UTC).
                    Defaults to now. Example: "2026-10-31T23:59:59Z"
        format: "json" (default) or "html" to also get a printable page.

    Returns:
        JSON string with keys:
          - dossier: dict (dossier_version, generated_at, period, mandate, status,
            integrity, sub_mandates, sub_mandates_truncated, events, actions,
            tokens, limits)
          - dossier_sha256: hex SHA-256 of the canonical dossier
          - signature: {jws, algorithm "EdDSA", key_id, public_key_pem}
          - html: printable page (only when format is "html")
        On error: {"error": "..."}.
    """
    db = None
    try:
        try:
            req = InsurerDossierRequest(
                mandate_id=mandate_id,
                period_start=period_start,
                period_end=period_end,
                format=format,
            )
        except ValidationError as exc:
            return json.dumps({"error": f"Invalid input: {exc.errors()[0]['msg']}"})

        try:
            root = await _proof(str(req.mandate_id))
        except LookupError as exc:
            return json.dumps({"error": str(exc)})

        now = datetime.now(UTC)
        mandate = root["mandate"]
        start = req.period_start or _aware(mandate["created_at"])
        end = req.period_end or now
        if start > end:
            return json.dumps({"error": "Invalid input: period_start is after period_end"})

        await init_db(settings.db_path)
        db = await get_db(settings.db_path)

        reason = _own_refusal(mandate["status"], mandate["expires_at"], now)
        if reason is None:
            _, refusal = await load_ancestors(db, mandate["parent_mandate_id"], now)
            if refusal is not None:
                reason = refusal.reason
        in_force = reason is None

        subs, sub_events, truncated = await _sub_mandates(
            db, mandate["id"], in_force, start, end, now
        )
        mandate_ids = [mandate["id"]] + [s["id"] for s in subs]

        tokens: list[dict[str, Any]] = []
        for one_id in mandate_ids:
            cursor = await db.execute(
                """
                SELECT jti, mandate_id, agent_id, action_hash, audience,
                       issued_at, expires_at, key_id
                FROM issued_tokens
                WHERE mandate_id = ?
                ORDER BY issued_at ASC
                """,
                (one_id,),
            )
            tokens.extend(
                dict(row)
                for row in await cursor.fetchall()
                if _in_period(row["issued_at"], start, end)
            )

        events = [ev for ev in root["events"] if _in_period(ev["timestamp"], start, end)]
        events.extend(sub_events)
        events.sort(key=lambda ev: _aware(ev["timestamp"]))

        dossier = {
            "dossier_version": DOSSIER_VERSION,
            "generated_at": now.isoformat(),
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "mandate": mandate,
            "status": {
                "stored_status": mandate.get("stored_status", mandate["status"]),
                "in_force": in_force,
                "not_in_force_reason": reason,
            },
            "integrity": _integrity(root),
            "sub_mandates": subs,
            "sub_mandates_truncated": truncated,
            "events": events,
            "actions": [a for a in root["actions"] if _in_period(a["timestamp"], start, end)],
            "tokens": tokens,
            "limits": list(LIMITS),
        }

        if not settings.signing_key_path.exists():
            # Never mint a key here: a dossier signed by a key no verifier holds is useless.
            return json.dumps(
                {"error": "No registry signing key: create and publish one before exporting"}
            )
        key_id = get_key_id()
        digest = dossier_digest(dossier)
        result: dict[str, Any] = {
            "dossier": dossier,
            "dossier_sha256": digest,
            "signature": {
                "jws": sign_dossier(dossier, load_signing_key(), key_id),
                "algorithm": "EdDSA",
                "key_id": key_id,
                "public_key_pem": settings.public_key_path.read_text(encoding="utf-8"),
            },
        }
        if req.format == "html":
            result["html"] = render_html(dossier, digest, key_id)
        return json.dumps(result)

    except Exception as exc:
        return json.dumps({"error": str(exc)})

    finally:
        if db is not None:
            await db.close()
