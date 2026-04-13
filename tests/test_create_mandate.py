"""Tests for the create_mandate tool."""

import json

import pytest
from pydantic import ValidationError

from amr.models.mandate import LegalBasis, MandateCreate
from amr.tools.create_mandate import create_mandate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LEGAL_KWARGS = {
    "legal_basis_regulation": "EU AI Act",
    "legal_basis_article": "Art.26(1)(a)",
    "legal_basis_jurisdiction": "EU",
}


async def _make_mandate(**overrides) -> dict:
    """Create a mandate with sensible defaults and return the parsed JSON."""
    kwargs = {
        "principal_id": "user:audric",
        "agent_id": "agent:korvex-advisor-v1",
        "scope": "Compare and recommend financial products",
        "duration_hours": 24.0,
        **_LEGAL_KWARGS,
        **overrides,
    }
    raw = await create_mandate(**kwargs)
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_create_mandate_basic():
    """A well-formed mandate must return status='created' and a 64-char chain_hash."""
    result = await _make_mandate()

    assert result["status"] == "created"
    assert "mandate_id" in result
    assert len(result["chain_hash"]) == 64  # SHA-256 hex digest


async def test_create_mandate_with_metadata():
    """A mandate created with a metadata dict must return status='created'."""
    result = await _make_mandate(
        metadata={"client_ref": "CL-2026-001", "advisor_code": "ADV42"}
    )

    assert result["status"] == "created"
    assert "mandate_id" in result


async def test_create_mandate_chain_integrity():
    """Two successive mandates must have different chain_hashes (each links to the previous)."""
    first = await _make_mandate(agent_id="agent:alpha")
    second = await _make_mandate(agent_id="agent:beta")

    assert first["status"] == "created"
    assert second["status"] == "created"
    assert first["chain_hash"] != second["chain_hash"]


def test_create_mandate_invalid_duration():
    """duration_hours > 8760 (one year) must raise a Pydantic ValidationError."""
    with pytest.raises(ValidationError):
        MandateCreate(
            principal_id="user:audric",
            agent_id="agent:test",
            scope="test scope",
            legal_basis=LegalBasis(regulation="EU AI Act", article="Art.26"),
            duration_hours=9000.0,  # exceeds max of 8760
        )


def test_create_mandate_empty_principal():
    """An empty principal_id must raise a Pydantic ValidationError (min_length=1)."""
    with pytest.raises(ValidationError):
        MandateCreate(
            principal_id="",  # violates min_length=1
            agent_id="agent:test",
            scope="test scope",
            legal_basis=LegalBasis(regulation="EU AI Act", article="Art.26"),
            duration_hours=24.0,
        )
