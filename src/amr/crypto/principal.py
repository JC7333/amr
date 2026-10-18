"""Principal signatures: the principal signs the mandate it grants (Ed25519).

Separate from the registry's own token key (amr.crypto.signing): this module only
verifies signatures made by principals with their own keys. It never holds a private key.

Encodings: public keys are the 32 raw Ed25519 bytes and signatures the 64 raw bytes,
both base64url without padding. Signed payloads are canonical JSON (sorted keys, no
spaces, UTF-8), always built by this module so the signer and the registry agree.
"""

import base64
import binascii
import hashlib
import json
from datetime import datetime
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

MANDATE_CONTEXT = "amr.mandate.v1"
KEY_REGISTRATION_CONTEXT = "amr.principal_key.v1"

_PUBLIC_KEY_BYTES = 32
_SIGNATURE_BYTES = 64
_B64URL_ALPHABET = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
)


class PrincipalSignatureError(Exception):
    """A principal key or signature problem, with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def b64url_encode(raw: bytes) -> str:
    """Base64url without padding."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(text: str, expected_len: int, what: str) -> bytes:
    """Decode base64url (padding optional) and check the decoded length.

    Raises PrincipalSignatureError(<what>_invalid) on any malformed input.
    """
    code = f"{what}_invalid"
    if not isinstance(text, str) or not text or len(text) > 200:
        raise PrincipalSignatureError(code, f"{what} must be a base64url string")
    stripped = text.rstrip("=")
    if any(c not in _B64URL_ALPHABET for c in stripped):
        raise PrincipalSignatureError(code, f"{what} must be base64url (A-Z a-z 0-9 - _)")
    try:
        raw = base64.urlsafe_b64decode(stripped + "=" * (-len(stripped) % 4))
    except (binascii.Error, ValueError) as exc:
        raise PrincipalSignatureError(code, f"{what} is not valid base64url") from exc
    if len(raw) != expected_len:
        raise PrincipalSignatureError(code, f"{what} must decode to {expected_len} bytes")
    return raw


def parse_public_key(public_key: str) -> bytes:
    """Return the 32 raw bytes of a base64url Ed25519 public key, or raise."""
    raw = b64url_decode(public_key, _PUBLIC_KEY_BYTES, "public_key")
    try:
        ed25519.Ed25519PublicKey.from_public_bytes(raw)
    except ValueError as exc:
        raise PrincipalSignatureError("public_key_invalid", "not an Ed25519 key") from exc
    return raw


def parse_signature(signature: str) -> bytes:
    """Return the 64 raw bytes of a base64url Ed25519 signature, or raise."""
    return b64url_decode(signature, _SIGNATURE_BYTES, "principal_signature")


def key_id(public_key_raw: bytes) -> str:
    """Stable key identifier: first 16 hex chars of SHA-256 of the raw public key."""
    return hashlib.sha256(public_key_raw).hexdigest()[:16]


def verify(public_key_raw: bytes, payload: bytes, signature_raw: bytes) -> bool:
    """True if ``signature_raw`` is a valid Ed25519 signature of ``payload``."""
    try:
        ed25519.Ed25519PublicKey.from_public_bytes(public_key_raw).verify(
            signature_raw, payload
        )
    except (InvalidSignature, ValueError):
        return False
    return True


def canonical_json(obj: dict[str, Any]) -> bytes:
    """Canonical JSON bytes: sorted keys, no whitespace, UTF-8."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def parse_signed_at(signed_at: str) -> datetime:
    """Parse an ISO 8601 timestamp that must carry a timezone, or raise."""
    if not isinstance(signed_at, str) or not signed_at or len(signed_at) > 64:
        raise PrincipalSignatureError("signed_at_invalid", "signed_at must be an ISO 8601 string")
    try:
        moment = datetime.fromisoformat(signed_at)
    except ValueError as exc:
        raise PrincipalSignatureError(
            "signed_at_invalid", "signed_at must be an ISO 8601 timestamp"
        ) from exc
    if moment.tzinfo is None:
        raise PrincipalSignatureError(
            "signed_at_invalid", "signed_at must include a timezone, e.g. +00:00"
        )
    return moment


def mandate_payload(
    *,
    principal_id: str,
    agent_id: str,
    scope: str,
    legal_basis: dict[str, str],
    duration_hours: float,
    parent_mandate_id: str | None,
    metadata: dict[str, str],
    perimeter: dict[str, Any] | None,
    signed_at: str,
) -> bytes:
    """The exact bytes a principal signs to grant a mandate.

    Covers every field the principal decides; the registry adds only the mandate id
    and the timestamps. ``perimeter`` is the requested perimeter in canonical form.
    """
    return canonical_json(
        {
            "context": MANDATE_CONTEXT,
            "principal_id": principal_id,
            "agent_id": agent_id,
            "scope": scope,
            "legal_basis": legal_basis,
            "duration_hours": float(duration_hours),
            "parent_mandate_id": parent_mandate_id,
            "metadata": metadata,
            "perimeter": perimeter,
            "signed_at": signed_at,
        }
    )


def key_registration_payload(principal_id: str, public_key: str) -> bytes:
    """The exact bytes a principal signs to prove it holds the key it registers."""
    return canonical_json(
        {
            "context": KEY_REGISTRATION_CONTEXT,
            "principal_id": principal_id,
            "public_key": public_key,
        }
    )
