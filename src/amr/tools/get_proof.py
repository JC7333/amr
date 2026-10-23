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
    key_id,
    key_registration_payload,
    parse_public_key,
    parse_signature,
    verify,
)
from amr.db.engine import get_db, get_principal_key, get_revocation, init_db
from amr.models.perimeter import Perimeter
from amr.tools.revoke_mandate import revocation_signature_valid


def _aware(moment: str) -> datetime:
    parsed = datetime.fromisoformat(moment)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _key_row_valid(key_row: Any) -> bool:
    """The registered key still carries its own proof of possession and key id."""
    try:
        public_key_raw = parse_public_key(key_row["public_key"])
        proof_raw = parse_signature(key_row["proof_signature"])
    except PrincipalSignatureError:
        return False
    payload = key_registration_payload(key_row["principal_id"], key_row["public_key"])
    return key_row["key_id"] == key_id(public_key_raw) and verify(
        public_key_raw, payload, proof_raw
    )


def _principal_signature_valid(
    mandate: dict[str, Any], signature: dict[str, Any], parent_perimeter_json: str | None
) -> bool:
    """Re-verify the principal's signature and that it covers this very mandate.

    The signed payload must match the stored mandate: principal, agent, scope, legal
    basis, parent, metadata, signed_at, the duration (created_at + duration_hours ==
    expires_at, to the second) and the perimeter (for a sub-mandate, the signed
    perimeter narrowed by the parent's). Any damaged field reads as invalid.
    """
    try:
        return _signature_matches(mandate, signature, parent_perimeter_json)
    except (ValueError, TypeError, KeyError, AttributeError, PrincipalSignatureError):
        return False


def _signature_matches(
    mandate: dict[str, Any], signature: dict[str, Any], parent_perimeter_json: str | None
) -> bool:
    public_key_raw = parse_public_key(signature["public_key"])
    signature_raw = parse_signature(signature["signature"])
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
    if mandate["parent_mandate_id"] is None:
        if payload.get("perimeter") != mandate["perimeter"]:
            return False
    else:
        if payload.get("perimeter") is None or parent_perimeter_json is None:
            return False
        effective = Perimeter.model_validate(payload["perimeter"]).narrowed_by(
            Perimeter.from_json(parent_perimeter_json)
        )
        if effective.canonical() != mandate["perimeter"]:
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
            ({signature, signed_at, key_id, public_key, key_proof_signature, payload,
            algorithm} or null), status ("revoked" once revoke_mandate ran, whatever
            the stored status) and revocation ({revoked_at, reason,
            principal_signature, chain_hash} or null)
          - actions: list of action log entries
          - events: list of mandate events
          - chain_integrity: dict with actions_chain_valid (bool),
            principal_signature_valid (bool; null for an unsigned mandate whose
            principal had no key when it was created), revocation_signature_valid
            (bool; null when the mandate is not revoked or was revoked without a
            signature by a principal that had no key),
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
        key_row = await get_principal_key(db, mandate_row["principal_id"])
        if mandate_row["principal_signature"] is not None:
            signature = {
                "signature": mandate_row["principal_signature"],
                "signed_at": mandate_row["principal_signed_at"],
                "key_id": mandate_row["principal_key_id"],
                "public_key": key_row["public_key"] if key_row is not None else None,
                "key_proof_signature": (
                    key_row["proof_signature"] if key_row is not None else None
                ),
                "payload": mandate_row["principal_signed_payload"],
                "algorithm": "Ed25519",
            }
            mandate_dict["principal_signature"] = signature
            parent_perimeter_json = None
            if mandate_row["parent_mandate_id"] is not None:
                parent_cursor = await db.execute(
                    "SELECT perimeter_json FROM mandates WHERE id = ?",
                    (mandate_row["parent_mandate_id"],),
                )
                parent_row = await parent_cursor.fetchone()
                if parent_row is not None:
                    parent_perimeter_json = parent_row["perimeter_json"]
            principal_signature_valid = (
                key_row is not None
                and key_row["key_id"] == signature["key_id"]
                and _key_row_valid(key_row)
                and _principal_signature_valid(mandate_dict, signature, parent_perimeter_json)
            )
        elif key_row is not None and _aware(key_row["registered_at"]) <= _aware(
            mandate_row["created_at"]
        ):
            # The principal had a key when this mandate was created, so it was signed:
            # a missing signature means it was stripped.
            principal_signature_valid = False

        # A revocation (revoke_mandate) overrides the stored status.
        mandate_dict["revocation"] = None
        revocation_valid = None
        revocation_row = await get_revocation(db, mandate_row["id"])
        if revocation_row is not None:
            mandate_dict["status"] = "revoked"
            revocation = dict(revocation_row)
            mandate_dict["revocation"] = {
                "revoked_at": revocation["revoked_at"],
                "reason": revocation["reason"],
                "principal_signature": (
                    {
                        "signature": revocation["principal_signature"],
                        "signed_at": revocation["principal_signed_at"],
                        "key_id": revocation["principal_key_id"],
                        "payload": revocation["principal_signed_payload"],
                        "algorithm": "Ed25519",
                    }
                    if revocation["principal_signature"] is not None
                    else None
                ),
                "chain_hash": revocation["chain_hash"],
            }
            if revocation["principal_signature"] is not None:
                revocation_valid = (
                    key_row is not None
                    and key_row["key_id"] == revocation["principal_key_id"]
                    and revocation_signature_valid(revocation, key_row["public_key"])
                )
            elif key_row is not None and _aware(key_row["registered_at"]) <= _aware(
                revocation["revoked_at"]
            ):
                # The principal had a key when it revoked, so the revocation was signed.
                revocation_valid = False

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
                "revocation_signature_valid": revocation_valid,
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
