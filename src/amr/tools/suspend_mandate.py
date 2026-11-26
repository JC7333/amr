"""AMR tools: suspend_mandate, resume_mandate and prepare_suspension_signature.

A suspension pauses a mandate at once and can be lifted; a revocation (revoke_mandate)
is final. The principal designates, when it grants the mandate, the keys that may
suspend it (perimeter suspension_keys): a security officer, an on-call person. Any one
of them suspends alone, with its signature; only the principal lifts the suspension.

Append-only: each suspension or resumption is a row in mandate_suspensions (chained,
SHA-256, anchored to the mandate's own chain_hash) plus a "suspended" or "resumed"
mandate event. The mandates row is never updated. While the latest row is a suspension,
the mandate counts as suspended everywhere: issue_action_token, issue_mandate_attestation
and check_action_token refuse it (mandate_status_suspended), log_action records nothing,
verify_mandate does not return it, every sub-mandate below it is cut
(parent_mandate_suspended) and no new sub-mandate can hang from it; get_proof, the
insurer dossier and the public registry export show it.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

import aiosqlite
from pydantic import BaseModel, Field, ValidationError

from amr.config import settings
from amr.crypto.chain import compute_hash
from amr.crypto.principal import (
    PrincipalSignatureError,
    b64url_encode,
    canonical_json,
    key_id,
    parse_public_key,
    parse_signature,
    parse_signed_at,
    verify,
)
from amr.db.engine import (
    get_db,
    get_last_suspension_hash,
    get_principal_key,
    get_revocation,
    init_db,
)
from amr.delegation import is_suspended
from amr.models.perimeter import Perimeter
from amr.tool_errors import validation_field

SUSPENSION_CONTEXT = "amr.suspension.v1"


def _error(code: str, message: str, field: str | None = None) -> str:
    body = {"error": f"{code}: {message}", "code": code}
    if field is not None:
        body["field"] = field
    return json.dumps(body)


class SuspensionRequest(BaseModel):
    """Validated input of the suspension tools."""

    model_config = {"extra": "forbid"}

    mandate_id: UUID
    reason: str = Field(..., min_length=1, max_length=500)


def suspension_payload(
    *,
    action: str,
    mandate_id: str,
    principal_id: str,
    reason: str,
    key_id: str,
    signed_at: str,
) -> bytes:
    """The exact bytes signed to suspend (designated key) or resume (principal key)."""
    return canonical_json(
        {
            "context": SUSPENSION_CONTEXT,
            "action": action,
            "mandate_id": mandate_id,
            "principal_id": principal_id,
            "reason": reason,
            "key_id": key_id,
            "signed_at": signed_at,
        }
    )


def designated_keys(perimeter_json: str | None) -> tuple[str, ...]:
    """The suspension keys a mandate designates (empty for a mandate without any)."""
    if not perimeter_json:
        return ()
    return Perimeter.from_json(perimeter_json).suspension_keys


def suspension_record_hash(record: dict[str, Any], mandate_chain_hash: str, previous: str) -> str:
    """Chain hash of one suspension record (the same fields the tools seal)."""
    hash_data: dict[str, Any] = {
        "mandate_id": record["mandate_id"],
        "mandate_chain_hash": mandate_chain_hash,
        "action": record["action"],
        "reason": record["reason"],
        "recorded_at": record["recorded_at"],
    }
    if record["signature"] is not None:
        hash_data["signature"] = {
            "signature": record["signature"],
            "signed_at": record["signed_at"],
            "key_id": record["key_id"],
        }
    return compute_hash(hash_data, previous)


def suspension_signature_valid(
    record: dict[str, Any], principal_id: str, public_key: str | None
) -> bool:
    """Re-check a stored suspension or resumption signature against ``public_key``.

    The signed payload must be the one this record describes (action, mandate,
    principal, reason, key id and signed_at). Any damaged field reads as invalid.
    """
    try:
        if public_key is None or record["signature"] is None:
            return False
        public_key_raw = parse_public_key(public_key)
        if key_id(public_key_raw) != record["key_id"]:
            return False
        payload_text = record["signed_payload"]
        if not verify(public_key_raw, payload_text.encode("utf-8"),
                      parse_signature(record["signature"])):
            return False
        expected = suspension_payload(
            action=record["action"],
            mandate_id=record["mandate_id"],
            principal_id=principal_id,
            reason=record["reason"],
            key_id=record["key_id"],
            signed_at=record["signed_at"],
        )
        return payload_text.encode("utf-8") == expected
    except (ValueError, TypeError, KeyError, AttributeError, PrincipalSignatureError):
        return False


def _check_freshness(signed_at: str, now: datetime) -> None:
    signed_moment = parse_signed_at(signed_at)
    max_age = timedelta(seconds=settings.principal_signature_max_age_seconds)
    if abs(now - signed_moment) > max_age:
        raise PrincipalSignatureError(
            "principal_signature_stale",
            f"signed_at must be within {settings.principal_signature_max_age_seconds} "
            "seconds of the registry clock",
        )


async def _read_mandate(db: aiosqlite.Connection, mandate_id: str) -> aiosqlite.Row | None:
    cursor = await db.execute(
        "SELECT id, principal_id, chain_hash, perimeter_json FROM mandates WHERE id = ?",
        (mandate_id,),
    )
    return await cursor.fetchone()


async def _record(
    db: aiosqlite.Connection,
    mandate: aiosqlite.Row,
    action: str,
    reason: str,
    now: datetime,
    signature: dict[str, str] | None,
) -> dict[str, Any]:
    """Append one suspension record and its event (the caller commits)."""
    record: dict[str, Any] = {
        "mandate_id": mandate["id"],
        "action": action,
        "reason": reason,
        "recorded_at": now.isoformat(),
        "key_id": signature["key_id"] if signature else None,
        "public_key": signature["public_key"] if signature else None,
        "signature": signature["signature"] if signature else None,
        "signed_at": signature["signed_at"] if signature else None,
        "signed_payload": signature["payload"] if signature else None,
    }
    record["chain_hash"] = suspension_record_hash(
        record, mandate["chain_hash"], await get_last_suspension_hash(db)
    )
    await db.execute(
        """
        INSERT INTO mandate_suspensions
          (mandate_id, action, reason, recorded_at, key_id, public_key, signature,
           signed_at, signed_payload, chain_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record["mandate_id"],
            record["action"],
            record["reason"],
            record["recorded_at"],
            record["key_id"],
            record["public_key"],
            record["signature"],
            record["signed_at"],
            record["signed_payload"],
            record["chain_hash"],
        ),
    )
    await db.execute(
        "INSERT INTO mandate_events (mandate_id, event_type, timestamp, reason) "
        "VALUES (?, ?, ?, ?)",
        (
            mandate["id"],
            "suspended" if action == "suspend" else "resumed",
            record["recorded_at"],
            reason,
        ),
    )
    return record


async def prepare_suspension_signature(
    mandate_id: str,
    action: Literal["suspend", "resume"],
    reason: str,
    public_key: str = "",
    signed_at: str | None = None,
) -> str:
    """Return the exact bytes to sign to suspend a mandate, or to lift its suspension.

    Nothing is written. To suspend, the holder of a key the mandate designates
    (suspension_keys) signs payload with that key, then calls suspend_mandate with the
    same mandate_id, reason, public_key and signed_at. To resume, the principal signs
    with its registered key and calls resume_mandate.

    Args:
        mandate_id: UUID of the mandate.
        action: "suspend" or "resume".
        reason: Why, as it will be recorded (1 to 500 characters).
        public_key: To suspend: the designated public key that will sign (base64url
                    Ed25519). Ignored to resume (the principal's registered key is used).
        signed_at: ISO 8601 timestamp with timezone. Default: now (UTC).

    Returns:
        JSON string with keys: payload (str), payload_b64url, signed_at, principal_id,
        key_id. On error: {"error": "...", "code": "..."}.
    """
    db = None
    try:
        try:
            req = SuspensionRequest(mandate_id=mandate_id, reason=reason)  # type: ignore[arg-type]
        except ValidationError as exc:
            return _error("invalid_input", exc.errors()[0]["msg"], validation_field(exc))
        if action not in ("suspend", "resume"):
            return _error("invalid_input", "action must be 'suspend' or 'resume'", "action")
        moment = signed_at if signed_at is not None else datetime.now(UTC).isoformat()
        parse_signed_at(moment)
        await init_db(settings.db_path)
        db = await get_db(settings.db_path)
        mandate = await _read_mandate(db, str(req.mandate_id))
        if mandate is None:
            return _error("mandate_not_found", f"no mandate '{req.mandate_id}'")
        if action == "suspend":
            signer = key_id(parse_public_key(public_key))
        else:
            key_row = await get_principal_key(db, mandate["principal_id"])
            if key_row is None:
                return _error(
                    "principal_key_not_registered",
                    "no public key is registered for this principal (register_principal_key)",
                )
            signer = key_row["key_id"]
        payload = suspension_payload(
            action=action,
            mandate_id=str(req.mandate_id),
            principal_id=mandate["principal_id"],
            reason=req.reason,
            key_id=signer,
            signed_at=moment,
        )
        return json.dumps(
            {
                "payload": payload.decode("utf-8"),
                "payload_b64url": b64url_encode(payload),
                "signed_at": moment,
                "principal_id": mandate["principal_id"],
                "key_id": signer,
            }
        )

    except PrincipalSignatureError as exc:
        return _error(exc.code, exc.message)

    except Exception as exc:
        return json.dumps({"error": str(exc)})

    finally:
        if db is not None:
            await db.close()


async def suspend_mandate(
    mandate_id: str,
    reason: str,
    public_key: str,
    signature: str,
    signed_at: str,
) -> str:
    """Suspend a mandate now, with a key the principal designated for that. Reversible.

    Only a key listed in the mandate's suspension_keys (set by the principal in
    create_mandate) can suspend, and it must sign: build the bytes with
    prepare_suspension_signature (action "suspend"), sign them with that key, and pass
    public_key, signature and signed_at. A mandate that designates no key cannot be
    suspended (the principal can still revoke it). The key holder cannot lift the
    suspension: only the principal can (resume_mandate).

    Effect, from the moment this returns, until resume_mandate: no new token or
    attestation for the mandate or any sub-mandate below it, check_action_token
    answers valid false, log_action records nothing, verify_mandate does not return it,
    and no sub-mandate can be created under it. Tokens and attestations already issued
    cannot be called back: they stay valid until their exp for a receiver that checks
    them offline.

    Args:
        mandate_id: UUID of the mandate to suspend.
        reason: Why, recorded in the registry and the Proof Pack (1 to 500 characters).
                Example: "unusual orders, under review"
        public_key: The designated public key that signed (base64url Ed25519).
        signature: Base64url Ed25519 signature of the suspension payload.
        signed_at: The signed_at placed in the payload (ISO 8601 with timezone).

    Returns:
        JSON string with keys: status ("suspended"), mandate_id, principal_id, reason,
        suspended_at, key_id, chain_hash.
        On error: {"error": "...", "code": "..."} with code mandate_not_found,
        mandate_already_revoked, mandate_already_suspended, suspension_not_designated,
        suspension_key_not_designated, invalid_input or a signature code.
    """
    db = None
    try:
        try:
            req = SuspensionRequest(mandate_id=mandate_id, reason=reason)  # type: ignore[arg-type]
        except ValidationError as exc:
            return _error("invalid_input", exc.errors()[0]["msg"], validation_field(exc))
        canonical_id = str(req.mandate_id)
        now = datetime.now(UTC)
        public_key_raw = parse_public_key(public_key)
        signature_raw = parse_signature(signature)
        _check_freshness(signed_at, now)

        await init_db(settings.db_path)
        db = await get_db(settings.db_path)
        mandate = await _read_mandate(db, canonical_id)
        if mandate is None:
            return _error("mandate_not_found", f"no mandate '{canonical_id}'")
        keys = designated_keys(mandate["perimeter_json"])
        if not keys:
            return _error(
                "suspension_not_designated",
                "this mandate designates no suspension key (suspension_keys in "
                "create_mandate); its principal can revoke it",
            )
        normalized_key = b64url_encode(public_key_raw)
        if normalized_key not in keys:
            return _error(
                "suspension_key_not_designated",
                "this key is not one of the mandate's suspension_keys",
                "public_key",
            )
        signer = key_id(public_key_raw)
        payload = suspension_payload(
            action="suspend",
            mandate_id=canonical_id,
            principal_id=mandate["principal_id"],
            reason=req.reason,
            key_id=signer,
            signed_at=signed_at,
        )
        if not verify(public_key_raw, payload, signature_raw):
            return _error(
                "suspension_signature_invalid",
                "the signature does not match this suspension and this key",
                "signature",
            )

        await db.execute("BEGIN IMMEDIATE")
        if await get_revocation(db, canonical_id) is not None:
            await db.rollback()
            return _error("mandate_already_revoked", "this mandate is revoked")
        if await is_suspended(db, canonical_id):
            await db.rollback()
            return _error("mandate_already_suspended", "this mandate is already suspended")
        record = await _record(
            db,
            mandate,
            "suspend",
            req.reason,
            now,
            {
                "key_id": signer,
                "public_key": normalized_key,
                "signature": b64url_encode(signature_raw),
                "signed_at": signed_at,
                "payload": payload.decode("utf-8"),
            },
        )
        await db.commit()
        return json.dumps(
            {
                "status": "suspended",
                "mandate_id": canonical_id,
                "principal_id": mandate["principal_id"],
                "reason": req.reason,
                "suspended_at": record["recorded_at"],
                "key_id": signer,
                "chain_hash": record["chain_hash"],
            }
        )

    except PrincipalSignatureError as exc:
        return _error(exc.code, exc.message)

    except aiosqlite.IntegrityError as exc:
        if "signature" in str(exc):
            return _error("suspension_signature_replayed", "this signature was already used")
        return json.dumps({"error": str(exc)})

    except Exception as exc:
        return json.dumps({"error": str(exc)})

    finally:
        if db is not None:
            await db.close()


async def resume_mandate(
    mandate_id: str,
    reason: str,
    principal_signature: str | None = None,
    signed_at: str | None = None,
) -> str:
    """Lift the suspension of a mandate. Only the mandate's own principal can.

    Same signature policy as revoke_mandate: if the principal has a registered key, the
    resumption must carry its signature (prepare_suspension_signature with action
    "resume", then principal_signature and signed_at); with
    AMR_REQUIRE_PRINCIPAL_SIGNATURE, every resumption must be signed. Without a key,
    anyone who can call this tool can resume: expose it to principals only.

    Args:
        mandate_id: UUID of the suspended mandate.
        reason: Why the suspension is lifted (1 to 500 characters).
        principal_signature: Base64url Ed25519 signature of the resume payload.
        signed_at: The signed_at placed in the payload (ISO 8601 with timezone).

    Returns:
        JSON string with keys: status ("resumed"), mandate_id, principal_id, reason,
        resumed_at, principal_signature ({key_id, signed_at} or null), chain_hash.
        On error: {"error": "...", "code": "..."} with code mandate_not_found,
        mandate_already_revoked, mandate_not_suspended, invalid_input or a principal
        signature code.
    """
    db = None
    try:
        try:
            req = SuspensionRequest(mandate_id=mandate_id, reason=reason)  # type: ignore[arg-type]
        except ValidationError as exc:
            return _error("invalid_input", exc.errors()[0]["msg"], validation_field(exc))
        canonical_id = str(req.mandate_id)
        now = datetime.now(UTC)

        await init_db(settings.db_path)
        db = await get_db(settings.db_path)
        mandate = await _read_mandate(db, canonical_id)
        if mandate is None:
            return _error("mandate_not_found", f"no mandate '{canonical_id}'")

        key_row = await get_principal_key(db, mandate["principal_id"])
        signature: dict[str, str] | None = None
        if principal_signature is None and signed_at is None:
            if key_row is not None:
                raise PrincipalSignatureError(
                    "principal_signature_required",
                    "this principal has a registered key: the resumption must carry its "
                    "signature",
                )
            if settings.require_principal_signature:
                raise PrincipalSignatureError(
                    "principal_signature_required",
                    "this registry requires every resumption to be signed by the principal",
                )
        else:
            if principal_signature is None or signed_at is None:
                raise PrincipalSignatureError(
                    "principal_signature_incomplete",
                    "principal_signature and signed_at must be given together",
                )
            signature_raw = parse_signature(principal_signature)
            _check_freshness(signed_at, now)
            if key_row is None:
                raise PrincipalSignatureError(
                    "principal_key_not_registered",
                    "no public key is registered for this principal (register_principal_key)",
                )
            payload = suspension_payload(
                action="resume",
                mandate_id=canonical_id,
                principal_id=mandate["principal_id"],
                reason=req.reason,
                key_id=key_row["key_id"],
                signed_at=signed_at,
            )
            if not verify(parse_public_key(key_row["public_key"]), payload, signature_raw):
                raise PrincipalSignatureError(
                    "principal_signature_invalid",
                    "the signature does not match this resumption and the principal's "
                    "registered key",
                )
            signature = {
                "key_id": key_row["key_id"],
                "public_key": key_row["public_key"],
                "signature": b64url_encode(signature_raw),
                "signed_at": signed_at,
                "payload": payload.decode("utf-8"),
            }

        await db.execute("BEGIN IMMEDIATE")
        if await get_revocation(db, canonical_id) is not None:
            await db.rollback()
            return _error("mandate_already_revoked", "this mandate is revoked")
        if not await is_suspended(db, canonical_id):
            await db.rollback()
            return _error("mandate_not_suspended", "this mandate is not suspended")
        record = await _record(db, mandate, "resume", req.reason, now, signature)
        await db.commit()
        return json.dumps(
            {
                "status": "resumed",
                "mandate_id": canonical_id,
                "principal_id": mandate["principal_id"],
                "reason": req.reason,
                "resumed_at": record["recorded_at"],
                "principal_signature": (
                    {"key_id": signature["key_id"], "signed_at": signature["signed_at"]}
                    if signature
                    else None
                ),
                "chain_hash": record["chain_hash"],
            }
        )

    except PrincipalSignatureError as exc:
        return _error(exc.code, exc.message)

    except aiosqlite.IntegrityError as exc:
        if "signature" in str(exc):
            return _error(
                "principal_signature_replayed", "this signature was already used"
            )
        return json.dumps({"error": str(exc)})

    except Exception as exc:
        return json.dumps({"error": str(exc)})

    finally:
        if db is not None:
            await db.close()
