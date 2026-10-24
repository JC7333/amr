"""AMR tool: verify_mandate - Check if an agent has an active valid mandate."""

import json
from datetime import UTC, datetime

from amr.config import settings
from amr.db.engine import get_db, init_db
from amr.delegation import load_ancestors
from amr.models.organ_decision import recorded_organ_decision


async def verify_mandate(
    agent_id: str,
    action: str,
    context: str = "",
) -> str:
    """Verify whether an AI agent has a currently active and valid mandate to perform an action.

    Looks up the most recent active, non-expired, non-revoked mandate for the given
    agent. For a sub-mandate, every mandate above it must also be active, unrevoked
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

        await init_db(settings.db_path)
        db = await get_db(settings.db_path)

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
            return json.dumps(
                {
                    "authorized": False,
                    "mandate_id": None,
                    "reason": f"No active mandate found for agent '{agent_id}'",
                    "scope": "",
                    "perimeter": None,
                    "parent_mandate_id": None,
                    "organ_decision": None,
                    "expires_at": None,
                }
            )

        _, refusal = await load_ancestors(db, row["parent_mandate_id"], now)
        if refusal is not None:
            return json.dumps(
                {
                    "authorized": False,
                    "mandate_id": row["id"],
                    "reason": f"Delegation chain broken: {refusal.reason}",
                    "scope": row["scope"],
                    "perimeter": (
                        json.loads(row["perimeter_json"]) if row["perimeter_json"] else None
                    ),
                    "parent_mandate_id": row["parent_mandate_id"],
                    "organ_decision": recorded_organ_decision(row["metadata_json"]),
                    "expires_at": row["expires_at"],
                }
            )

        return json.dumps(
            {
                "authorized": True,
                "mandate_id": row["id"],
                "reason": "Active mandate found",
                "scope": row["scope"],
                "perimeter": json.loads(row["perimeter_json"]) if row["perimeter_json"] else None,
                "parent_mandate_id": row["parent_mandate_id"],
                "organ_decision": recorded_organ_decision(row["metadata_json"]),
                "expires_at": row["expires_at"],
            }
        )

    except Exception as exc:
        return json.dumps({"error": str(exc)})

    finally:
        if db is not None:
            await db.close()
