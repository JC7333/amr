"""AMR tool: verify_mandate - Check if an agent has an active valid mandate."""

import json
from datetime import UTC, datetime
from uuid import UUID

import aiosqlite

from amr.config import settings
from amr.db.engine import get_db, init_db
from amr.delegation import is_expired, is_revoked, load_ancestors
from amr.models.organ_decision import recorded_organ_decision


def _answer(authorized: bool, reason: str, row: aiosqlite.Row | None = None) -> str:
    """Build the verify_mandate answer; without a row, no mandate detail is disclosed."""
    if row is None:
        return json.dumps(
            {
                "authorized": authorized,
                "mandate_id": None,
                "reason": reason,
                "scope": "",
                "perimeter": None,
                "parent_mandate_id": None,
                "organ_decision": None,
                "expires_at": None,
            }
        )
    return json.dumps(
        {
            "authorized": authorized,
            "mandate_id": row["id"],
            "reason": reason,
            "scope": row["scope"],
            "perimeter": json.loads(row["perimeter_json"]) if row["perimeter_json"] else None,
            "parent_mandate_id": row["parent_mandate_id"],
            "organ_decision": recorded_organ_decision(row["metadata_json"]),
            "expires_at": row["expires_at"],
        }
    )


async def _check_named_mandate(
    db: aiosqlite.Connection, agent_id: str, mandate_id: str, now: datetime
) -> tuple[aiosqlite.Row | None, str | None]:
    """Read one named mandate of the agent; return (row, refusal reason or None).

    A mandate held by another agent, or unknown, comes back without its row so that
    nothing about it is disclosed.
    """
    cursor = await db.execute(
        """
        SELECT id, agent_id, scope, expires_at, status, parent_mandate_id, perimeter_json,
               metadata_json
        FROM mandates
        WHERE id = ?
        """,
        (mandate_id,),
    )
    row = await cursor.fetchone()
    if row is None or row["agent_id"] != agent_id:
        return None, f"Mandate '{mandate_id}' not found for agent '{agent_id}'"
    if await is_revoked(db, row["id"]):
        return row, "Mandate revoked"
    if row["status"] != "active":
        return row, f"Mandate is {row['status']}"
    try:
        expired = is_expired(row["expires_at"], now)
    except (TypeError, ValueError):
        return row, "Mandate expiry unreadable"
    if expired:
        return row, "Mandate expired"
    return row, None


async def verify_mandate(
    agent_id: str,
    action: str,
    context: str = "",
    mandate_id: str = "",
) -> str:
    """Verify whether an AI agent has a currently active and valid mandate to perform an action.

    Without mandate_id, looks up the most recent active, non-expired, non-revoked
    mandate for the given agent: if one mandate was revoked and another is still in
    force, the answer is authorized, for the other one. Pass mandate_id to check one
    named mandate: the answer is then about that mandate only (revoked, expired or
    held by another agent means authorized=false, even if the agent holds another
    active mandate).
    For a sub-mandate, every mandate above it must also be active, unrevoked
    and unexpired.
    Does NOT check the action against the scope: it returns the free-text scope and,
    when the mandate has one, its structured perimeter. To enforce the perimeter,
    request a token with issue_action_token, which refuses out-of-scope actions.

    Args:
        agent_id: Unique identifier of the agent to check.
                  Example: "agent:korvex-advisor-v1"
        action: Description of the action the agent wants to perform.
                Example: "send investment recommendation" or "access user portfolio"
        context: Optional additional context for logging or audit purposes.
                 Example: "client session cs-2026-0042"
        mandate_id: Optional UUID of the one mandate to check, e.g. the mandate an
                    agent presents to you. Empty (default): any active mandate of
                    the agent, as before.

    Returns:
        JSON string with keys: authorized (bool), mandate_id (str|null),
        reason (str), scope (str), perimeter (dict|null),
        parent_mandate_id (str|null), organ_decision (dict|null: the body,
        title, date, reference and authorized personnel of the decision that
        authorized the agent, when the mandate records one), expires_at (str|null).
        authorized=True means an active mandate exists; the caller should verify
        that the action falls within the returned scope.
    """
    db = None
    try:
        now = datetime.now(UTC)
        named = mandate_id.strip()
        if named:
            try:
                named = str(UUID(named))
            except ValueError:
                return _answer(False, f"Invalid mandate_id format: '{mandate_id}'")

        await init_db(settings.db_path)
        db = await get_db(settings.db_path)

        if named:
            row, refusal_reason = await _check_named_mandate(db, agent_id, named, now)
            if refusal_reason is not None:
                return _answer(False, refusal_reason, row)
        else:
            cursor = await db.execute(
                """
                SELECT id, scope, expires_at, status, parent_mandate_id, perimeter_json,
                       metadata_json
                FROM mandates
                WHERE agent_id = ?
                  AND status = ?
                  AND expires_at > ?
                  AND NOT EXISTS (
                      SELECT 1 FROM mandate_revocations r WHERE r.mandate_id = mandates.id
                  )
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (agent_id, "active", now.isoformat()),
            )
            row = await cursor.fetchone()
            if row is None:
                return _answer(False, f"No active mandate found for agent '{agent_id}'")

        _, refusal = await load_ancestors(db, row["parent_mandate_id"], now)
        if refusal is not None:
            return _answer(False, f"Delegation chain broken: {refusal.reason}", row)

        return _answer(True, "Active mandate found", row)

    except Exception as exc:
        return json.dumps({"error": str(exc)})

    finally:
        if db is not None:
            await db.close()
