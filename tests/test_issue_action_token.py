"""Tests for the issue_action_token tool — structural hard-stop enforcement."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization

from amr.crypto.signing import (
    ensure_signing_key_exists,
    generate_signing_key,
    load_public_key,
)
from amr.tools.issue_action_token import _canonical_action_hash, issue_action_token
from tests._helpers import insert_mandate_directly


@pytest.fixture(autouse=True)
def isolated_signing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide isolated signing key paths per test."""
    priv = tmp_path / "test_key.pem"
    pub = tmp_path / "test_key.pub"
    monkeypatch.setattr("amr.config.settings.signing_key_path", priv)
    monkeypatch.setattr("amr.config.settings.public_key_path", pub)
    generate_signing_key(priv, pub)


def _public_key_pem() -> bytes:
    pub = load_public_key()
    return pub.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


async def test_happy_path_issues_valid_token(temp_db: Path) -> None:
    import jwt as pyjwt

    mandate_id = str(uuid4())
    await insert_mandate_directly(
        temp_db,
        mandate_id,
        agent_id="happy-agent",
        scope="test scope",
    )

    result_json = await issue_action_token(
        mandate_id=mandate_id,
        agent_id="happy-agent",
        action="do the thing",
        audience="runtime://platform-a",
    )
    result = json.loads(result_json)
    assert "token" in result, f"Expected token in result: {result}"

    decoded = pyjwt.decode(
        result["token"],
        _public_key_pem(),
        algorithms=["EdDSA"],
        audience="runtime://platform-a",
    )
    assert decoded["iss"] == "amr://localhost"
    assert decoded["sub"] == "happy-agent"
    assert decoded["aud"] == "runtime://platform-a"
    assert "iat" in decoded
    assert "nbf" in decoded
    assert "exp" in decoded
    assert "jti" in decoded
    assert decoded["amr_mandate_id"] == mandate_id
    assert "amr_action_hash" in decoded
    assert "amr_scope_digest" in decoded


async def test_mandate_not_found_is_denied(temp_db: Path) -> None:
    result = json.loads(await issue_action_token(
        mandate_id=str(uuid4()),
        agent_id="any-agent",
        action="do something",
        audience="runtime://x",
    ))
    assert result.get("denied") is True
    assert result.get("reason") == "mandate_not_found"


async def test_agent_mismatch_is_denied(temp_db: Path) -> None:
    mandate_id = str(uuid4())
    await insert_mandate_directly(temp_db, mandate_id, agent_id="real-agent")

    result = json.loads(await issue_action_token(
        mandate_id=mandate_id,
        agent_id="wrong-agent",
        action="do something",
        audience="runtime://x",
    ))
    assert result.get("denied") is True
    assert result.get("reason") == "agent_mismatch"


async def test_expired_mandate_is_denied(temp_db: Path) -> None:
    mandate_id = str(uuid4())
    await insert_mandate_directly(
        temp_db, mandate_id, agent_id="expired-agent", hours_until_expiry=-1.0
    )

    result = json.loads(await issue_action_token(
        mandate_id=mandate_id,
        agent_id="expired-agent",
        action="do something",
        audience="runtime://x",
    ))
    assert result.get("denied") is True
    assert result.get("reason") == "mandate_expired"


async def test_revoked_mandate_is_denied(temp_db: Path) -> None:
    mandate_id = str(uuid4())
    await insert_mandate_directly(
        temp_db, mandate_id, agent_id="revoked-agent", status="revoked"
    )

    result = json.loads(await issue_action_token(
        mandate_id=mandate_id,
        agent_id="revoked-agent",
        action="do something",
        audience="runtime://x",
    ))
    assert result.get("denied") is True
    assert result.get("reason") == "mandate_status_revoked"


async def test_replay_is_denied_when_active_token_exists(temp_db: Path) -> None:
    mandate_id = str(uuid4())
    await insert_mandate_directly(temp_db, mandate_id, agent_id="replay-agent")

    # First issuance — should succeed
    result_a = json.loads(await issue_action_token(
        mandate_id=mandate_id,
        agent_id="replay-agent",
        action="same action",
        audience="runtime://x",
    ))
    assert "token" in result_a, f"First issuance should succeed: {result_a}"

    # Second issuance — same mandate + same action → replay denied
    result_b = json.loads(await issue_action_token(
        mandate_id=mandate_id,
        agent_id="replay-agent",
        action="same action",
        audience="runtime://x",
    ))
    assert result_b.get("denied") is True
    assert result_b.get("reason") == "replay_detected_active_token_exists"


async def test_replay_allowed_after_previous_token_expired(temp_db: Path) -> None:
    mandate_id = str(uuid4())
    await insert_mandate_directly(temp_db, mandate_id, agent_id="replay-expiry-agent")

    # Issue token A with very short lifetime
    result_a = json.loads(await issue_action_token(
        mandate_id=mandate_id,
        agent_id="replay-expiry-agent",
        action="short-lived action",
        audience="runtime://x",
        lifetime_override_seconds=1,
    ))
    assert "token" in result_a, f"First issuance should succeed: {result_a}"

    # Wait for expiry
    await asyncio.sleep(2)

    # Issue token B for same action — should now be allowed
    result_b = json.loads(await issue_action_token(
        mandate_id=mandate_id,
        agent_id="replay-expiry-agent",
        action="short-lived action",
        audience="runtime://x",
    ))
    assert "token" in result_b, f"Re-issuance after expiry should succeed: {result_b}"


async def test_invalid_mandate_id_format_is_denied(temp_db: Path) -> None:
    result = json.loads(await issue_action_token(
        mandate_id="not-a-uuid",
        agent_id="some-agent",
        action="do something",
        audience="runtime://x",
    ))
    assert result.get("denied") is True
    assert result.get("reason", "").startswith("invalid_input")


async def test_invalid_action_metadata_json_is_denied(temp_db: Path) -> None:
    result = json.loads(await issue_action_token(
        mandate_id=str(uuid4()),
        agent_id="some-agent",
        action="do something",
        audience="runtime://x",
        action_metadata_json="not json",
    ))
    assert result.get("denied") is True
    assert result.get("reason", "").startswith("invalid_input")


def test_action_hash_is_deterministic() -> None:
    args = ("my action", "runtime://x", {"key": "value"})
    hashes = [_canonical_action_hash(*args) for _ in range(10)]
    assert len(set(hashes)) == 1, "Hash must be identical across calls"


async def test_two_different_actions_produce_different_tokens(temp_db: Path) -> None:
    mandate_id = str(uuid4())
    await insert_mandate_directly(temp_db, mandate_id, agent_id="diff-agent")

    result_x = json.loads(await issue_action_token(
        mandate_id=mandate_id,
        agent_id="diff-agent",
        action="action X",
        audience="runtime://x",
    ))
    result_y = json.loads(await issue_action_token(
        mandate_id=mandate_id,
        agent_id="diff-agent",
        action="action Y",
        audience="runtime://x",
    ))

    assert "token" in result_x
    assert "token" in result_y

    hash_x = _canonical_action_hash("action X", "runtime://x", {})
    hash_y = _canonical_action_hash("action Y", "runtime://x", {})
    assert hash_x != hash_y


async def test_token_signature_verifies_with_public_key(temp_db: Path) -> None:
    import jwt as pyjwt

    mandate_id = str(uuid4())
    await insert_mandate_directly(temp_db, mandate_id, agent_id="sig-agent")

    result = json.loads(await issue_action_token(
        mandate_id=mandate_id,
        agent_id="sig-agent",
        action="verify this",
        audience="runtime://verify",
    ))
    assert "token" in result

    # Should not raise
    pyjwt.decode(
        result["token"],
        _public_key_pem(),
        algorithms=["EdDSA"],
        audience="runtime://verify",
    )


async def test_audience_claim_matches_input(temp_db: Path) -> None:
    import jwt as pyjwt

    mandate_id = str(uuid4())
    await insert_mandate_directly(temp_db, mandate_id, agent_id="aud-agent")

    result = json.loads(await issue_action_token(
        mandate_id=mandate_id,
        agent_id="aud-agent",
        action="some action",
        audience="runtime://platform-x",
    ))
    assert "token" in result

    decoded = pyjwt.decode(
        result["token"],
        _public_key_pem(),
        algorithms=["EdDSA"],
        audience="runtime://platform-x",
    )
    assert decoded["aud"] == "runtime://platform-x"
