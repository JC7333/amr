"""AMR tool: get_proof - Generate a cryptographic Proof Pack for a mandate."""

import json
from datetime import UTC, datetime
from uuid import UUID

from amr.config import settings
from amr.crypto.chain import verify_chain
from amr.db.engine import get_db, init_db


async def get_proof(
    mandate_id: str,
    format: str = "json",  # noqa: A002
) -> str:
    """Generate a complete Proof Pack for a mandate, including all actions and chain integrity.

    The Proof Pack documents the full mandate chain for regulatory compliance (EU AI Act Art.26,
    eIDAS 2.0). It includes the mandate details, all logged actions, mandate events, and
    cryptographic chain integrity verification.

    Args:
        mandate_id: UUID of the mandate to generate a proof pack for.
                    Example: "550e8400-e29b-41d4-a716-446655440000"
        format: Output format. Currently only "json" is supported.
                Example: "json"

    Returns:
        JSON string (Proof Pack) with keys:
          - proof_pack_version: str
          - generated_at: ISO datetime string
          - mandate: dict with full mandate details
          - actions: list of action log entries
          - events: list of mandate events
          - chain_integrity: dict with actions_chain_valid (bool), total_actions, total_events
          - compliance_notes: dict with ai_act_art26 and retention notes
        On error: {"error": "..."}.
    """
    db = None
    try:
        # Validate mandate_id format
        try:
            UUID(mandate_id)
        except ValueError:
            return json.dumps({"error": f"Invalid mandate_id format: '{mandate_id}'"})

        await init_db(settings.db_path)
        db = await get_db(settings.db_path)

        # Fetch the mandate
        cursor = await db.execute(
            """
            SELECT id, principal_id, agent_id, scope, legal_basis_json,
                   status, created_at, expires_at, parent_mandate_id,
                   metadata_json, chain_hash
            FROM mandates
            WHERE id = ?
            """,
            (mandate_id,),
        )
        mandate_row = await cursor.fetchone()

        if mandate_row is None:
            return json.dumps({"error": f"Mandate '{mandate_id}' not found"})

        mandate_dict = {
            "id": mandate_row["id"],
            "principal_id": mandate_row["principal_id"],
            "agent_id": mandate_row["agent_id"],
            "scope": mandate_row["scope"],
            "legal_basis": json.loads(mandate_row["legal_basis_json"]),
            "status": mandate_row["status"],
            "created_at": mandate_row["created_at"],
            "expires_at": mandate_row["expires_at"],
            "parent_mandate_id": mandate_row["parent_mandate_id"],
            "metadata": json.loads(mandate_row["metadata_json"]),
            "chain_hash": mandate_row["chain_hash"],
        }

        # Fetch all action logs for this mandate
        actions_cursor = await db.execute(
            """
            SELECT id, mandate_id, agent_id, action, evidence, result, timestamp, chain_hash
            FROM action_logs
            WHERE mandate_id = ?
            ORDER BY timestamp ASC
            """,
            (mandate_id,),
        )
        action_rows = await actions_cursor.fetchall()
        actions = [dict(row) for row in action_rows]

        # Fetch all mandate events
        events_cursor = await db.execute(
            """
            SELECT id, mandate_id, event_type, timestamp, reason
            FROM mandate_events
            WHERE mandate_id = ?
            ORDER BY timestamp ASC
            """,
            (mandate_id,),
        )
        event_rows = await events_cursor.fetchall()
        events = [dict(row) for row in event_rows]

        # Verify the action chain integrity
        # Action chains are anchored to the mandate's chain_hash (not "")
        actions_chain_valid = verify_chain(
            actions,
            hash_field="chain_hash",
            initial_hash=mandate_dict["chain_hash"],
        )

        proof_pack = {
            "proof_pack_version": "0.1.0",
            "generated_at": datetime.now(UTC).isoformat(),
            "mandate": mandate_dict,
            "actions": actions,
            "events": events,
            "chain_integrity": {
                "actions_chain_valid": actions_chain_valid,
                "total_actions": len(actions),
                "total_events": len(events),
            },
            "compliance_notes": {
                "ai_act_art26": (
                    "This Proof Pack documents the mandate chain for AI Act Art.26 compliance. "
                    "It records the principal's authorization, agent scope, legal basis, "
                    "and a cryptographically chained action log."
                ),
                "retention": (
                    "Logs must be retained for minimum 6 months per AI Act Art.26(6). "
                    "This Proof Pack should be archived securely."
                ),
            },
        }

        return json.dumps(proof_pack, default=str)

    except Exception as exc:
        return json.dumps({"error": str(exc)})

    finally:
        if db is not None:
            await db.close()
