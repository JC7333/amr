"""AMR tool: log_action - Log an agent action under an active mandate."""

import json
from datetime import UTC, datetime
from uuid import UUID

from amr.config import settings
from amr.crypto.chain import compute_hash
from amr.db.engine import get_db, get_last_action_hash, init_db


async def log_action(
    mandate_id: str,
    action: str,
    evidence: str = "",
    result: str = "",
) -> str:
    """Log an action performed by an AI agent under an active mandate for audit and compliance.

    Each action log entry is cryptographically linked to the previous action (SHA-256 chain),
    creating a tamper-evident audit trail. The mandate must be active and not expired.

    Args:
        mandate_id: UUID of the mandate under which the action was performed.
                    Example: "550e8400-e29b-41d4-a716-446655440000"
        action: Description of the action that was performed.
                Example: "Generated investment recommendation for Product X"
        evidence: Optional supporting evidence or reference for the action.
                  Example: "email:msg_abc123" or "document:report_2026_042.pdf"
        result: Optional outcome or result of the action.
                Example: "Delivered" or "Rejected by client" or "Pending review"

    Returns:
        JSON string with keys: status, action_id, mandate_id, action, chain_hash.
        On error (invalid mandate): {"error": "..."}.
    """
    db = None
    try:
        # Validate mandate_id format
        try:
            UUID(mandate_id)
        except ValueError:
            return json.dumps({"error": f"Invalid mandate_id format: '{mandate_id}'"})

        now = datetime.now(UTC)

        await init_db(settings.db_path)
        db = await get_db(settings.db_path)

        # Verify mandate exists, is active, and not expired
        cursor = await db.execute(
            """
            SELECT id, agent_id, status, expires_at
            FROM mandates
            WHERE id = ?
            """,
            (mandate_id,),
        )
        mandate_row = await cursor.fetchone()

        if mandate_row is None:
            return json.dumps({"error": f"Mandate '{mandate_id}' not found"})

        if mandate_row["status"] != "active":
            return json.dumps(
                {
                    "error": (
                        f"Mandate '{mandate_id}' is not active "
                        f"(status: {mandate_row['status']})"
                    )
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
                {"error": f"Mandate '{mandate_id}' has expired at {expires_at_str}"}
            )

        agent_id = mandate_row["agent_id"]
        action_id = str(__import__("uuid").uuid4())

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
        await db.commit()

        return json.dumps(
            {
                "status": "logged",
                "action_id": action_id,
                "mandate_id": mandate_id,
                "action": action,
                "chain_hash": chain_hash,
            }
        )

    except Exception as exc:
        return json.dumps({"error": str(exc)})

    finally:
        if db is not None:
            await db.close()
