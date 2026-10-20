"""Mandate attestations: a signed statement a third party checks offline.

An agent asks the registry for an attestation of its mandate (tool
``issue_mandate_attestation``) and shows it to whoever receives it: a seller, a
hospital, an insurer. The receiver checks it alone, with the registry's public key
obtained once (tool ``get_registry_public_key``), without an account and without
calling the registry: the mandate exists, who granted it, what it allows, until when,
and that it was active, along its whole delegation chain, when the attestation was
issued.

This module is the receiver's side. It reads no database and makes no network call.
See docs/mandate-attestation-spec.md.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from amr.crypto.principal import (
    MANDATE_CONTEXT,
    PrincipalSignatureError,
    key_id,
    parse_public_key,
    parse_signature,
    verify,
)
from amr.delegation import MAX_DELEGATION_DEPTH
from amr.models.perimeter import Perimeter

ATTESTATION_TYP = "amr-attestation+jwt"
ATTESTATION_VERSION = "mandate.v1"
# EdDSA is the only algorithm accepted, in issuance and in verification.
ALGORITHM = "EdDSA"

_MANDATE_KEYS = (
    "id",
    "principal_id",
    "agent_id",
    "scope",
    "legal_basis",
    "status",
    "created_at",
    "expires_at",
    "parent_mandate_id",
    "perimeter",
    "perimeter_digest",
    "chain_hash",
    "principal_signature",
)
_LINK_KEYS = (
    "id",
    "principal_id",
    "agent_id",
    "status",
    "expires_at",
    "parent_mandate_id",
    "perimeter_digest",
)
_SIGNATURE_KEYS = ("key_id", "public_key", "signature", "signed_at", "payload")


class AttestationError(Exception):
    """An attestation failed a check. ``code`` is stable and machine-readable."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def registry_key_id(public_key: ed25519.Ed25519PublicKey) -> str:
    """Key identifier of the registry key: first 16 hex chars of SHA-256 of its raw bytes."""
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return hashlib.sha256(raw).hexdigest()[:16]


def claims_digest(claims: dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON of the claims (kept in the issuance audit)."""
    canonical = json.dumps(claims, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _timestamp(moment: str) -> float:
    parsed = datetime.fromisoformat(moment)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def _iso(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, UTC).isoformat()


def _require_keys(obj: Any, keys: tuple[str, ...], what: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise AttestationError("claims_invalid", f"{what} must be an object")
    missing = [key for key in keys if key not in obj]
    if missing:
        raise AttestationError("claims_invalid", f"{what} lacks {', '.join(missing)}")
    return obj


def _perimeter_digest(perimeter: Any) -> str | None:
    if perimeter is None:
        return None
    try:
        return Perimeter.model_validate(perimeter).digest()
    except ValueError as exc:
        raise AttestationError("claims_invalid", "perimeter is not a valid perimeter") from exc


def _check_principal_signature(mandate: dict[str, Any]) -> None:
    """Re-check the principal's own Ed25519 signature carried in the attestation.

    It must verify with the principal's public key, that key must match its key id,
    and the signed payload must name this principal, agent, scope, legal basis and
    parent (and, for a root mandate, this exact perimeter).
    """
    block = _require_keys(mandate["principal_signature"], _SIGNATURE_KEYS, "principal_signature")
    try:
        public_key_raw = parse_public_key(block["public_key"])
        signature_raw = parse_signature(block["signature"])
    except PrincipalSignatureError as exc:
        raise AttestationError("principal_signature_invalid", exc.code) from exc
    if key_id(public_key_raw) != block["key_id"]:
        raise AttestationError("principal_signature_invalid", "key_id does not match key")
    payload_text = block["payload"]
    if not isinstance(payload_text, str) or not verify(
        public_key_raw, payload_text.encode("utf-8"), signature_raw
    ):
        raise AttestationError("principal_signature_invalid", "signature does not verify")
    try:
        payload = json.loads(payload_text)
    except ValueError as exc:
        raise AttestationError("principal_signature_invalid", "payload is not JSON") from exc
    if not isinstance(payload, dict):
        raise AttestationError("principal_signature_invalid", "payload is not an object")
    expected = {
        "context": MANDATE_CONTEXT,
        "principal_id": mandate["principal_id"],
        "agent_id": mandate["agent_id"],
        "scope": mandate["scope"],
        "legal_basis": mandate["legal_basis"],
        "parent_mandate_id": mandate["parent_mandate_id"],
        "signed_at": block["signed_at"],
    }
    if mandate["parent_mandate_id"] is None:
        expected["perimeter"] = mandate["perimeter"]
    for field, value in expected.items():
        if payload.get(field) != value:
            raise AttestationError(
                "principal_signature_invalid", f"signed {field} differs from the mandate"
            )


def check_claims(claims: dict[str, Any], now: float, leeway: int = 0) -> dict[str, Any]:
    """Check the content of verified claims; return the receiver's summary or raise.

    The JWS signature must already have been verified (see verify_attestation).
    """
    for name in ("iss", "sub", "iat", "nbf", "exp", "jti"):
        if name not in claims:
            raise AttestationError("claims_invalid", f"missing claim {name}")
    if claims.get("amr_attestation") != ATTESTATION_VERSION:
        raise AttestationError("not_an_attestation", "amr_attestation claim missing or unknown")
    for name in ("iat", "nbf", "exp"):
        if isinstance(claims[name], bool) or not isinstance(claims[name], int):
            raise AttestationError("claims_invalid", f"{name} must be an integer")
    if claims["nbf"] > now + leeway:
        raise AttestationError("not_yet_valid", f"valid from {_iso(claims['nbf'])}")
    if claims["exp"] <= now - leeway:
        raise AttestationError("expired", f"expired at {_iso(claims['exp'])}")

    mandate = _require_keys(claims.get("amr_mandate"), _MANDATE_KEYS, "amr_mandate")
    chain = claims.get("amr_chain")
    if not isinstance(chain, list) or len(chain) > MAX_DELEGATION_DEPTH:
        raise AttestationError("claims_invalid", "amr_chain must be a list of parent mandates")
    links = [_require_keys(link, _LINK_KEYS, "amr_chain entry") for link in chain]

    if claims["sub"] != mandate["agent_id"]:
        raise AttestationError("claims_invalid", "sub differs from the mandate's agent")
    if _perimeter_digest(mandate["perimeter"]) != mandate["perimeter_digest"]:
        raise AttestationError("claims_invalid", "perimeter_digest does not match perimeter")

    # The chain must be complete and in order: mandate -> parent -> ... -> root.
    expected_parent = mandate["parent_mandate_id"]
    for link in links:
        if link["id"] != expected_parent:
            raise AttestationError("claims_invalid", "amr_chain is incomplete or out of order")
        expected_parent = link["parent_mandate_id"]
    if expected_parent is not None:
        raise AttestationError("claims_invalid", "amr_chain does not reach a root mandate")

    # Active, and not expired before the attestation, at every level.
    for entry in (mandate, *links):
        if entry["status"] != "active":
            raise AttestationError("claims_invalid", f"mandate {entry['id']} is not active")
        try:
            entry_expiry = _timestamp(entry["expires_at"])
        except (TypeError, ValueError) as exc:
            raise AttestationError("claims_invalid", "expires_at is not ISO 8601") from exc
        if claims["exp"] > entry_expiry:
            raise AttestationError(
                "claims_invalid", f"attestation outlives mandate {entry['id']}"
            )

    if mandate["principal_signature"] is not None:
        _check_principal_signature(mandate)

    signature = mandate["principal_signature"]
    return {
        "mandate_id": mandate["id"],
        "principal_id": mandate["principal_id"],
        "agent_id": mandate["agent_id"],
        "scope": mandate["scope"],
        "legal_basis": mandate["legal_basis"],
        "perimeter": mandate["perimeter"],
        "mandate_expires_at": mandate["expires_at"],
        "delegated": mandate["parent_mandate_id"] is not None,
        "delegation_chain": [
            {"mandate_id": link["id"], "principal_id": link["principal_id"],
             "agent_id": link["agent_id"]}
            for link in links
        ],
        "principal_signed": signature is not None,
        "principal_key_id": signature["key_id"] if signature is not None else None,
        "issuer": claims["iss"],
        "audience": claims.get("aud"),
        "status_checked_at": _iso(claims["iat"]),
        "attestation_expires_at": _iso(claims["exp"]),
        "jti": claims["jti"],
    }


def _load_public_key(public_key_pem: bytes | str) -> ed25519.Ed25519PublicKey:
    pem = public_key_pem.encode("ascii") if isinstance(public_key_pem, str) else public_key_pem
    try:
        key = serialization.load_pem_public_key(pem)
    except ValueError as exc:
        raise AttestationError("public_key_invalid", "not a PEM public key") from exc
    if not isinstance(key, ed25519.Ed25519PublicKey):
        raise AttestationError("public_key_invalid", "the registry key must be Ed25519")
    return key


def verify_attestation(
    attestation: str,
    public_key_pem: bytes | str,
    *,
    audience: str | None = None,
    issuer: str | None = None,
    now: float | None = None,
    leeway: int = 0,
) -> dict[str, Any]:
    """Verify a mandate attestation offline, with the registry's public key only.

    Checks, in order: the header (EdDSA only, attestation type, key id of this key),
    the Ed25519 signature, the issuer and audience when given (an attestation addressed
    to an audience is accepted only by a receiver that names that audience), the
    validity window, then the content (see check_claims), including the principal's
    own signature when the mandate carries one.

    Args:
        attestation: The compact JWS returned by issue_mandate_attestation.
        public_key_pem: The registry's public key (PEM), from get_registry_public_key.
        audience: Who you are, if the attestation must be addressed to you.
        issuer: The registry you expect (its token_issuer), if you want it checked.
        now: Unix time to check against (default: the current time).
        leeway: Seconds of clock skew tolerated on nbf and exp.

    Returns:
        {"valid": true, "reason": "ok", "attestation": {...summary}} or
        {"valid": false, "reason": "<code>", "detail": "..."}.
    """
    moment = datetime.now(UTC).timestamp() if now is None else now
    try:
        public_key = _load_public_key(public_key_pem)
        try:
            header = jwt.get_unverified_header(attestation)
        except jwt.InvalidTokenError as exc:
            raise AttestationError("malformed", "not a compact JWS") from exc
        if header.get("alg") != ALGORITHM:
            raise AttestationError("wrong_algorithm", "only EdDSA is accepted")
        if header.get("typ") != ATTESTATION_TYP:
            raise AttestationError("not_an_attestation", f"typ must be {ATTESTATION_TYP}")
        if header.get("kid") != registry_key_id(public_key):
            raise AttestationError("key_mismatch", "signed with another registry key")
        try:
            claims = jwt.decode(
                attestation,
                public_key,
                algorithms=[ALGORITHM],
                options={
                    "verify_exp": False,
                    "verify_nbf": False,
                    "verify_iat": False,
                    "verify_aud": False,
                    "verify_iss": False,
                },
            )
        except jwt.InvalidSignatureError as exc:
            raise AttestationError("bad_signature", "signature does not verify") from exc
        except jwt.InvalidTokenError as exc:
            raise AttestationError("malformed", str(exc)) from exc
        if issuer is not None and claims.get("iss") != issuer:
            raise AttestationError("wrong_issuer", "issued by another registry")
        token_audience = claims.get("aud")
        if token_audience is not None and token_audience != audience:
            raise AttestationError("wrong_audience", "addressed to another receiver")
        if audience is not None and token_audience is None:
            raise AttestationError("wrong_audience", "not addressed to any receiver")
        summary = check_claims(claims, moment, leeway)
    except AttestationError as exc:
        return {"valid": False, "reason": exc.code, "detail": exc.detail}
    return {"valid": True, "reason": "ok", "attestation": summary}
