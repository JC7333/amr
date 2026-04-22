"""Test helpers for AMR — direct DB manipulation for isolated test setup."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiosqlite

from amr.db.engine import init_db


async def insert_mandate_directly(
    db_path: Path,
    mandate_id: str,
    principal_id: str = "test-principal",
    agent_id: str = "test-agent",
    scope: str = "default scope",
    status: str = "active",
    hours_until_expiry: float = 24.0,
    chain_hash: str = "0" * 64,
) -> None:
    """Insert a mandate directly via SQL for isolated test setup.

    Allows negative hours_until_expiry to create already-expired mandates,
    and allows status="revoked" / "expired" to test denial paths.

    IMPORTANT: this bypasses the production chain_hash invariant. The default
    chain_hash is a placeholder ("0" * 64). Tests that combine this helper
    with real chain-dependent operations (e.g. log_action after) may produce
    broken chains — which is fine for isolated tests of issue_action_token,
    since that tool does not re-verify the chain. If a test needs a valid
    chain, use create_mandate() instead.
    """
    await init_db(db_path)
    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=hours_until_expiry)

    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute(
            """
            INSERT INTO mandates (
                id, principal_id, agent_id, scope, legal_basis_json,
                status, created_at, expires_at, metadata_json, chain_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mandate_id,
                principal_id,
                agent_id,
                scope,
                '{"regulation":"test","article":"test","jurisdiction":"EU"}',
                status,
                now.isoformat(),
                expires_at.isoformat(),
                "{}",
                chain_hash,
            ),
        )
        await db.commit()
