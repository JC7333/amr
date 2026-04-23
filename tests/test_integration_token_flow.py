"""End-to-end integration test for the token issuance flow.

Scenario: a principal creates a mandate for an agent, the agent requests
tokens for various actions, some are granted, some are denied.
"""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization

from amr.crypto.signing import ensure_signing_key_exists, generate_signing_key, load_public_key
from amr.tools.create_mandate import create_mandate
from amr.tools.issue_action_token import issue_action_token


@pytest.fixture(autouse=True)
def isolated_signing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide isolated Ed25519 key paths for each integration test."""
    priv = tmp_path / "integ_key.pem"
    pub = tmp_path / "integ_key.pub"
    monkeypatch.setattr("amr.config.settings.signing_key_path", priv)
    monkeypatch.setattr("amr.config.settings.public_key_path", pub)
    generate_signing_key(priv, pub)


@pytest.mark.asyncio
async def test_end_to_end_token_flow(temp_db: Path) -> None:
    """Full flow: create mandate → issue token → verify → replay → expire → deny."""

    ensure_signing_key_exists()
    public_key = load_public_key()
    public_key_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    # 1. Create a valid mandate
    # NOTE: signature of create_mandate is exact — do not rename params.
    # Verified against src/amr/tools/create_mandate.py at 2026-04-22.
    create_result_json = await create_mandate(
        principal_id="hospital-paris-01",
        agent_id="claude-clinical-v1",
        scope="summarize patient records for physician review",
        legal_basis_regulation="EU AI Act",
        legal_basis_article="Art. 26",
        duration_hours=24.0,
        legal_basis_jurisdiction="EU",
    )
    create_result = json.loads(create_result_json)
    assert "mandate_id" in create_result, (
        f"create_mandate returned unexpected result: {create_result_json}"
    )
    mandate_id = create_result["mandate_id"]

    # 2. Issue a token for a valid action
    issue_result_1 = json.loads(await issue_action_token(
        mandate_id=mandate_id,
        agent_id="claude-clinical-v1",
        action="summarize patient 12345",
        audience="clinical-runtime://hospital-paris-01",
        lifetime_override_seconds=2,  # short to test expiry quickly
    ))
    assert "token" in issue_result_1, f"token issuance failed: {issue_result_1}"
    token_1 = issue_result_1["token"]

    # 3. Verify the token offline with the public key
    decoded = jwt.decode(
        token_1,
        public_key_pem,
        algorithms=["EdDSA"],
        audience="clinical-runtime://hospital-paris-01",
    )
    assert decoded["sub"] == "claude-clinical-v1"
    assert decoded["amr_mandate_id"] == mandate_id
    assert "amr_action_hash" in decoded

    # 4. Replay attempt on same action → denied
    issue_result_2 = json.loads(await issue_action_token(
        mandate_id=mandate_id,
        agent_id="claude-clinical-v1",
        action="summarize patient 12345",
        audience="clinical-runtime://hospital-paris-01",
    ))
    assert issue_result_2.get("denied") is True
    assert issue_result_2.get("reason") == "replay_detected_active_token_exists"

    # 5. Different action → allowed
    issue_result_3 = json.loads(await issue_action_token(
        mandate_id=mandate_id,
        agent_id="claude-clinical-v1",
        action="summarize patient 67890",
        audience="clinical-runtime://hospital-paris-01",
    ))
    assert "token" in issue_result_3, f"different-action issuance failed: {issue_result_3}"

    # 6. Wait for token_1 to expire, then re-issue for the same action → allowed
    await asyncio.sleep(3)
    issue_result_4 = json.loads(await issue_action_token(
        mandate_id=mandate_id,
        agent_id="claude-clinical-v1",
        action="summarize patient 12345",
        audience="clinical-runtime://hospital-paris-01",
    ))
    assert "token" in issue_result_4, (
        f"re-issuance after expiry failed: {issue_result_4}"
    )

    # 7. Audience confusion defense: consumer B refuses token for audience A
    # token_1 may have expired at this point (lifetime=2s, sleep=3s), so we
    # disable exp verification to isolate the audience check — the audience
    # mismatch MUST still be raised even when expiry is ignored.
    with pytest.raises(jwt.exceptions.InvalidAudienceError):
        jwt.decode(
            token_1,
            public_key_pem,
            algorithms=["EdDSA"],
            audience="wrong-runtime://other-hospital",
            options={"verify_exp": False},
        )


@pytest.mark.asyncio
async def test_expired_mandate_denies_token(temp_db: Path) -> None:
    """A mandate whose expires_at is in the past cannot issue new tokens.

    Uses insert_mandate_directly to set up an already-expired mandate
    without violating the production append-only invariant on real data.
    """
    from tests._helpers import insert_mandate_directly

    mandate_id = str(uuid4())
    await insert_mandate_directly(
        db_path=temp_db,
        mandate_id=mandate_id,
        agent_id="expired-agent",
        status="active",  # status "active" but expires_at in the past
        hours_until_expiry=-1.0,
    )

    result = json.loads(await issue_action_token(
        mandate_id=mandate_id,
        agent_id="expired-agent",
        action="do something",
        audience="runtime://x",
    ))
    assert result.get("denied") is True
    assert result.get("reason") == "mandate_expired"
