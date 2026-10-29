"""AMR tool: check_action_token — the receiver re-checks a token when it acts.

A token is signed for a short window. Between issuance and execution the mandate (or a
mandate above it) may be revoked, suspended or expire; the signature alone cannot say
so. Before an irreversible action, the receiver asks the registry: is this token one
the registry issued, and do its mandate and the whole delegation chain still stand?
Read only: the database is opened read-only and the check writes nothing.
"""

import json
from datetime import UTC, datetime
from typing import Any

import aiosqlite
import jwt
from pydantic import ValidationError

from amr.config import settings
from amr.crypto.signing import get_key_id, load_public_key
from amr.db.engine import get_issued_token
from amr.delegation import is_expired, is_revoked, load_ancestors
from amr.models.token import CheckTokenRequest

ALGORITHM = "EdDSA"
REQUIRED_CLAIMS = ["iss", "sub", "aud", "exp", "nbf", "iat", "jti", "amr_mandate_id",
                   "amr_action_hash"]


def _result(valid: bool, reason: str, checked_at: datetime, **fields: Any) -> str:
    body: dict[str, Any] = {"valid": valid, "reason": reason}
    body.update({key: value for key, value in fields.items() if value is not None})
    body["checked_at"] = checked_at.isoformat()
    return json.dumps(body)


def _decode(token: str, audience: str) -> tuple[dict[str, Any] | None, str, str | None]:
    """Verify header, signature, iss, aud, exp and nbf. Returns (claims, reason, detail)."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError:
        return None, "malformed", "not a compact JWS"
    # Algorithm fixed to EdDSA: never alg=none, never an RS256/HS256 substitution.
    if header.get("alg") != ALGORITHM:
        return None, "wrong_algorithm", "only EdDSA is accepted"
    if not settings.public_key_path.exists():
        return None, "key_mismatch", "this registry has no signing key"
    if header.get("kid") != get_key_id():
        return None, "key_mismatch", "signed with another registry key"
    try:
        claims = jwt.decode(
            token,
            load_public_key(),
            algorithms=[ALGORITHM],
            audience=audience,
            issuer=settings.token_issuer,
            options={"require": REQUIRED_CLAIMS},
        )
    except jwt.InvalidSignatureError:
        return None, "bad_signature", "signature does not verify"
    except jwt.ExpiredSignatureError:
        return None, "token_expired", None
    except jwt.ImmatureSignatureError:
        return None, "token_not_yet_valid", None
    except jwt.InvalidAudienceError:
        return None, "wrong_audience", "addressed to another receiver"
    except jwt.InvalidIssuerError:
        return None, "wrong_issuer", "issued by another registry"
    except jwt.MissingRequiredClaimError as exc:
        return None, "missing_claim", str(exc)
    except jwt.InvalidTokenError as exc:
        return None, "malformed", str(exc)
    return claims, "ok", None


async def _open_read_only() -> aiosqlite.Connection | None:
    """The registry database, read-only; None if it does not exist (never created here)."""
    path = settings.db_path.resolve()
    if not path.is_file():
        return None
    db = await aiosqlite.connect(f"{path.as_uri()}?mode=ro", uri=True)
    db.row_factory = aiosqlite.Row
    return db


async def check_action_token(
    token: str,
    audience: str,
    expected_action_hash: str | None = None,
    max_token_age_seconds: int | None = None,
) -> str:
    """Re-check an action token with the registry at the moment of acting.

    For the receiver of an agent's action, typically before an irreversible one (a
    payment, a sent document, a signed order), and always when the token carries
    amr_registry_check: true. The signature only proves the action was authorized
    when the token was issued; this check also says whether it still is now.

    Checks, in order: header (EdDSA only, key of this registry), signature, iss, aud,
    exp, nbf; the token is one this registry issued (its jti, mandate, action hash and
    audience match the issued_tokens record); the action hash, if you give one; the
    token's age, if you set a maximum; then the mandate is still active, not revoked,
    not expired and held by the token's agent, and so is every mandate above it in the
    delegation chain. Read only: the database is opened read-only, nothing is written,
    and the answer is not signed. Call the registry over your own channel: never accept
    a check result relayed by the agent whose token it is.

    Args:
        token: The compact JWS returned by issue_action_token.
        audience: Who you are; must equal the token's aud.
        expected_action_hash: Optional SHA-256 (64 lowercase hex) of the canonical
            action you are about to perform; must equal amr_action_hash.
        max_token_age_seconds: Optional stricter bound you set as receiver (1 to
            86400): refuse a token issued more than this many seconds ago. It can
            only tighten the check; a token past its exp is refused whatever you set.

    Returns:
        JSON string. Valid: {valid: true, reason: "ok", jti, mandate_id, agent_id,
        action_type (if sealed), registry_check_required, expires_at, checked_at}.
        Refused: {valid: false, reason, detail?, jti?, mandate_id?, refused_by?,
        checked_at}. Reasons: invalid_input, malformed, wrong_algorithm,
        key_mismatch, bad_signature, wrong_issuer, wrong_audience, token_expired,
        token_not_yet_valid, missing_claim, registry_unavailable, unknown_token,
        token_record_mismatch,
        action_mismatch, token_too_old, mandate_not_found, agent_mismatch,
        mandate_status_<status>, mandate_status_revoked, mandate_expired,
        parent_mandate_<status>, parent_mandate_revoked, parent_mandate_expired,
        parent_mandate_not_found, delegation_chain_too_deep, internal_error.
    """
    now = datetime.now(UTC)
    db = None
    try:
        try:
            req = CheckTokenRequest(
                token=token,
                audience=audience,
                expected_action_hash=expected_action_hash,
                max_token_age_seconds=max_token_age_seconds,
            )
        except ValidationError as exc:
            return _result(False, "invalid_input", now, detail=str(exc))

        claims, reason, detail = _decode(req.token, req.audience)
        if claims is None:
            return _result(False, reason, now, detail=detail)
        jti = str(claims["jti"])
        mandate_id = str(claims["amr_mandate_id"])

        db = await _open_read_only()
        if db is None:
            return _result(
                False,
                "registry_unavailable",
                now,
                detail="no registry database at the configured path",
                jti=jti,
                mandate_id=mandate_id,
            )

        record = await get_issued_token(db, jti)
        if record is None:
            return _result(False, "unknown_token", now, jti=jti, mandate_id=mandate_id)
        if (
            record["mandate_id"] != mandate_id
            or record["action_hash"] != claims["amr_action_hash"]
            or record["audience"] != claims["aud"]
            or record["agent_id"] != claims["sub"]
        ):
            return _result(False, "token_record_mismatch", now, jti=jti, mandate_id=mandate_id)

        if (
            req.expected_action_hash is not None
            and req.expected_action_hash != claims["amr_action_hash"]
        ):
            return _result(False, "action_mismatch", now, jti=jti, mandate_id=mandate_id)

        if (
            req.max_token_age_seconds is not None
            and now.timestamp() - int(claims["iat"]) > req.max_token_age_seconds
        ):
            return _result(False, "token_too_old", now, jti=jti, mandate_id=mandate_id)

        cursor = await db.execute(
            "SELECT id, agent_id, status, expires_at, parent_mandate_id FROM mandates "
            "WHERE id = ?",
            (mandate_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return _result(False, "mandate_not_found", now, jti=jti, mandate_id=mandate_id)
        if row["agent_id"] != claims["sub"]:
            return _result(False, "agent_mismatch", now, jti=jti, mandate_id=mandate_id)
        if row["status"] != "active":
            return _result(
                False, f"mandate_status_{row['status']}", now, jti=jti, mandate_id=mandate_id
            )
        if await is_revoked(db, row["id"]):
            return _result(False, "mandate_status_revoked", now, jti=jti, mandate_id=mandate_id)
        if is_expired(row["expires_at"], now):
            return _result(False, "mandate_expired", now, jti=jti, mandate_id=mandate_id)

        _, refusal = await load_ancestors(db, row["parent_mandate_id"], now)
        if refusal is not None:
            return _result(
                False,
                refusal.reason,
                now,
                jti=jti,
                mandate_id=mandate_id,
                refused_by=refusal.refused_by,
            )

        return _result(
            True,
            "ok",
            now,
            jti=jti,
            mandate_id=mandate_id,
            agent_id=claims["sub"],
            action_type=claims.get("amr_action_type"),
            registry_check_required=claims.get("amr_registry_check") is True,
            expires_at=datetime.fromtimestamp(int(claims["exp"]), UTC).isoformat(),
        )

    except Exception as exc:
        return _result(False, "internal_error", now, detail=str(exc))
    finally:
        if db is not None:
            await db.close()
