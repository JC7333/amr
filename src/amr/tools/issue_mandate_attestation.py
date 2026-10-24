"""AMR tools: issue_mandate_attestation and get_registry_public_key.

An agent shows a third party a signed attestation of its mandate; the third party
checks it offline with the registry's public key (amr.attestation.verify_attestation).
"""

import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from pydantic import ValidationError

from amr.attestation import (
    ALGORITHM,
    ATTESTATION_TYP,
    ATTESTATION_VERSION,
    claims_digest,
)
from amr.config import settings
from amr.crypto.signing import (
    ensure_signing_key_exists,
    get_key_id,
    load_public_key,
    load_signing_key,
)
from amr.db.engine import get_db, init_db, record_issued_attestation
from amr.delegation import is_expired, load_ancestors
from amr.models.attestation import AttestationRequest
from amr.models.perimeter import Perimeter
from amr.tools.get_proof import principal_signature_status

_MANDATE_COLUMNS = """
    SELECT id, principal_id, agent_id, scope, legal_basis_json, status,
           created_at, expires_at, parent_mandate_id, metadata_json, chain_hash,
           perimeter_json, principal_signature, principal_signed_at,
           principal_key_id, principal_signed_payload
    FROM mandates
    WHERE id = ?
"""


def _denied(reason: str, mandate_id: str | None, refused_by: str | None = None) -> str:
    denial: dict[str, Any] = {"denied": True, "reason": reason, "mandate_id": mandate_id}
    if refused_by is not None:
        denial["refused_by"] = refused_by
    return json.dumps(denial)


def _perimeter_digest(perimeter_json: str | None) -> str | None:
    return Perimeter.from_json(perimeter_json).digest() if perimeter_json else None


def _decoded(row: Any) -> dict[str, Any]:
    """The mandate as in the Proof Pack (JSON columns decoded)."""
    return {
        "id": row["id"],
        "principal_id": row["principal_id"],
        "agent_id": row["agent_id"],
        "scope": row["scope"],
        "legal_basis": json.loads(row["legal_basis_json"]),
        "status": row["status"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "parent_mandate_id": row["parent_mandate_id"],
        "metadata": json.loads(row["metadata_json"]),
        "perimeter": json.loads(row["perimeter_json"]) if row["perimeter_json"] else None,
    }


async def issue_mandate_attestation(
    mandate_id: str,
    agent_id: str,
    audience: str | None = None,
    lifetime_seconds: int | None = None,
    include_principal_payload: bool = False,
) -> str:
    """Issue a signed attestation of a mandate, for the agent to show a third party.

    The receiver (a seller, a hospital, an insurer) verifies it offline with the
    registry's public key (see get_registry_public_key and amr.verify_attestation),
    without an account and without calling the registry. It states that the mandate
    exists, who granted it, the agent, the scope and structured perimeter, the expiry,
    the principal's own signature when there is one, and that the mandate and every
    mandate above it were active when the attestation was issued.

    Issued only if the mandate is active and unexpired, belongs to agent_id, every
    parent mandate is active and unexpired, and no principal signature in the chain
    is invalid or stripped. The attestation expires at the earliest of: now plus the
    lifetime (at most settings.attestation_lifetime_seconds), the mandate's expiry,
    any parent's expiry. A revocation made after issuance reaches an offline receiver
    only when the attestation expires: ask for a fresh one for each important act.

    Args:
        mandate_id: UUID of the mandate to attest.
        agent_id: Agent identifier, must match mandate.agent_id.
        audience: Optional receiver the attestation is addressed to (e.g. "seller:acme").
            The receiver must then name this audience when verifying.
        lifetime_seconds: Optional shorter lifetime. It can shorten, never extend,
            the configured maximum.
        include_principal_payload: For a principal-signed mandate, also include the
            principal's signature and the exact bytes it signed, so the receiver can
            re-check it without trusting the registry. Off by default: those bytes
            contain the mandate metadata, which is then disclosed to the receiver.

    Returns:
        JSON string. Success keys: attestation (compact JWS), jti, issued_at,
        expires_at, key_id, issuer. Denial keys: denied (true), reason, mandate_id,
        and refused_by for a problem higher in the delegation chain.
    """
    db = None
    try:
        try:
            req = AttestationRequest(
                mandate_id=UUID(mandate_id),
                agent_id=agent_id,
                audience=audience,
                lifetime_seconds=lifetime_seconds,
                include_principal_payload=include_principal_payload,
            )
        except (ValidationError, ValueError) as exc:
            return json.dumps({
                "denied": True, "reason": f"invalid_input: {exc}", "mandate_id": None
            })
        mandate_key = str(req.mandate_id)

        ensure_signing_key_exists()
        now = datetime.now(UTC).replace(microsecond=0)
        await init_db(settings.db_path)
        db = await get_db(settings.db_path)

        cursor = await db.execute(_MANDATE_COLUMNS, (mandate_key,))
        row = await cursor.fetchone()
        if row is None:
            return _denied("mandate_not_found", mandate_key)
        if row["agent_id"] != req.agent_id:
            return _denied("agent_mismatch", mandate_key)
        if row["status"] != "active":
            return _denied(f"mandate_status_{row['status']}", mandate_key)
        if is_expired(row["expires_at"], now):
            return _denied("mandate_expired", mandate_key)

        ancestors, refusal = await load_ancestors(db, row["parent_mandate_id"], now)
        if refusal is not None:
            return _denied(refusal.reason, mandate_key, refusal.refused_by)

        # Every principal signature in the chain must hold (none tampered or stripped).
        signature = None
        for link_id in [row["id"], *(link["id"] for link in ancestors)]:
            link_cursor = await db.execute(_MANDATE_COLUMNS, (link_id,))
            link_row = await link_cursor.fetchone()
            block, valid = await principal_signature_status(db, link_row, _decoded(link_row))
            if valid is False:
                return _denied(
                    "principal_signature_invalid",
                    mandate_key,
                    None if link_id == row["id"] else link_id,
                )
            if link_id == row["id"]:
                signature = block

        lifetime = settings.attestation_lifetime_seconds
        if req.lifetime_seconds is not None:
            lifetime = min(lifetime, req.lifetime_seconds)
        expiry = now + timedelta(seconds=lifetime)
        for entry in (row, *ancestors):
            entry_expiry = datetime.fromisoformat(entry["expires_at"])
            if entry_expiry.tzinfo is None:
                entry_expiry = entry_expiry.replace(tzinfo=UTC)
            expiry = min(expiry, entry_expiry)
        iat = int(now.timestamp())
        exp = int(expiry.timestamp())  # rounds down: never outlives a mandate
        if exp <= iat:
            return _denied("mandate_expired", mandate_key)

        mandate = _decoded(row)
        del mandate["metadata"]  # labels, possibly personal: not disclosed
        mandate["perimeter_digest"] = _perimeter_digest(row["perimeter_json"])
        mandate["chain_hash"] = row["chain_hash"]
        if signature is not None and not req.include_principal_payload:
            # The signed payload carries the metadata: disclose it only on request.
            signature = {
                "key_id": signature["key_id"],
                "public_key": signature["public_key"],
                "signed_at": signature["signed_at"],
                "algorithm": signature["algorithm"],
            }
        mandate["principal_signature"] = signature
        chain = [
            {
                "id": link["id"],
                "principal_id": link["principal_id"],
                "agent_id": link["agent_id"],
                "status": link["status"],
                "expires_at": link["expires_at"],
                "parent_mandate_id": link["parent_mandate_id"],
                "perimeter_digest": _perimeter_digest(link["perimeter_json"]),
            }
            for link in ancestors
        ]

        jti = str(uuid4())
        key_id = get_key_id()
        claims: dict[str, Any] = {
            "iss": settings.token_issuer,
            "sub": req.agent_id,
            "iat": iat,
            "nbf": iat,
            "exp": exp,
            "jti": jti,
            "amr_attestation": ATTESTATION_VERSION,
            "amr_mandate": mandate,
            "amr_chain": chain,
        }
        if req.audience is not None:
            claims["aud"] = req.audience

        private_key_pem = load_signing_key().private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        attestation = jwt.encode(
            claims,
            private_key_pem,
            algorithm=ALGORITHM,
            headers={"kid": key_id, "typ": ATTESTATION_TYP},
        )

        issued_at = datetime.fromtimestamp(iat, UTC).isoformat()
        expires_at = datetime.fromtimestamp(exp, UTC).isoformat()
        await record_issued_attestation(
            db,
            {
                "jti": jti,
                "mandate_id": mandate_key,
                "agent_id": req.agent_id,
                "audience": req.audience,
                "issued_at": issued_at,
                "expires_at": expires_at,
                "key_id": key_id,
                "claims_digest": claims_digest(claims),
            },
        )
        await db.commit()

        return json.dumps({
            "attestation": attestation,
            "jti": jti,
            "issued_at": issued_at,
            "expires_at": expires_at,
            "key_id": key_id,
            "issuer": settings.token_issuer,
        })

    except Exception as exc:
        return json.dumps({"denied": True, "reason": f"internal_error: {exc}"})
    finally:
        if db is not None:
            await db.close()


async def get_registry_public_key() -> str:
    """Return the registry's public key, for third parties who verify attestations.

    A receiver fetches it once, through a channel it trusts, and compares key_id with
    the one the registry operator publishes. It then verifies attestations offline.

    Returns:
        JSON string with keys: issuer, key_id, algorithm ("EdDSA"),
        public_key_pem, public_key_jwk ({kty "OKP", crv "Ed25519", x, kid, alg}).
        On error: {"error": "..."}.
    """
    try:
        ensure_signing_key_exists()
        public_key = load_public_key()
        pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")
        raw = public_key.public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        )
        key_id = get_key_id()
        return json.dumps({
            "issuer": settings.token_issuer,
            "key_id": key_id,
            "algorithm": ALGORITHM,
            "public_key_pem": pem,
            "public_key_jwk": {
                "kty": "OKP",
                "crv": "Ed25519",
                "x": base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii"),
                "kid": key_id,
                "alg": ALGORITHM,
            },
        })
    except Exception as exc:
        return json.dumps({"error": str(exc)})
