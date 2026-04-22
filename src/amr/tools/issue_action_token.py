"""AMR tool: issue_action_token — structural hard-stop token issuer.

This is the enforcement layer: no valid mandate → no token → no action.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from pydantic import ValidationError

from amr.config import settings
from amr.crypto.signing import ensure_signing_key_exists, get_key_id, load_signing_key
from amr.db.engine import (
    get_db,
    init_db,
    is_token_replay,
    record_issued_token,
)
from amr.models.token import IssueTokenRequest


def _canonical_action_hash(action: str, audience: str, metadata: dict[str, str]) -> str:
    """Canonical SHA-256 hash of the action descriptor.

    Uses sorted keys and compact separators for reproducibility across
    languages and implementations. Consumers MUST use the exact same
    canonicalization when verifying a token.
    """
    canonical = json.dumps(
        {"action": action, "audience": audience, "metadata": metadata},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _scope_digest(scope: str) -> str:
    """SHA-256 of the mandate scope at issuance time."""
    return hashlib.sha256(scope.encode("utf-8")).hexdigest()


async def issue_action_token(
    mandate_id: str,
    agent_id: str,
    action: str,
    audience: str,
    action_metadata_json: str = "{}",
    lifetime_override_seconds: int | None = None,
) -> str:
    """Issue a signed action token IF AND ONLY IF a valid mandate authorizes it.

    This is the hard-stop: no valid mandate → no token → no action possible.
    Returns a JSON string with either {token, jti, expires_at, key_id}
    on success, or {denied: true, reason: "...", mandate_id: "..."} on denial.

    Args:
        mandate_id: UUID of the mandate the agent invokes.
        agent_id: Agent identifier, must match mandate.agent_id.
        action: Description of the action to be authorized.
        audience: Where the token will be presented (runtime/platform URL or id).
        action_metadata_json: Optional JSON-encoded dict of additional action metadata.
        lifetime_override_seconds: Optional override for token lifetime.
            Intended for tests only. If None, uses settings.token_lifetime_seconds.

    Returns:
        JSON string. Success keys: token, jti, expires_at, key_id.
        Denial keys: denied (true), reason, mandate_id.
    """
    db = None
    try:
        # --- 1. Validate inputs via Pydantic ---
        try:
            metadata_raw = (
                json.loads(action_metadata_json) if action_metadata_json else {}
            )
            if not isinstance(metadata_raw, dict):
                return json.dumps({
                    "denied": True,
                    "reason": "invalid_input: action_metadata_json must decode to a dict",
                })
            req = IssueTokenRequest(
                mandate_id=UUID(mandate_id),
                agent_id=agent_id,
                action=action,
                audience=audience,
                action_metadata=metadata_raw,
            )
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            return json.dumps({"denied": True, "reason": f"invalid_input: {exc}"})

        # --- 2. Ensure signing key exists (generates on first use) ---
        ensure_signing_key_exists()

        # --- 3. Fetch mandate and perform hard checks ---
        now = datetime.now(UTC)
        await init_db(settings.db_path)
        db = await get_db(settings.db_path)

        cursor = await db.execute(
            """
            SELECT id, agent_id, scope, status, expires_at
            FROM mandates
            WHERE id = ?
            """,
            (str(req.mandate_id),),
        )
        row = await cursor.fetchone()

        if row is None:
            return json.dumps({
                "denied": True,
                "reason": "mandate_not_found",
                "mandate_id": str(req.mandate_id),
            })

        if row["agent_id"] != req.agent_id:
            return json.dumps({
                "denied": True,
                "reason": "agent_mismatch",
                "mandate_id": str(req.mandate_id),
            })

        if row["status"] != "active":
            return json.dumps({
                "denied": True,
                "reason": f"mandate_status_{row['status']}",
                "mandate_id": str(req.mandate_id),
            })

        mandate_expires = datetime.fromisoformat(row["expires_at"])
        # Ensure timezone awareness (SQLite stores ISO strings; reparse as UTC)
        if mandate_expires.tzinfo is None:
            mandate_expires = mandate_expires.replace(tzinfo=UTC)
        if mandate_expires <= now:
            return json.dumps({
                "denied": True,
                "reason": "mandate_expired",
                "mandate_id": str(req.mandate_id),
            })

        # --- 4. Replay prevention ---
        action_hash = _canonical_action_hash(
            req.action, req.audience, req.action_metadata
        )
        if await is_token_replay(
            db, str(req.mandate_id), action_hash, now.isoformat()
        ):
            return json.dumps({
                "denied": True,
                "reason": "replay_detected_active_token_exists",
                "mandate_id": str(req.mandate_id),
            })

        # --- 5. Build JWS claims ---
        jti = uuid4()
        lifetime = (
            lifetime_override_seconds
            if lifetime_override_seconds is not None
            else settings.token_lifetime_seconds
        )
        expires_at = now + timedelta(seconds=lifetime)
        scope_digest = _scope_digest(row["scope"])
        key_id = get_key_id()

        claims = {
            "iss": settings.token_issuer,
            "sub": req.agent_id,
            "aud": req.audience,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "jti": str(jti),
            "amr_mandate_id": str(req.mandate_id),
            "amr_action_hash": action_hash,
            "amr_scope_digest": scope_digest,
        }

        # Load key and serialize to PEM bytes (pyjwt expects bytes or str for EdDSA)
        private_key = load_signing_key()
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        token = jwt.encode(
            claims,
            private_key_pem,
            algorithm="EdDSA",
            headers={"kid": key_id, "typ": "JWT"},
        )

        # --- 6. Record the issued token (replay prevention + audit) ---
        await record_issued_token(
            db,
            {
                "jti": str(jti),
                "mandate_id": str(req.mandate_id),
                "agent_id": req.agent_id,
                "action_hash": action_hash,
                "scope_digest": scope_digest,
                "audience": req.audience,
                "issued_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "key_id": key_id,
            },
        )
        await db.commit()

        return json.dumps({
            "token": token,
            "jti": str(jti),
            "expires_at": expires_at.isoformat(),
            "key_id": key_id,
        })

    except Exception as exc:
        return json.dumps({"denied": True, "reason": f"internal_error: {exc}"})
    finally:
        if db is not None:
            await db.close()
