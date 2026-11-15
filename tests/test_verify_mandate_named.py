"""verify_mandate(mandate_id=...) answers about one named mandate.

Found in a real test on 09/11/2026 (package 0.1.1): after revoke_mandate, verify_mandate
still answered authorized=true for the agent when it held another active mandate, so a
receiver could not ask "is the mandate this agent shows me still in force?". Without
mandate_id the answer is unchanged; with it, only that mandate counts.
"""

import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from amr.crypto.signing import generate_signing_key
from amr.tools.create_mandate import create_mandate
from amr.tools.revoke_mandate import revoke_mandate
from amr.tools.verify_mandate import verify_mandate

AGENT = "agent:billing"
OTHER = "agent:other"
HELPER = "agent:helper"

ROOT = {
    "principal_id": "org:clinic",
    "agent_id": AGENT,
    "scope": "Handle supplier invoices",
    "legal_basis_regulation": "Mandate contract",
    "legal_basis_article": "Clause 1",
    "duration_hours": 24.0,
    "allowed_actions": ["invoice.*"],
    "delegation_allowed": True,
}

KEYS = {
    "authorized", "mandate_id", "reason", "scope", "perimeter", "parent_mandate_id",
    "organ_decision", "expires_at",
}


@pytest.fixture(autouse=True)
def isolated_signing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    priv = tmp_path / "test_key.pem"
    pub = tmp_path / "test_key.pub"
    monkeypatch.setattr("amr.config.settings.signing_key_path", priv)
    monkeypatch.setattr("amr.config.settings.public_key_path", pub)
    generate_signing_key(priv, pub)


async def _create(**overrides: object) -> str:
    result = json.loads(await create_mandate(**{**ROOT, **overrides}))
    assert result.get("status") == "created", result
    return result["mandate_id"]


async def _verify(agent_id: str = AGENT, mandate_id: str = "") -> dict:
    result = json.loads(await verify_mandate(agent_id, "pay invoice", mandate_id=mandate_id))
    assert set(result) == KEYS, result
    return result


async def _revoke(mandate_id: str) -> None:
    result = json.loads(await revoke_mandate(mandate_id, "test"))
    assert result.get("status") == "revoked", result


async def test_named_active_mandate_is_authorized() -> None:
    mid = await _create()
    result = await _verify(mandate_id=mid)
    assert result["authorized"] is True
    assert result["mandate_id"] == mid
    assert result["reason"] == "Active mandate found"
    assert result["scope"] == "Handle supplier invoices"
    assert result["perimeter"] is not None


async def test_named_mandate_picks_that_one_not_the_newest() -> None:
    older = await _create(scope="Older mandate")
    await _create(scope="Newer mandate")
    result = await _verify(mandate_id=older)
    assert result["authorized"] is True
    assert result["mandate_id"] == older
    assert result["scope"] == "Older mandate"


async def test_revoked_named_mandate_refused_even_with_another_active() -> None:
    revoked = await _create(scope="Revoked one")
    kept = await _create(scope="Kept one")
    await _revoke(revoked)

    # Default answer unchanged: the agent still holds an active mandate.
    default = await _verify()
    assert default["authorized"] is True
    assert default["mandate_id"] == kept

    named = await _verify(mandate_id=revoked)
    assert named["authorized"] is False
    assert named["reason"] == "Mandate revoked"
    assert named["mandate_id"] == revoked

    assert (await _verify(mandate_id=kept))["authorized"] is True


async def test_named_mandate_of_another_agent_is_refused_without_detail() -> None:
    foreign = await _create(agent_id=OTHER, scope="Secret scope of another agent")
    await _create()  # AGENT holds its own active mandate
    result = await _verify(mandate_id=foreign)
    assert result["authorized"] is False
    assert result["mandate_id"] is None
    assert result["scope"] == ""
    assert result["perimeter"] is None
    assert result["expires_at"] is None
    assert "Secret" not in json.dumps(result)
    assert "not found for agent" in result["reason"]


async def test_unknown_named_mandate_is_refused() -> None:
    await _create()
    missing = str(uuid.uuid4())
    result = await _verify(mandate_id=missing)
    assert result["authorized"] is False
    assert result["mandate_id"] is None
    assert missing in result["reason"]


async def test_invalid_mandate_id_is_refused_before_any_lookup() -> None:
    await _create()
    result = await _verify(mandate_id="not-a-uuid' OR 1=1 --")
    assert result["authorized"] is False
    assert result["mandate_id"] is None
    assert result["reason"].startswith("Invalid mandate_id format")


async def test_uppercase_and_padded_uuid_is_accepted() -> None:
    mid = await _create()
    result = await _verify(mandate_id=f"  {mid.upper()} ")
    assert result["authorized"] is True
    assert result["mandate_id"] == mid


async def test_blank_mandate_id_keeps_the_old_behaviour() -> None:
    mid = await _create()
    for blank in ("", "   "):
        result = await _verify(mandate_id=blank)
        assert result["authorized"] is True
        assert result["mandate_id"] == mid


async def test_expired_named_mandate_is_refused(temp_db: Path) -> None:
    mid = await _create()
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    con = sqlite3.connect(temp_db)
    try:
        # Test-only: simulate time passing on the stored expiry.
        con.execute("UPDATE mandates SET expires_at = ? WHERE id = ?", (past, mid))
        con.commit()
    finally:
        con.close()
    result = await _verify(mandate_id=mid)
    assert result["authorized"] is False
    assert result["reason"] == "Mandate expired"


async def test_inactive_status_named_mandate_is_refused(temp_db: Path) -> None:
    mid = await _create()
    con = sqlite3.connect(temp_db)
    try:
        con.execute("UPDATE mandates SET status = ? WHERE id = ?", ("suspended", mid))
        con.commit()
    finally:
        con.close()
    result = await _verify(mandate_id=mid)
    assert result["authorized"] is False
    assert result["reason"] == "Mandate is suspended"


async def test_named_sub_mandate_under_revoked_parent_is_refused() -> None:
    root = await _create()
    sub = json.loads(
        await create_mandate(
            principal_id=AGENT,
            agent_id=HELPER,
            scope="Read invoices only",
            legal_basis_regulation="Service contract",
            legal_basis_article="Clause 4",
            duration_hours=12.0,
            parent_mandate_id=root,
            allowed_actions=["invoice.read"],
        )
    )["mandate_id"]
    assert (await _verify(HELPER, sub))["authorized"] is True
    await _revoke(root)
    result = await _verify(HELPER, sub)
    assert result["authorized"] is False
    assert result["reason"] == "Delegation chain broken: parent_mandate_revoked"
    assert result["mandate_id"] == sub


async def test_positional_call_without_mandate_id_still_works() -> None:
    mid = await _create()
    result = json.loads(await verify_mandate(AGENT, "pay invoice", "ctx"))
    assert result["authorized"] is True
    assert result["mandate_id"] == mid
