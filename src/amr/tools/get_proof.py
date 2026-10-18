"""AMR tool: get_proof - Generate a cryptographic Proof Pack for a mandate."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from amr.config import settings
from amr.crypto.chain import verify_chain
from amr.crypto.principal import (
    MANDATE_CONTEXT,
    PrincipalSignatureError,
    parse_public_key,
    parse_signature,
    verify,
)
from amr.db.engine import get_db, get_principal_key, init_db


def _aware(moment: str) -> datetime:
    parsed = datetime.fromisoformat(moment)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _principal_signature_valid(mandate: dict[str, Any], signature: dict[str, Any]) -> bool:
    """Re-verify the principal's signature and that it covers this very mandate.

    The signed payload must match the stored mandate: principal, agent, scope, legal
    basis, parent, metadata, signed_at, the duration (created_at + duration_hours ==
    expires_at, to the second) and, for a root mandate, the perimeter. A sub-mandate's
    stored perimeter is the requested one narrowed by its parent, so it is not compared.
    """
    if signature.get("public_key") is None:
        return False
    try:
        public_key_raw = parse_public_key(signature["public_key"])
        signature_raw = parse_signature(signature["signature"])
    except PrincipalSignatureError:
        return False
    payload_text = signature["payload"]
    if not verify(public_key_raw, payload_text.encode("utf-8"), signature_raw):
        return False
    payload = json.loads(payload_text)
    expected = {
        "context": MANDATE_CONTEXT,
        "principal_id": mandate["principal_id"],
        "agent_id": mandate["agent_id"],
        "scope": mandate["scope"],
        "legal_basis": mandate["legal_basis"],
        "parent_mandate_id": mandate["parent_mandate_id"],
        "metadata": mandate["metadata"],
        "signed_at": signature["signed_at"],
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        return False
    if mandate["parent_mandate_id"] is None and payload.get("perimeter") != mandate["perimeter"]:
        return False
    duration = payload.get("duration_hours")
    if isinstance(duration, bool) or not isinstance(duration, int | float):
        return False
    granted = _aware(mandate["expires_at"]) - _aware(mandate["created_at"])
    return abs(granted - timedelta(hours=duration)) <= timedelta(seconds=1)


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
          - mandate: dict with full mandate details, including principal_signature
            ({signature, signed_at, key_id, public_key, payload, algorithm} or null)
          - actions: list of action log entries
          - events: list of mandate events
          - chain_integrity: dict with actions_chain_valid (bool),
            principal_signature_valid (bool, or null for an unsigned mandate),
            total_actions, total_events
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
                   metadata_json, chain_hash, perimeter_json,
                   principal_signature, principal_signed_at, principal_key_id,
                   principal_signed_payload
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
            "perimeter": (
                json.loads(mandate_row["perimeter_json"])
                if mandate_row["perimeter_json"]
                else None
            ),
            "principal_signature": None,
            "chain_hash": mandate_row["chain_hash"],
        }

        # The principal's signature, if any, with the key it was checked against.
        principal_signature_valid = None
        if mandate_row["principal_signature"] is not None:
            key_row = await get_principal_key(db, mandate_row["principal_id"])
            signature = {
                "signature": mandate_row["principal_signature"],
                "signed_at": mandate_row["principal_signed_at"],
                "key_id": mandate_row["principal_key_id"],
                "public_key": key_row["public_key"] if key_row is not None else None,
                "payload": mandate_row["principal_signed_payload"],
                "algorithm": "Ed25519",
            }
            mandate_dict["principal_signature"] = signature
            principal_signature_valid = (
                key_row is not None
                and key_row["key_id"] == signature["key_id"]
                and _principal_signature_valid(mandate_dict, signature)
            )

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
                "principal_signature_valid": principal_signature_valid,
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
