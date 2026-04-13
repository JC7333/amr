"""AMR tool: create_mandate - Register a new legal agent mandate."""

import json
from datetime import UTC, datetime, timedelta

from amr.config import settings
from amr.crypto.chain import compute_hash
from amr.db.engine import get_db, get_last_mandate_hash, init_db
from amr.models.mandate import LegalBasis, MandateCreate


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
) -> str:
    """Create and register a new legal mandate authorizing an AI agent
    to act on behalf of a principal.

    A mandate defines the legal basis, scope, and duration of an agent's authorization.
    Each mandate is cryptographically linked to the previous one (SHA-256 chain).

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
        parent_mandate_id: UUID of a parent mandate for sub-delegation chains.
                           Example: "550e8400-e29b-41d4-a716-446655440000"
        metadata: Optional dict of string key-value pairs for custom annotations.
                  Example: {"client_ref": "CL-2026-001", "advisor_code": "ADV42"}

    Returns:
        JSON string with keys: status, mandate_id, principal_id, agent_id,
        scope, expires_at, chain_hash. On error: {"error": "..."}.
    """
    db = None
    try:
        # Validate inputs via Pydantic
        legal_basis = LegalBasis(
            regulation=legal_basis_regulation,
            article=legal_basis_article,
            jurisdiction=legal_basis_jurisdiction,
        )
        mandate_data = MandateCreate(
            principal_id=principal_id,
            agent_id=agent_id,
            scope=scope,
            legal_basis=legal_basis,
            duration_hours=duration_hours,
            parent_mandate_id=parent_mandate_id,  # type: ignore[arg-type]
            metadata=metadata or {},
        )

        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=mandate_data.duration_hours)
        mandate_id = str(__import__("uuid").uuid4())

        await init_db(settings.db_path)
        db = await get_db(settings.db_path)

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
            "parent_mandate_id": str(parent_mandate_id) if parent_mandate_id else None,
        }
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
               created_at, expires_at, parent_mandate_id, metadata_json, chain_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                str(parent_mandate_id) if parent_mandate_id else None,
                metadata_json,
                chain_hash,
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
                "expires_at": expires_at.isoformat(),
                "chain_hash": chain_hash,
            }
        )

    except Exception as exc:
        return json.dumps({"error": str(exc)})

    finally:
        if db is not None:
            await db.close()
