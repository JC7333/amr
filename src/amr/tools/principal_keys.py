"""AMR tools: register_principal_key and prepare_mandate_signature.

A principal registers its Ed25519 public key once; from then on every mandate it
grants must carry its signature (see create_mandate).
"""

import json
from datetime import UTC, datetime

import aiosqlite
from pydantic import BaseModel, Field, ValidationError

from amr.config import settings
from amr.crypto.chain import compute_hash
from amr.crypto.principal import (
    KEY_REGISTRATION_CONTEXT,
    PrincipalSignatureError,
    b64url_encode,
    key_id,
    key_registration_payload,
    parse_public_key,
    parse_signature,
    verify,
)
from amr.db.engine import get_db, get_last_principal_key_hash, get_principal_key, init_db
from amr.models.mandate import LegalBasis, MandateCreate
from amr.models.perimeter import PerimeterError
from amr.tools.create_mandate import _build_perimeter, signed_mandate_payload


def _error(code: str, message: str) -> str:
    return json.dumps({"error": f"{code}: {message}", "code": code})


class _PrincipalId(BaseModel):
    model_config = {"extra": "forbid"}

    principal_id: str = Field(..., min_length=1, max_length=200)


async def register_principal_key(
    principal_id: str,
    public_key: str,
    proof_signature: str,
) -> str:
    """Register the Ed25519 public key of a principal, once.

    After registration, create_mandate refuses any mandate from this principal that
    is not signed with the matching private key. The key cannot be replaced or
    removed in this version (first registration wins), so register it before
    anyone else can, ideally when the principal is onboarded.

    Proof of possession: proof_signature is the principal's signature of the canonical
    JSON {"context": "amr.principal_key.v1", "principal_id": ..., "public_key": ...}
    (sorted keys, no spaces, UTF-8; public_key base64url without padding).

    Args:
        principal_id: The principal the key belongs to. Example: "user:audric"
        public_key: Raw 32-byte Ed25519 public key, base64url.
                    Example: "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo"
        proof_signature: Base64url Ed25519 signature of the registration payload.

    Returns:
        JSON string with keys: status ("registered"), principal_id, key_id,
        registered_at, chain_hash.
        On error: {"error": "...", "code": "..."} with code public_key_invalid,
        principal_signature_invalid, principal_key_proof_invalid or
        principal_key_already_registered.
    """
    db = None
    try:
        try:
            _PrincipalId(principal_id=principal_id)
        except ValidationError as exc:
            return _error("principal_id_invalid", str(exc))
        public_key_raw = parse_public_key(public_key)
        signature_raw = parse_signature(proof_signature)
        normalized_key = b64url_encode(public_key_raw)
        payload = key_registration_payload(principal_id, normalized_key)
        if not verify(public_key_raw, payload, signature_raw):
            raise PrincipalSignatureError(
                "principal_key_proof_invalid",
                "proof_signature does not sign the registration payload with this key",
            )

        await init_db(settings.db_path)
        db = await get_db(settings.db_path)
        if await get_principal_key(db, principal_id) is not None:
            raise PrincipalSignatureError(
                "principal_key_already_registered",
                "this principal already has a key; it cannot be replaced",
            )

        registered_at = datetime.now(UTC).isoformat()
        record = {
            "context": KEY_REGISTRATION_CONTEXT,
            "principal_id": principal_id,
            "public_key": normalized_key,
            "key_id": key_id(public_key_raw),
            "proof_signature": b64url_encode(signature_raw),
            "registered_at": registered_at,
        }
        chain_hash = compute_hash(record, await get_last_principal_key_hash(db))
        await db.execute(
            """
            INSERT INTO principal_keys
              (principal_id, public_key, key_id, proof_signature, registered_at, chain_hash)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                principal_id,
                normalized_key,
                record["key_id"],
                record["proof_signature"],
                registered_at,
                chain_hash,
            ),
        )
        await db.commit()
        return json.dumps(
            {
                "status": "registered",
                "principal_id": principal_id,
                "key_id": record["key_id"],
                "registered_at": registered_at,
                "chain_hash": chain_hash,
            }
        )

    except PrincipalSignatureError as exc:
        return _error(exc.code, exc.message)

    except aiosqlite.IntegrityError:
        return _error(
            "principal_key_already_registered",
            "this principal already has a key; it cannot be replaced",
        )

    except Exception as exc:
        return json.dumps({"error": str(exc)})

    finally:
        if db is not None:
            await db.close()


async def prepare_mandate_signature(
    principal_id: str,
    agent_id: str,
    scope: str,
    legal_basis_regulation: str,
    legal_basis_article: str,
    duration_hours: float,
    legal_basis_jurisdiction: str = "EU",
    parent_mandate_id: str | None = None,
    metadata: dict[str, str] | None = None,
    allowed_actions: list[str] | None = None,
    forbidden_actions: list[str] | None = None,
    delegation_allowed: bool = False,
    max_amount: str | None = None,
    currency: str = "EUR",
    amount_actions: list[str] | None = None,
    signed_at: str | None = None,
) -> str:
    """Return the exact bytes a principal must sign to grant this mandate.

    Takes the same arguments as create_mandate. Nothing is written. The principal
    signs payload (UTF-8 bytes; payload_b64url is the same bytes) with its Ed25519
    key, then calls create_mandate with the same arguments plus principal_signature
    and this signed_at. Any difference in the arguments makes the signature invalid.

    Args:
        signed_at: ISO 8601 timestamp with timezone to place in the payload.
                   Default: now (UTC). Example: "2026-10-18T20:30:00+00:00"
        (all other arguments: see create_mandate)

    Returns:
        JSON string with keys: payload (str), payload_b64url, signed_at.
        On error: {"error": "...", "code": "..."}.
    """
    try:
        legal_basis = LegalBasis(
            regulation=legal_basis_regulation,
            article=legal_basis_article,
            jurisdiction=legal_basis_jurisdiction,
        )
        try:
            perimeter = _build_perimeter(
                allowed_actions,
                forbidden_actions,
                delegation_allowed,
                max_amount,
                currency,
                amount_actions,
            )
        except ValidationError as exc:
            return _error("perimeter_invalid", str(exc))
        mandate_data = MandateCreate(
            principal_id=principal_id,
            agent_id=agent_id,
            scope=scope,
            legal_basis=legal_basis,
            duration_hours=duration_hours,
            parent_mandate_id=parent_mandate_id,  # type: ignore[arg-type]
            metadata=metadata or {},
            perimeter=perimeter,
        )
        moment = signed_at if signed_at is not None else datetime.now(UTC).isoformat()
        payload = signed_mandate_payload(mandate_data, moment)
        return json.dumps(
            {
                "payload": payload.decode("utf-8"),
                "payload_b64url": b64url_encode(payload),
                "signed_at": moment,
            }
        )

    except PerimeterError as exc:
        return _error(exc.code, exc.message)

    except PrincipalSignatureError as exc:
        return _error(exc.code, exc.message)

    except Exception as exc:
        return json.dumps({"error": str(exc)})
