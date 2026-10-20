"""Delegation chain checks shared by mandate creation, verification and token issuance.

A sub-mandate is only as valid as every mandate above it: if any ancestor is missing,
not active, or expired, the whole branch below it is cut.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

import aiosqlite

# Cycles are impossible by construction (a parent must exist before its child);
# this bounds the walk and the length of delegation chains anyway.
MAX_DELEGATION_DEPTH = 16


@dataclass(frozen=True)
class ChainRefusal:
    """Why a delegation chain is broken, and which mandate broke it."""

    reason: str
    refused_by: str | None


def is_expired(expires_at: str, now: datetime) -> bool:
    """True if the stored ISO expiry is at or before ``now`` (naive values read as UTC)."""
    moment = datetime.fromisoformat(expires_at)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment <= now


async def load_ancestors(
    db: aiosqlite.Connection, parent_id: str | None, now: datetime
) -> tuple[list[aiosqlite.Row], ChainRefusal | None]:
    """Walk up the chain from ``parent_id``, nearest ancestor first.

    Returns the ancestors read so far and, if the chain is broken, the refusal:
    ``parent_mandate_not_found``, ``parent_mandate_<status>``, ``parent_mandate_expired``
    or ``delegation_chain_too_deep``.
    """
    ancestors: list[aiosqlite.Row] = []
    while parent_id:
        if len(ancestors) >= MAX_DELEGATION_DEPTH:
            return ancestors, ChainRefusal("delegation_chain_too_deep", None)
        cursor = await db.execute(
            """
            SELECT id, principal_id, agent_id, status, expires_at, parent_mandate_id,
                   perimeter_json
            FROM mandates
            WHERE id = ?
            """,
            (parent_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return ancestors, ChainRefusal("parent_mandate_not_found", parent_id)
        if row["status"] != "active":
            return ancestors, ChainRefusal(f"parent_mandate_{row['status']}", row["id"])
        if is_expired(row["expires_at"], now):
            return ancestors, ChainRefusal("parent_mandate_expired", row["id"])
        ancestors.append(row)
        parent_id = row["parent_mandate_id"]
    return ancestors, None
