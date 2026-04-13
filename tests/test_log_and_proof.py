"""Tests for the log_action and get_proof tools."""

import json
import uuid

from amr.tools.create_mandate import create_mandate
from amr.tools.get_proof import get_proof
from amr.tools.log_action import log_action

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_LEGAL = {
    "legal_basis_regulation": "EU AI Act",
    "legal_basis_article": "Art.26(1)(a)",
    "legal_basis_jurisdiction": "EU",
}


async def _create_mandate(agent_id: str = "agent:korvex") -> str:
    """Create a mandate and return its mandate_id."""
    raw = await create_mandate(
        principal_id="user:audric",
        agent_id=agent_id,
        scope="Compare and recommend financial products",
        duration_hours=24.0,
        **_BASE_LEGAL,
    )
    return json.loads(raw)["mandate_id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_log_action_basic():
    """Logging an action under a valid mandate must return status='logged' with a chain_hash."""
    mandate_id = await _create_mandate()

    result = json.loads(
        await log_action(
            mandate_id=mandate_id,
            action="Generated investment recommendation for Product X",
            evidence="email:msg_abc123",
            result="Delivered",
        )
    )

    assert result["status"] == "logged"
    assert result["mandate_id"] == mandate_id
    assert "chain_hash" in result
    assert len(result["chain_hash"]) == 64


async def test_log_action_invalid_mandate():
    """Logging an action under a non-existent mandate_id must return an error."""
    fake_id = str(uuid.uuid4())

    result = json.loads(await log_action(mandate_id=fake_id, action="test action"))

    assert "error" in result


async def test_log_action_chain_integrity():
    """Two successive actions under the same mandate must have different chain_hashes."""
    mandate_id = await _create_mandate()

    first = json.loads(await log_action(mandate_id=mandate_id, action="First action"))
    second = json.loads(await log_action(mandate_id=mandate_id, action="Second action"))

    assert first["status"] == "logged"
    assert second["status"] == "logged"
    assert first["chain_hash"] != second["chain_hash"]


async def test_get_proof_complete():
    """A Proof Pack for a mandate with 2 actions must report chain_integrity valid
    and total_actions=2.
    """
    mandate_id = await _create_mandate()

    await log_action(mandate_id=mandate_id, action="First logged action")
    await log_action(mandate_id=mandate_id, action="Second logged action")

    proof = json.loads(await get_proof(mandate_id=mandate_id))

    assert "error" not in proof
    assert proof["mandate"]["id"] == mandate_id
    assert proof["chain_integrity"]["actions_chain_valid"] is True
    assert proof["chain_integrity"]["total_actions"] == 2


async def test_get_proof_nonexistent():
    """Requesting a Proof Pack for a non-existent mandate_id must return an error."""
    fake_id = str(uuid.uuid4())

    result = json.loads(await get_proof(mandate_id=fake_id))

    assert "error" in result
