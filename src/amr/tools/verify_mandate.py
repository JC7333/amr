"""AMR tool: verify_mandate - Check if an agent has an active valid mandate."""

import json
from datetime import UTC, datetime

from amr.config import settings
from amr.db.engine import get_db, init_db


async def verify_mandate(
    agent_id: str,
    action: str,
    context: str = "",
) -> str:
    """Verify whether an AI agent has a currently active and valid mandate to perform an action.

    Looks up the most recent active, non-expired mandate for the given agent.
    Does NOT check scope semantically - returns the scope for the caller to evaluate.

    Args:
        agent_id: Unique identifier of the agent to check.
                  Example: "agent:korvex-advisor-v1"
        action: Description of the action the agent wants to perform.
                Example: "send investment recommendation" or "access user portfolio"
        context: Optional additional context for logging or audit purposes.
                 Example: "client session cs-2026-0042"

    Returns:
        JSON string with keys: authorized (bool), mandate_id (str|null),
        reason (str), scope (str), expires_at (str|null).
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
            SELECT id, scope, expires_at, status
            FROM mandates
            WHERE agent_id = ?
              AND status = ?
              AND expires_at > ?
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
                    "expires_at": None,
                }
            )

        return json.dumps(
            {
                "authorized": True,
                "mandate_id": row["id"],
                "reason": "Active mandate found",
                "scope": row["scope"],
                "expires_at": row["expires_at"],
            }
        )

    except Exception as exc:
        return json.dumps({"error": str(exc)})

    finally:
        if db is not None:
            await db.close()
