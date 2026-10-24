"""AMR tools: revoke_mandate and prepare_revocation_signature.

Revocation is append-only: a row in mandate_revocations (chained, SHA-256) plus a
"revoked" mandate event. The mandates row itself is never updated. From that row on,
the mandate counts as revoked everywhere: verify_mandate skips it, issue_action_token
refuses it (mandate_status_revoked), every sub-mandate below it is cut
(parent_mandate_revoked), no new sub-mandate can hang from it, and get_proof and
export_insurer_dossier report it.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import aiosqlite
from pydantic import BaseModel, Field, ValidationError

from amr.config import settings
from amr.crypto.chain import compute_hash
from amr.crypto.principal import (
    PrincipalSignatureError,
    b64url_encode,
    canonical_json,
    parse_public_key,
    parse_signature,
    parse_signed_at,
    verify,
)
from amr.db.engine import (
    get_db,
    get_last_revocation_hash,
    get_principal_key,
    get_revocation,
    init_db,
)
from amr.delegation import MAX_DELEGATION_DEPTH

REVOCATION_CONTEXT = "amr.revocation.v1"


def _error(code: str, message: str) -> str:
    return json.dumps({"error": f"{code}: {message}", "code": code})


class RevocationRequest(BaseModel):
    """Validated input of revoke_mandate and prepare_revocation_signature."""

    model_config = {"extra": "forbid"}

    mandate_id: UUID
    reason: str = Field(..., min_length=1, max_length=500)


def revocation_payload(
    *, mandate_id: str, principal_id: str, reason: str, signed_at: str
) -> bytes:
    """The exact bytes a principal signs to revoke one of its mandates."""
    return canonical_json(
        {
            "context": REVOCATION_CONTEXT,
            "mandate_id": mandate_id,
            "principal_id": principal_id,
            "reason": reason,
            "signed_at": signed_at,
        }
    )


def revocation_signature_valid(revocation: dict[str, Any], public_key: str | None) -> bool:
    """Re-check a stored revocation signature against the principal's registered key.

    The signed payload must name this mandate, this principal, this reason and this
    signed_at. Any damaged field reads as invalid.
    """
    try:
        if public_key is None:
            return False
        public_key_raw = parse_public_key(public_key)
        signature_raw = parse_signature(revocation["principal_signature"])
        payload_text = revocation["principal_signed_payload"]
        if not verify(public_key_raw, payload_text.encode("utf-8"), signature_raw):
            return False
        expected = revocation_payload(
            mandate_id=revocation["mandate_id"],
            principal_id=revocation["principal_id"],
            reason=revocation["reason"],
            signed_at=revocation["principal_signed_at"],
        )
        return payload_text.encode("utf-8") == expected
    except (ValueError, TypeError, KeyError, AttributeError, PrincipalSignatureError):
        return False


async def _check_revocation_signature(
    db: aiosqlite.Connection,
    mandate_id: str,
    principal_id: str,
    reason: str,
    principal_signature: str | None,
    signed_at: str | None,
    now: datetime,
) -> dict[str, str] | None:
    """Same policy as create_mandate: a principal with a registered key must sign.

    Returns the verified signature record, or None for an unsigned revocation.
    Raises PrincipalSignatureError with a stable code.
    """
    key_row = await get_principal_key(db, principal_id)
    if principal_signature is None and signed_at is None:
        if key_row is not None:
            raise PrincipalSignatureError(
                "principal_signature_required",
                "this principal has a registered key: the revocation must carry its signature",
            )
        if settings.require_principal_signature:
            raise PrincipalSignatureError(
                "principal_signature_required",
                "this registry requires every revocation to be signed by the principal",
            )
        return None
    if principal_signature is None or signed_at is None:
        raise PrincipalSignatureError(
            "principal_signature_incomplete",
            "principal_signature and signed_at must be given together",
        )
    signature_raw = parse_signature(principal_signature)
    signed_moment = parse_signed_at(signed_at)
    if key_row is None:
        raise PrincipalSignatureError(
            "principal_key_not_registered",
            "no public key is registered for this principal (register_principal_key)",
        )
    max_age = timedelta(seconds=settings.principal_signature_max_age_seconds)
    if abs(now - signed_moment) > max_age:
        raise PrincipalSignatureError(
            "principal_signature_stale",
            f"signed_at must be within {settings.principal_signature_max_age_seconds} "
            "seconds of the registry clock",
        )
    payload = revocation_payload(
        mandate_id=mandate_id, principal_id=principal_id, reason=reason, signed_at=signed_at
    )
    if not verify(parse_public_key(key_row["public_key"]), payload, signature_raw):
        raise PrincipalSignatureError(
            "principal_signature_invalid",
            "the signature does not match this revocation and the principal's registered key",
        )
    return {
        "signature": b64url_encode(signature_raw),
        "signed_at": signed_at,
        "key_id": key_row["key_id"],
        "payload": payload.decode("utf-8"),
    }


async def _outstanding_tokens(
    db: aiosqlite.Connection, mandate_id: str, now: datetime
) -> dict[str, Any]:
    """Tokens already issued under the mandate or its sub-mandates and not yet expired.

    A JWS cannot be called back: those tokens stay valid for their consumers until
    their exp. Returned so the principal knows exactly until when.
    """
    count = 0
    last: datetime | None = None
    frontier = [mandate_id]
    depth = 0
    while frontier and depth <= MAX_DELEGATION_DEPTH:
        next_frontier: list[str] = []
        for one_id in frontier:
            cursor = await db.execute(
                "SELECT expires_at FROM issued_tokens WHERE mandate_id = ?", (one_id,)
            )
            for row in await cursor.fetchall():
                expires = datetime.fromisoformat(row["expires_at"])
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=UTC)
                if expires > now:
                    count += 1
                    last = expires if last is None or expires > last else last
            cursor = await db.execute(
                "SELECT id FROM mandates WHERE parent_mandate_id = ?", (one_id,)
            )
            next_frontier.extend(row["id"] for row in await cursor.fetchall())
        frontier = next_frontier
        depth += 1
    return {
        "still_valid": count,
        "last_expires_at": last.isoformat() if last is not None else None,
    }


async def prepare_revocation_signature(
    mandate_id: str,
    reason: str,
    signed_at: str | None = None,
) -> str:
    """Return the exact bytes a principal must sign to revoke one of its mandates.

    Nothing is written. The principal signs payload (UTF-8 bytes; payload_b64url is
    the same bytes) with its Ed25519 key, then calls revoke_mandate with the same
    mandate_id and reason plus principal_signature and this signed_at.

    Args:
        mandate_id: UUID of the mandate to revoke.
        reason: Why it is revoked, as it will be recorded (1 to 500 characters).
        signed_at: ISO 8601 timestamp with timezone. Default: now (UTC).

    Returns:
        JSON string with keys: payload (str), payload_b64url, signed_at, principal_id.
        On error: {"error": "...", "code": "..."}.
    """
    db = None
    try:
        try:
            req = RevocationRequest(mandate_id=mandate_id, reason=reason)  # type: ignore[arg-type]
        except ValidationError as exc:
            return _error("invalid_input", exc.errors()[0]["msg"])
        moment = signed_at if signed_at is not None else datetime.now(UTC).isoformat()
        parse_signed_at(moment)
        await init_db(settings.db_path)
        db = await get_db(settings.db_path)
        cursor = await db.execute(
            "SELECT principal_id FROM mandates WHERE id = ?", (str(req.mandate_id),)
        )
        row = await cursor.fetchone()
        if row is None:
            return _error("mandate_not_found", f"no mandate '{req.mandate_id}'")
        payload = revocation_payload(
            mandate_id=str(req.mandate_id),
            principal_id=row["principal_id"],
            reason=req.reason,
            signed_at=moment,
        )
        return json.dumps(
            {
                "payload": payload.decode("utf-8"),
                "payload_b64url": b64url_encode(payload),
                "signed_at": moment,
                "principal_id": row["principal_id"],
            }
        )

    except PrincipalSignatureError as exc:
        return _error(exc.code, exc.message)

    except Exception as exc:
        return json.dumps({"error": str(exc)})

    finally:
        if db is not None:
            await db.close()


async def revoke_mandate(
    mandate_id: str,
    reason: str,
    principal_signature: str | None = None,
    signed_at: str | None = None,
) -> str:
    """Revoke a mandate now. Final: a revoked mandate cannot be reactivated.

    Only the mandate's own principal revokes it (for a sub-mandate, that is the agent
    that delegated it). If the principal has a registered key, the revocation must
    carry its signature: build the bytes with prepare_revocation_signature, sign them,
    and pass principal_signature and signed_at. With AMR_REQUIRE_PRINCIPAL_SIGNATURE,
    every revocation must be signed. Without a key, anyone who can call this tool can
    revoke: expose it to principals (or their back office), like create_mandate.

    Effect, from the moment this returns: no new token for the mandate or any
    sub-mandate below it, verify_mandate no longer returns it, and no sub-mandate can
    be created under it. Tokens already issued cannot be called back: they stay valid
    until their exp, given in outstanding_tokens.

    Args:
        mandate_id: UUID of the mandate to revoke.
        reason: Why it is revoked, recorded in the registry and the Proof Pack
                (1 to 500 characters). Example: "agent exceeded its order limit"
        principal_signature: Base64url Ed25519 signature of the revocation payload.
        signed_at: The signed_at placed in the payload (ISO 8601 with timezone).

    Returns:
        JSON string with keys: status ("revoked"), mandate_id, principal_id, reason,
        revoked_at, principal_signature ({key_id, signed_at} or null), chain_hash,
        outstanding_tokens ({still_valid, last_expires_at}).
        On error: {"error": "...", "code": "..."} with code mandate_not_found,
        mandate_already_revoked, invalid_input or a principal signature code.
    """
    db = None
    try:
        try:
            req = RevocationRequest(mandate_id=mandate_id, reason=reason)  # type: ignore[arg-type]
        except ValidationError as exc:
            return _error("invalid_input", exc.errors()[0]["msg"])
        canonical_id = str(req.mandate_id)
        now = datetime.now(UTC)

        await init_db(settings.db_path)
        db = await get_db(settings.db_path)

        cursor = await db.execute(
            "SELECT id, principal_id, chain_hash FROM mandates WHERE id = ?",
            (canonical_id,),
        )
        mandate = await cursor.fetchone()
        if mandate is None:
            return _error("mandate_not_found", f"no mandate '{canonical_id}'")
        if await get_revocation(db, canonical_id) is not None:
            return _error("mandate_already_revoked", "this mandate is already revoked")

        signature = await _check_revocation_signature(
            db,
            canonical_id,
            mandate["principal_id"],
            req.reason,
            principal_signature,
            signed_at,
            now,
        )

        revoked_at = now.isoformat()
        hash_data: dict[str, Any] = {
            "mandate_id": canonical_id,
            "mandate_chain_hash": mandate["chain_hash"],
            "principal_id": mandate["principal_id"],
            "reason": req.reason,
            "revoked_at": revoked_at,
        }
        if signature is not None:
            hash_data["principal_signature"] = {
                "signature": signature["signature"],
                "signed_at": signature["signed_at"],
                "key_id": signature["key_id"],
            }
        chain_hash = compute_hash(hash_data, await get_last_revocation_hash(db))

        await db.execute(
            """
            INSERT INTO mandate_revocations
              (mandate_id, principal_id, reason, revoked_at, principal_signature,
               principal_signed_at, principal_key_id, principal_signed_payload, chain_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                canonical_id,
                mandate["principal_id"],
                req.reason,
                revoked_at,
                signature["signature"] if signature else None,
                signature["signed_at"] if signature else None,
                signature["key_id"] if signature else None,
                signature["payload"] if signature else None,
                chain_hash,
            ),
        )
        await db.execute(
            """
            INSERT INTO mandate_events (mandate_id, event_type, timestamp, reason)
            VALUES (?, ?, ?, ?)
            """,
            (canonical_id, "revoked", revoked_at, req.reason),
        )
        outstanding = await _outstanding_tokens(db, canonical_id, now)
        await db.commit()

        return json.dumps(
            {
                "status": "revoked",
                "mandate_id": canonical_id,
                "principal_id": mandate["principal_id"],
                "reason": req.reason,
                "revoked_at": revoked_at,
                "principal_signature": (
                    {"key_id": signature["key_id"], "signed_at": signature["signed_at"]}
                    if signature
                    else None
                ),
                "chain_hash": chain_hash,
                "outstanding_tokens": outstanding,
            }
        )

    except PrincipalSignatureError as exc:
        return _error(exc.code, exc.message)

    except aiosqlite.IntegrityError as exc:
        if "mandate_revocations.mandate_id" in str(exc):
            return _error("mandate_already_revoked", "this mandate is already revoked")
        if "principal_signature" in str(exc):
            return _error(
                "principal_signature_replayed", "this signature already revoked a mandate"
            )
        return json.dumps({"error": str(exc)})

    except Exception as exc:
        return json.dumps({"error": str(exc)})

    finally:
        if db is not None:
            await db.close()
