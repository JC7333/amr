"""Tests for AMR token Pydantic models."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from amr.models.token import IssueTokenRequest, TokenIssueResult


def test_issue_token_request_valid() -> None:
    req = IssueTokenRequest(
        mandate_id=uuid4(),
        agent_id="test-agent",
        action="do something useful",
        audience="runtime://platform-x",
    )
    assert req.agent_id == "test-agent"
    assert req.action_metadata == {}


def test_issue_token_request_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        IssueTokenRequest(
            mandate_id=uuid4(),
            agent_id="test-agent",
            action="do something",
            audience="runtime://x",
            foo="bar",  # type: ignore[call-arg]
        )


def test_issue_token_request_rejects_invalid_uuid() -> None:
    with pytest.raises(ValidationError):
        IssueTokenRequest(
            mandate_id="not-a-uuid",  # type: ignore[arg-type]
            agent_id="test-agent",
            action="do something",
            audience="runtime://x",
        )


def test_issue_token_request_rejects_empty_agent_id() -> None:
    with pytest.raises(ValidationError):
        IssueTokenRequest(
            mandate_id=uuid4(),
            agent_id="",
            action="do something",
            audience="runtime://x",
        )


def test_issue_token_request_rejects_too_long_action() -> None:
    with pytest.raises(ValidationError):
        IssueTokenRequest(
            mandate_id=uuid4(),
            agent_id="test-agent",
            action="x" * 2001,
            audience="runtime://x",
        )


def test_token_issue_result_roundtrip() -> None:
    from datetime import UTC, datetime

    original = TokenIssueResult(
        token="header.payload.signature",
        jti=uuid4(),
        expires_at=datetime.now(UTC),
        key_id="abcd1234ef567890",
    )
    serialized = original.model_dump_json()
    loaded = TokenIssueResult.model_validate(json.loads(serialized))
    assert loaded.token == original.token
    assert loaded.jti == original.jti
    assert loaded.key_id == original.key_id
