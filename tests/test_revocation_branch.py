"""Revocation and expiry of a parent stop log_action on its whole branch.

Before this change, log_action checked only the mandate it was given: a sub-mandate
under a revoked or expired parent could still write to the action journal, and its
Proof Pack showed nothing wrong. Answers a question asked on 23/10/2026: a revocation
that lives in the registry must not leave a branch that is still accepted.
"""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from amr.crypto.signing import generate_signing_key
from amr.tools.create_mandate import create_mandate
from amr.tools.get_proof import get_proof
from amr.tools.log_action import log_action
from amr.tools.revoke_mandate import revoke_mandate

PRINCIPAL = "org:clinic"
AGENT = "agent:billing"
HELPER = "agent:helper"
LEAF = "agent:leaf"

ROOT = {
    "principal_id": PRINCIPAL,
    "agent_id": AGENT,
    "scope": "Handle supplier invoices",
    "legal_basis_regulation": "Mandate contract",
    "legal_basis_article": "Clause 1",
    "duration_hours": 24.0,
    "allowed_actions": ["invoice.*"],
    "delegation_allowed": True,
}

UNBROKEN = {"broken": False, "reason": None, "refused_by": None}


@pytest.fixture(autouse=True)
def isolated_signing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    priv = tmp_path / "test_key.pem"
    pub = tmp_path / "test_key.pub"
    monkeypatch.setattr("amr.config.settings.signing_key_path", priv)
    monkeypatch.setattr("amr.config.settings.public_key_path", pub)
    generate_signing_key(priv, pub)


async def _create(**overrides: object) -> dict:
    result = json.loads(await create_mandate(**{**ROOT, **overrides}))
    assert result.get("status") == "created", result
    return result


async def _sub(parent_id: str, **overrides: object) -> dict:
    params: dict = {
        "principal_id": AGENT,
        "agent_id": HELPER,
        "scope": "Read invoices only",
        "legal_basis_regulation": "Service contract",
        "legal_basis_article": "Clause 4",
        "duration_hours": 12.0,
        "parent_mandate_id": parent_id,
        "allowed_actions": ["invoice.read"],
    }
    params.update(overrides)
    result = json.loads(await create_mandate(**params))
    assert result.get("status") == "created", result
    return result


async def _chain() -> tuple[dict, dict, dict]:
    """Root -> middle -> leaf, all in force."""
    root = await _create()
    middle = await _sub(root["mandate_id"], allowed_actions=["invoice.*"],
                        delegation_allowed=True)
    leaf = await _sub(middle["mandate_id"], principal_id=HELPER, agent_id=LEAF,
                      duration_hours=6.0)
    return root, middle, leaf


async def _log(mandate_id: str, action: str = "read invoice 7") -> dict:
    return json.loads(await log_action(mandate_id=mandate_id, action=action))


async def _proof(mandate_id: str) -> dict:
    return json.loads(await get_proof(mandate_id))


def _sql(db_path: Path, statement: str, params: tuple = ()) -> list[tuple]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(statement, params).fetchall()
        conn.commit()
    return rows


def _actions(db_path: Path, mandate_id: str) -> int:
    return _sql(db_path, "SELECT COUNT(*) FROM action_logs WHERE mandate_id = ?",
                (mandate_id,))[0][0]


def _expire(db_path: Path, mandate_id: str) -> None:
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    _sql(db_path, "UPDATE mandates SET expires_at = ? WHERE id = ?", (past, mandate_id))


# --- log_action --------------------------------------------------------------------


async def test_sub_mandate_logs_while_its_chain_is_in_force(temp_db: Path) -> None:
    _, middle, leaf = await _chain()
    assert (await _log(middle["mandate_id"]))["status"] == "logged"
    assert (await _log(leaf["mandate_id"]))["status"] == "logged"
    assert _actions(temp_db, leaf["mandate_id"]) == 1


async def test_revoked_parent_stops_logging_on_the_sub_mandate(temp_db: Path) -> None:
    root = await _create()
    child = await _sub(root["mandate_id"])
    await revoke_mandate(root["mandate_id"], "agent exceeded its order limit")
    refused = await _log(child["mandate_id"])
    assert "status" not in refused
    assert refused["reason"] == "parent_mandate_revoked"
    assert refused["refused_by"] == root["mandate_id"]
    assert "not in force" in refused["error"]
    assert _actions(temp_db, child["mandate_id"]) == 0


async def test_revoked_grandparent_stops_logging_on_the_whole_branch(temp_db: Path) -> None:
    root, middle, leaf = await _chain()
    await revoke_mandate(root["mandate_id"], "branch cut by the clinic")
    for mandate in (middle, leaf):
        refused = await _log(mandate["mandate_id"])
        assert refused["reason"] == "parent_mandate_revoked"
        assert refused["refused_by"] == root["mandate_id"]
        assert _actions(temp_db, mandate["mandate_id"]) == 0


async def test_revoked_middle_stops_the_leaf_but_not_the_root(temp_db: Path) -> None:
    root, middle, leaf = await _chain()
    await revoke_mandate(middle["mandate_id"], "helper no longer needed")
    refused = await _log(leaf["mandate_id"])
    assert refused["reason"] == "parent_mandate_revoked"
    assert refused["refused_by"] == middle["mandate_id"]
    assert (await _log(root["mandate_id"]))["status"] == "logged"


async def test_expired_parent_stops_logging_on_the_sub_mandate(temp_db: Path) -> None:
    root = await _create()
    child = await _sub(root["mandate_id"])
    _expire(temp_db, root["mandate_id"])
    refused = await _log(child["mandate_id"])
    assert refused["reason"] == "parent_mandate_expired"
    assert refused["refused_by"] == root["mandate_id"]
    assert _actions(temp_db, child["mandate_id"]) == 0


async def test_inactive_grandparent_stops_logging_on_the_leaf(temp_db: Path) -> None:
    root, _, leaf = await _chain()
    _sql(temp_db, "UPDATE mandates SET status = 'suspended' WHERE id = ?",
         (root["mandate_id"],))
    refused = await _log(leaf["mandate_id"])
    assert refused["reason"] == "parent_mandate_suspended"
    assert refused["refused_by"] == root["mandate_id"]


async def test_revoked_sub_mandate_leaves_its_parent_logging(temp_db: Path) -> None:
    root = await _create()
    child = await _sub(root["mandate_id"])
    await revoke_mandate(child["mandate_id"], "helper no longer needed")
    assert "error" in await _log(child["mandate_id"])
    assert (await _log(root["mandate_id"]))["status"] == "logged"


async def test_revoked_sibling_does_not_cut_the_other_branch(temp_db: Path) -> None:
    root = await _create()
    first = await _sub(root["mandate_id"])
    second = await _sub(root["mandate_id"], agent_id="agent:other")
    await revoke_mandate(first["mandate_id"], "helper no longer needed")
    assert (await _log(second["mandate_id"]))["status"] == "logged"


async def test_actions_logged_before_the_cut_stay_chained(temp_db: Path) -> None:
    root = await _create()
    child = await _sub(root["mandate_id"])
    assert (await _log(child["mandate_id"], "read invoice 1"))["status"] == "logged"
    await revoke_mandate(root["mandate_id"], "agent exceeded its order limit")
    assert "error" in await _log(child["mandate_id"], "read invoice 2")
    proof = await _proof(child["mandate_id"])
    assert [a["action"] for a in proof["actions"]] == ["read invoice 1"]
    assert proof["chain_integrity"]["actions_chain_valid"] is True


async def test_own_expiry_is_still_reported_first(temp_db: Path) -> None:
    root = await _create()
    child = await _sub(root["mandate_id"])
    _expire(temp_db, child["mandate_id"])
    await revoke_mandate(root["mandate_id"], "agent exceeded its order limit")
    refused = await _log(child["mandate_id"])
    assert "has expired" in refused["error"]


async def test_root_mandate_logging_is_unchanged(temp_db: Path) -> None:
    root = await _create()
    logged = await _log(root["mandate_id"])
    assert set(logged) == {"status", "action_id", "mandate_id", "action", "chain_hash"}


# --- get_proof ---------------------------------------------------------------------


async def test_proof_of_a_root_mandate_has_an_unbroken_chain() -> None:
    root = await _create()
    assert (await _proof(root["mandate_id"]))["delegation_chain"] == UNBROKEN


async def test_proof_of_a_sub_mandate_in_force_has_an_unbroken_chain() -> None:
    _, _, leaf = await _chain()
    assert (await _proof(leaf["mandate_id"]))["delegation_chain"] == UNBROKEN


async def test_proof_shows_the_revoked_parent_of_a_sub_mandate() -> None:
    root, _, leaf = await _chain()
    await revoke_mandate(root["mandate_id"], "branch cut by the clinic")
    proof = await _proof(leaf["mandate_id"])
    assert proof["delegation_chain"] == {
        "broken": True,
        "reason": "parent_mandate_revoked",
        "refused_by": root["mandate_id"],
    }
    # The leaf's own status is unchanged: the cut is above it.
    assert proof["mandate"]["status"] == "active"
    assert proof["mandate"]["revocation"] is None


async def test_proof_shows_the_expired_parent_of_a_sub_mandate(temp_db: Path) -> None:
    root = await _create()
    child = await _sub(root["mandate_id"])
    _expire(temp_db, root["mandate_id"])
    chain = (await _proof(child["mandate_id"]))["delegation_chain"]
    assert chain == {
        "broken": True,
        "reason": "parent_mandate_expired",
        "refused_by": root["mandate_id"],
    }


async def test_proof_of_the_revoked_mandate_itself_keeps_an_unbroken_chain_above() -> None:
    root = await _create()
    await revoke_mandate(root["mandate_id"], "agent exceeded its order limit")
    proof = await _proof(root["mandate_id"])
    assert proof["mandate"]["status"] == "revoked"
    assert proof["delegation_chain"] == UNBROKEN


async def test_mandate_hashes_are_unchanged_by_the_check(temp_db: Path) -> None:
    root, middle, leaf = await _chain()
    before = _sql(temp_db, "SELECT id, chain_hash FROM mandates ORDER BY id")
    await revoke_mandate(root["mandate_id"], "branch cut by the clinic")
    await _log(leaf["mandate_id"])
    await _proof(leaf["mandate_id"])
    assert _sql(temp_db, "SELECT id, chain_hash FROM mandates ORDER BY id") == before
    proof = await _proof(middle["mandate_id"])
    assert proof["mandate"]["chain_hash"] == middle["chain_hash"]
