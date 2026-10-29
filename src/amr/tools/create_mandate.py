"""AMR tool: create_mandate - Register a new legal agent mandate."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import aiosqlite
from pydantic import ValidationError

from amr.config import settings
from amr.crypto.chain import compute_hash
from amr.crypto.principal import (
    PrincipalSignatureError,
    b64url_encode,
    mandate_payload,
    parse_public_key,
    parse_signature,
    parse_signed_at,
    verify,
)
from amr.db.engine import get_db, get_last_mandate_hash, get_principal_key, init_db
from amr.delegation import load_ancestors
from amr.models.mandate import LegalBasis, MandateCreate
from amr.models.organ_decision import OrganDecisionError, organ_decision_from_metadata
from amr.models.perimeter import Perimeter, PerimeterError


def _error(code: str, message: str) -> str:
    return json.dumps({"error": f"{code}: {message}", "code": code})


def _build_perimeter(
    allowed_actions: list[str] | None,
    forbidden_actions: list[str] | None,
    delegation_allowed: bool,
    max_amount: str | None,
    currency: str,
    amount_actions: list[str] | None,
    period_max_amount: str | None = None,
    period_days: int | None = None,
    risk_classes: list[dict[str, Any]] | None = None,
) -> Perimeter | None:
    """Build the structured perimeter, or None for a legacy free-text mandate.

    Any perimeter argument given explicitly (even an empty list) asks for a perimeter;
    an empty allowed_actions list is then rejected rather than read as "no perimeter".
    """
    if (
        allowed_actions is None
        and forbidden_actions is None
        and amount_actions is None
        and max_amount is None
        and period_max_amount is None
        and period_days is None
        and risk_classes is None
        and not delegation_allowed
    ):
        return None
    if allowed_actions is None:
        raise PerimeterError(
            "perimeter_invalid",
            "allowed_actions is required when a structured perimeter is given",
        )
    return Perimeter(
        allowed_actions=tuple(allowed_actions),
        forbidden_actions=tuple(forbidden_actions or ()),
        delegation_allowed=delegation_allowed,
        max_amount=max_amount,  # type: ignore[arg-type]
        currency=currency,
        amount_actions=tuple(amount_actions or ()),
        period_max_amount=period_max_amount,  # type: ignore[arg-type]
        period_days=period_days,
        risk_classes=tuple(risk_classes or ()),  # type: ignore[arg-type]
    )


def signed_mandate_payload(mandate_data: MandateCreate, signed_at: str) -> bytes:
    """The bytes the principal signs for this mandate request (requested perimeter)."""
    parse_signed_at(signed_at)
    return mandate_payload(
        principal_id=mandate_data.principal_id,
        agent_id=mandate_data.agent_id,
        scope=mandate_data.scope,
        legal_basis=mandate_data.legal_basis.model_dump(),
        duration_hours=mandate_data.duration_hours,
        parent_mandate_id=(
            str(mandate_data.parent_mandate_id)
            if mandate_data.parent_mandate_id is not None
            else None
        ),
        metadata=dict(mandate_data.metadata),
        perimeter=(
            mandate_data.perimeter.canonical() if mandate_data.perimeter is not None else None
        ),
        signed_at=signed_at,
    )


async def _check_principal_signature(
    db: aiosqlite.Connection,
    mandate_data: MandateCreate,
    principal_signature: str | None,
    signed_at: str | None,
    now: datetime,
) -> dict[str, str] | None:
    """Apply the principal signature policy; return the verified signature record or None.

    A principal with a registered key must sign; with require_principal_signature,
    every principal must. Raises PrincipalSignatureError with a stable code.
    """
    key_row = await get_principal_key(db, mandate_data.principal_id)
    if principal_signature is None and signed_at is None:
        if key_row is not None:
            raise PrincipalSignatureError(
                "principal_signature_required",
                "this principal has a registered key: the mandate must carry its signature",
            )
        if settings.require_principal_signature:
            raise PrincipalSignatureError(
                "principal_signature_required",
                "this registry requires every mandate to be signed by its principal",
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
    payload = signed_mandate_payload(mandate_data, signed_at)
    public_key_raw = parse_public_key(key_row["public_key"])
    if not verify(public_key_raw, payload, signature_raw):
        raise PrincipalSignatureError(
            "principal_signature_invalid",
            "the signature does not match this mandate and the principal's registered key",
        )
    signature = b64url_encode(signature_raw)
    cursor = await db.execute(
        "SELECT 1 FROM mandates WHERE principal_signature = ? LIMIT 1", (signature,)
    )
    if await cursor.fetchone() is not None:
        raise PrincipalSignatureError(
            "principal_signature_replayed", "this signature already registered a mandate"
        )
    return {
        "signature": signature,
        "signed_at": signed_at,
        "key_id": key_row["key_id"],
        "payload": payload.decode("utf-8"),
    }


async def _check_parent(
    db: aiosqlite.Connection,
    parent_mandate_id: str,
    principal_id: str,
    perimeter: Perimeter | None,
    expires_at: datetime,
    now: datetime,
) -> Perimeter:
    """Validate a sub-delegation against its parent mandate and the chain above it.

    Returns the child's effective perimeter (parent prohibitions and limits inherited),
    or raises PerimeterError with a stable code.
    """
    ancestors, refusal = await load_ancestors(db, parent_mandate_id, now)
    if refusal is not None:
        raise PerimeterError(
            refusal.reason, f"delegation chain broken at mandate '{refusal.refused_by}'"
        )
    parent = ancestors[0]
    parent_expires = datetime.fromisoformat(parent["expires_at"])
    if parent_expires.tzinfo is None:
        parent_expires = parent_expires.replace(tzinfo=UTC)
    if not parent["perimeter_json"]:
        raise PerimeterError(
            "delegation_not_allowed",
            "parent mandate has no structured perimeter, so it does not allow delegation",
        )
    parent_perimeter = Perimeter.from_json(parent["perimeter_json"])
    if not parent_perimeter.delegation_allowed:
        raise PerimeterError("delegation_not_allowed", "parent mandate forbids delegation")
    if principal_id != parent["agent_id"]:
        raise PerimeterError(
            "delegator_mismatch",
            "the principal of a sub-mandate must be the agent of the parent mandate",
        )
    if perimeter is None:
        raise PerimeterError(
            "sub_mandate_requires_perimeter",
            "a sub-mandate must declare allowed_actions within the parent's perimeter",
        )
    if expires_at > parent_expires:
        raise PerimeterError(
            "expires_after_parent", "a sub-mandate cannot outlive its parent mandate"
        )
    return perimeter.narrowed_by(parent_perimeter)


async def create_mandate(
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
    principal_signature: str | None = None,
    signed_at: str | None = None,
    period_max_amount: str | None = None,
    period_days: int | None = None,
    risk_classes: list[dict[str, Any]] | None = None,
) -> str:
    """Create and register a new legal mandate authorizing an AI agent
    to act on behalf of a principal.

    A mandate defines the legal basis, scope, and duration of an agent's authorization.
    Each mandate is cryptographically linked to the previous one (SHA-256 chain).

    The optional structured perimeter (allowed_actions, forbidden_actions,
    delegation_allowed, max_amount, period_max_amount, risk_classes) is enforced by
    issue_action_token: an action outside it gets no token. Without it, the mandate is
    a free-text scope only.

    The principal can sign the mandate with its own Ed25519 key (registered once with
    register_principal_key): build the exact bytes with prepare_mandate_signature, sign
    them, and pass principal_signature and signed_at. A principal with a registered key
    must always sign; the signature is sealed into chain_hash and kept in the Proof Pack.

    When a body (committee, board) authorized the agent, its decision goes in metadata
    under the reserved key "organ_decision": body, title, decided_on (YYYY-MM-DD, not in
    the future, judged on the registry's UTC date), optional reference, and
    authorized_personnel (the persons or roles the decision designates), as the compact
    JSON of OrganDecision.to_metadata_value(). It needs allowed_actions without patterns
    and is refused on a sub-mandate. It is validated, sealed into chain_hash, and shown
    by verify_mandate and get_proof.

    Args:
        principal_id: Unique identifier of the principal granting the mandate.
                      Example: "user:audric" or "org:acme-corp"
        agent_id: Unique identifier of the agent receiving authorization.
                  Example: "agent:korvex-advisor-v1"
        scope: Human-readable description of what the agent is authorized to do.
               Example: "Compare and recommend financial products to retail clients"
        legal_basis_regulation: Name of the regulation or contract granting authority.
                                Example: "EU AI Act Art.26" or "Service Agreement 2026"
        legal_basis_article: Specific article, clause, or reference number.
                             Example: "Art.26(1)(a)" or "Mandat conseil 2026-042"
        duration_hours: Duration of the mandate in hours. Max 8760 (1 year).
                        Example: 720 (30 days), 168 (1 week), 24 (1 day)
        legal_basis_jurisdiction: Jurisdiction code. Default "EU".
                                  Example: "EU", "FR", "US"
        parent_mandate_id: UUID of a parent mandate for sub-delegation chains. The parent
                           (and every mandate above it) must be active and unexpired; the
                           parent must allow delegation and have this mandate's
                           principal_id as its agent_id; the sub-mandate must declare
                           allowed_actions within the parent's, and cannot outlive it.
                           Example: "550e8400-e29b-41d4-a716-446655440000"
        metadata: Optional dict of string key-value pairs for custom annotations.
                  Example: {"client_ref": "CL-2026-001", "advisor_code": "ADV42"}
                  The key "organ_decision" is reserved (see above).
        allowed_actions: Action types the agent may request. Dotted lowercase identifiers,
                         "domain.*" prefix patterns, or "*".
                         Example: ["invoice.read", "invoice.pay"]
        forbidden_actions: Action types the agent may never request (wins over allowed).
                           Example: ["agent.create", "invoice.delete"]
        delegation_allowed: Whether the agent may grant sub-mandates to other agents.
                            Default False.
        max_amount: Optional ceiling per action, as a plain decimal string with a dot.
                    Example: "500" or "120.50"
        currency: ISO 4217 code of max_amount. Default "EUR".
        amount_actions: Action types that move money: they must carry "amount" and
                        "currency" metadata, the amount at or below max_amount. A pattern
                        also reaches its sub-types. Empty means every action.
                        Example: ["invoice.pay"]
        principal_signature: Base64url Ed25519 signature by the principal of the payload
                             returned by prepare_mandate_signature for these same
                             arguments and signed_at. Required if the principal has a
                             registered key.
        signed_at: The ISO 8601 timestamp (with timezone) placed in the signed payload.
                   Must be within 15 minutes of the registry clock by default.
                   Example: "2026-10-18T20:30:00+00:00"
        period_max_amount: Optional cumulative ceiling, same currency and same
                           amount_actions as max_amount: the total of the amounts of the
                           tokens issued under this mandate and every sub-mandate below
                           it, over the last period_days days, stays at or below it.
                           Plain decimal string. Example: "2000"
        period_days: Length of the rolling window of period_max_amount, in whole days
                     (1 to 366). Required with period_max_amount. Example: 30
        risk_classes: Optional risk classes bounding the lifetime of action tokens:
                      each {"name", "actions", "max_token_seconds"}. A class reaches its
                      action patterns and their sub-types; a token for an action it
                      reaches lives at most max_token_seconds (1 to 86400), the
                      shortest class winning, in this mandate and every sub-mandate
                      below it. A class may add "registry_check": true: its tokens
                      then carry amr_registry_check, and the receiver re-checks the
                      registry with check_action_token when it acts. Example:
                      [{"name": "irreversible", "actions": ["invoice.pay"],
                      "max_token_seconds": 30, "registry_check": true}]

    Returns:
        JSON string with keys: status, mandate_id, principal_id, agent_id,
        scope, perimeter, parent_mandate_id, principal_signature, expires_at,
        organ_decision, chain_hash. principal_signature is {key_id, signed_at} or
        null; organ_decision is the recorded decision or null.
        On error: {"error": "...", "code": "..."} (code present for perimeter,
        delegation, organ decision and principal signature errors).
    """
    db = None
    try:
        # Validate inputs via Pydantic
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
                period_max_amount,
                period_days,
                risk_classes,
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

        organ_decision = organ_decision_from_metadata(mandate_data.metadata)
        if organ_decision is not None:
            # A body decides for the root principal only; an agent cannot declare one for
            # its own sub-agent. And it authorizes a closed list of predefined actions.
            if mandate_data.parent_mandate_id is not None:
                return _error(
                    "organ_decision_on_sub_mandate",
                    "an organ decision can only be recorded on a root mandate",
                )
            if perimeter is None or any(a.endswith("*") for a in perimeter.allowed_actions):
                return _error(
                    "organ_decision_needs_closed_list",
                    "an organ decision needs allowed_actions as a closed list, without patterns",
                )

        # Signature inputs are checked for form before any database access.
        if principal_signature is not None:
            parse_signature(principal_signature)
        if signed_at is not None:
            parse_signed_at(signed_at)

        now = datetime.now(UTC)
        if organ_decision is not None and organ_decision.decided_on_date > now.date():
            return _error("organ_decision_invalid", "organ_decision.decided_on is in the future")
        expires_at = now + timedelta(hours=mandate_data.duration_hours)
        mandate_id = str(uuid.uuid4())

        await init_db(settings.db_path)
        db = await get_db(settings.db_path)

        # Canonical UUID form, so the stored link and the lookup always agree.
        parent_id = (
            str(mandate_data.parent_mandate_id)
            if mandate_data.parent_mandate_id is not None
            else None
        )
        signature_record = await _check_principal_signature(
            db, mandate_data, principal_signature, signed_at, now
        )

        if parent_id is not None:
            try:
                perimeter = await _check_parent(
                    db, parent_id, principal_id, perimeter, expires_at, now
                )
            except ValidationError as exc:
                return _error("perimeter_invalid", str(exc))

        previous_hash = await get_last_mandate_hash(db)

        # Build hash payload (everything except the hash itself)
        hash_data = {
            "id": mandate_id,
            "principal_id": principal_id,
            "agent_id": agent_id,
            "scope": scope,
            "legal_basis_regulation": legal_basis_regulation,
            "legal_basis_article": legal_basis_article,
            "legal_basis_jurisdiction": legal_basis_jurisdiction,
            "duration_hours": duration_hours,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "parent_mandate_id": parent_id,
        }
        # The perimeter is sealed into the chain. Free-text mandates keep the exact
        # pre-perimeter payload, so their hashes are unchanged.
        if perimeter is not None:
            hash_data["perimeter"] = perimeter.canonical()
        # Likewise, only signed mandates carry the principal's signature in the chain.
        if signature_record is not None:
            hash_data["principal_signature"] = {
                "signature": signature_record["signature"],
                "signed_at": signature_record["signed_at"],
                "key_id": signature_record["key_id"],
            }
        # And only mandates that record an organ decision carry it in the chain.
        if organ_decision is not None:
            hash_data["organ_decision"] = organ_decision.canonical()
        chain_hash = compute_hash(hash_data, previous_hash)

        legal_basis_json = json.dumps(
            {
                "regulation": legal_basis_regulation,
                "article": legal_basis_article,
                "jurisdiction": legal_basis_jurisdiction,
            },
            sort_keys=True,
        )
        metadata_json = json.dumps(metadata or {}, sort_keys=True)

        await db.execute(
            """
            INSERT INTO mandates
              (id, principal_id, agent_id, scope, legal_basis_json, status,
               created_at, expires_at, parent_mandate_id, metadata_json, chain_hash,
               perimeter_json, principal_signature, principal_signed_at,
               principal_key_id, principal_signed_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mandate_id,
                principal_id,
                agent_id,
                scope,
                legal_basis_json,
                "active",
                now.isoformat(),
                expires_at.isoformat(),
                parent_id,
                metadata_json,
                chain_hash,
                perimeter.to_json() if perimeter is not None else None,
                signature_record["signature"] if signature_record else None,
                signature_record["signed_at"] if signature_record else None,
                signature_record["key_id"] if signature_record else None,
                signature_record["payload"] if signature_record else None,
            ),
        )
        await db.commit()

        return json.dumps(
            {
                "status": "created",
                "mandate_id": mandate_id,
                "principal_id": principal_id,
                "agent_id": agent_id,
                "scope": scope,
                "perimeter": perimeter.canonical() if perimeter is not None else None,
                "parent_mandate_id": parent_id,
                "principal_signature": (
                    {
                        "key_id": signature_record["key_id"],
                        "signed_at": signature_record["signed_at"],
                    }
                    if signature_record
                    else None
                ),
                "organ_decision": (
                    organ_decision.canonical() if organ_decision is not None else None
                ),
                "expires_at": expires_at.isoformat(),
                "chain_hash": chain_hash,
            }
        )

    except PerimeterError as exc:
        return _error(exc.code, exc.message)

    except PrincipalSignatureError as exc:
        return _error(exc.code, exc.message)

    except OrganDecisionError as exc:
        return _error(exc.code, exc.message)

    except aiosqlite.IntegrityError as exc:
        if "principal_signature" in str(exc):
            return _error(
                "principal_signature_replayed", "this signature already registered a mandate"
            )
        return json.dumps({"error": str(exc)})

    except Exception as exc:
        return json.dumps({"error": str(exc)})

    finally:
        if db is not None:
            await db.close()
