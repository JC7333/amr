"""Tests for the verify_mandate tool."""

import asyncio
import json

from amr.tools.create_mandate import create_mandate
from amr.tools.verify_mandate import verify_mandate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_LEGAL = {
    "legal_basis_regulation": "EU AI Act",
    "legal_basis_article": "Art.26(1)(a)",
    "legal_basis_jurisdiction": "EU",
}


async def _create(agent_id: str, duration_hours: float = 24.0) -> str:
    """Create a mandate and return its mandate_id."""
    raw = await create_mandate(
        principal_id="user:audric",
        agent_id=agent_id,
        scope="Compare and recommend financial products to retail clients",
        duration_hours=duration_hours,
        **_BASE_LEGAL,
    )
    return json.loads(raw)["mandate_id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_verify_existing_mandate():
    """An agent with an active mandate must be authorized and return the correct scope."""
    agent = "agent:korvex-advisor-v1"
    await _create(agent)

    result = json.loads(
        await verify_mandate(agent_id=agent, action="send investment recommendation")
    )

    assert result["authorized"] is True
    assert result["mandate_id"] is not None
    assert "financial products" in result["scope"]


async def test_verify_no_mandate():
    """An agent that has never received a mandate must not be authorized."""
    result = json.loads(
        await verify_mandate(
            agent_id="agent:unknown-no-mandate",
            action="access user portfolio",
        )
    )

    assert result["authorized"] is False
    assert result["mandate_id"] is None


async def test_verify_expired_mandate():
    """A mandate with duration_hours=0.0001 (~0.36 s) must be expired after 1 second."""
    agent = "agent:short-lived"
    await _create(agent, duration_hours=0.0001)

    await asyncio.sleep(1.0)  # wait for the mandate to expire

    result = json.loads(
        await verify_mandate(agent_id=agent, action="any action")
    )

    assert result["authorized"] is False
