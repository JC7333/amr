"""AMR tool: create_mandate - Register a new legal agent mandate."""

import json
import uuid
from datetime import UTC, datetime, timedelta

import aiosqlite
from pydantic import ValidationError

from amr.config import settings
from amr.crypto.chain import compute_hash
from amr.db.engine import get_db, get_last_mandate_hash, init_db
from amr.delegation import load_ancestors
from amr.models.mandate import LegalBasis, MandateCreate
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
    )


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
) -> str:
    """Create and register a new legal mandate authorizing an AI agent
    to act on behalf of a principal.

    A mandate defines the legal basis, scope, and duration of an agent's authorization.
    Each mandate is cryptographically linked to the previous one (SHA-256 chain).

    The optional structured perimeter (allowed_actions, forbidden_actions,
    delegation_allowed, max_amount) is enforced by issue_action_token: an action
    outside it gets no token. Without it, the mandate is a free-text scope only.

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

    Returns:
        JSON string with keys: status, mandate_id, principal_id, agent_id,
        scope, perimeter, parent_mandate_id, expires_at, chain_hash.
        On error: {"error": "...", "code": "..."} (code present for perimeter
        and delegation errors).
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

        now = datetime.now(UTC)
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
               perimeter_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                "expires_at": expires_at.isoformat(),
                "chain_hash": chain_hash,
            }
        )

    except PerimeterError as exc:
        return _error(exc.code, exc.message)

    except Exception as exc:
        return json.dumps({"error": str(exc)})

    finally:
        if db is not None:
            await db.close()
