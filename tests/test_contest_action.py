"""Tests for contest_action, prepare_contest_signature and list_action_contests.

Answers the question "the agent has already acted: what does the registry keep?". The
principal records that one logged act is disputed, with a response deadline it chooses;
the registry keeps a dated, chained, append-only trace and reminds the deadline.
"""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from amr.crypto.chain import compute_hash
from amr.crypto.principal import b64url_encode, key_registration_payload
from amr.crypto.signing import generate_signing_key
from amr.db.engine import init_db
from amr.tools.contest_action import (
    contest_action,
    list_action_contests,
    prepare_contest_signature,
)
from amr.tools.create_mandate import create_mandate
from amr.tools.get_proof import get_proof
from amr.tools.issue_action_token import issue_action_token
from amr.tools.log_action import log_action
from amr.tools.principal_keys import prepare_mandate_signature, register_principal_key
from amr.tools.revoke_mandate import revoke_mandate
from amr.tools.verify_mandate import verify_mandate

PRINCIPAL = "org:clinic"
AGENT = "agent:buyer"
HELPER = "agent:helper"
REASON = "order placed above the agreed quantity"

ROOT = {
    "principal_id": PRINCIPAL,
    "agent_id": AGENT,
    "scope": "Order supplies",
    "legal_basis_regulation": "Mandate contract",
    "legal_basis_article": "Clause 1",
    "duration_hours": 24.0,
    "allowed_actions": ["order.*"],
    "delegation_allowed": True,
}


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
        "scope": "Order paper only",
        "legal_basis_regulation": "Service contract",
        "legal_basis_article": "Clause 4",
        "duration_hours": 12.0,
        "parent_mandate_id": parent_id,
        "allowed_actions": ["order.paper"],
    }
    params.update(overrides)
    result = json.loads(await create_mandate(**params))
    assert result.get("status") == "created", result
    return result


async def _log(mandate_id: str, action: str = "ordered 500 boxes of gloves") -> dict:
    result = json.loads(await log_action(mandate_id, action))
    assert result.get("status") == "logged", result
    return result


async def _contest(mandate_id: str, action_id: str, **kw: object) -> dict:
    params: dict = {"reason": REASON, "response_days": 14}
    params.update(kw)
    return json.loads(await contest_action(mandate_id, action_id, **params))


async def _proof(mandate_id: str) -> dict:
    return json.loads(await get_proof(mandate_id))


def _sql(db_path: Path, statement: str, params: tuple = ()) -> list[tuple]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(statement, params).fetchall()
        conn.commit()
    return rows


def _pub(key: ed25519.Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return b64url_encode(raw)


async def _register(key: ed25519.Ed25519PrivateKey, principal_id: str = PRINCIPAL) -> None:
    proof = b64url_encode(key.sign(key_registration_payload(principal_id, _pub(key))))
    result = json.loads(await register_principal_key(principal_id, _pub(key), proof))
    assert result["status"] == "registered", result


async def _signed_root(key: ed25519.Ed25519PrivateKey) -> dict:
    prepared = json.loads(await prepare_mandate_signature(**ROOT))
    signature = b64url_encode(key.sign(prepared["payload"].encode("utf-8")))
    return await _create(principal_signature=signature, signed_at=prepared["signed_at"])


async def _signature(
    key: ed25519.Ed25519PrivateKey,
    mandate_id: str,
    action_id: str,
    reason: str = REASON,
    response_days: int = 14,
    **kw: object,
) -> dict:
    prepared = json.loads(
        await prepare_contest_signature(mandate_id, action_id, reason, response_days, **kw)
    )
    assert "payload" in prepared, prepared
    return {
        "principal_signature": b64url_encode(key.sign(prepared["payload"].encode("utf-8"))),
        "signed_at": prepared["signed_at"],
    }


# --- The record ---------------------------------------------------------------------


async def test_contest_returns_the_record_and_its_reminder() -> None:
    root = await _create()
    action = await _log(root["mandate_id"])
    before = datetime.now(UTC)
    result = await _contest(root["mandate_id"], action["action_id"])
    assert result["status"] == "contested"
    assert result["mandate_id"] == root["mandate_id"]
    assert result["action_id"] == action["action_id"]
    assert result["action_chain_hash"] == action["chain_hash"]
    assert result["contested_by"] == PRINCIPAL
    assert result["reason"] == REASON
    assert result["response_days"] == 14
    assert result["principal_signature"] is None
    assert len(result["chain_hash"]) == 64
    contested_at = datetime.fromisoformat(result["contested_at"])
    assert before <= contested_at <= datetime.now(UTC)
    respond_by = datetime.fromisoformat(result["reminder"]["respond_by"])
    assert respond_by - contested_at == timedelta(days=14)
    assert result["reminder"]["days_left"] == 13 or result["reminder"]["days_left"] == 14
    assert result["reminder"]["deadline_passed"] is False


async def test_contest_changes_no_hash_and_does_not_revoke(temp_db: Path) -> None:
    root = await _create()
    action = await _log(root["mandate_id"])
    rows_before = _sql(temp_db, "SELECT * FROM action_logs")
    mandate_before = _sql(temp_db, "SELECT * FROM mandates")
    await _contest(root["mandate_id"], action["action_id"])
    assert _sql(temp_db, "SELECT * FROM action_logs") == rows_before
    assert _sql(temp_db, "SELECT * FROM mandates") == mandate_before
    verdict = json.loads(await verify_mandate(AGENT, "order"))
    assert verdict["authorized"] is True
    token = json.loads(
        await issue_action_token(
            root["mandate_id"], AGENT, "order paper", "runtime://erp", action_type="order.paper"
        )
    )
    assert "token" in token, token
    proof = await _proof(root["mandate_id"])
    assert proof["mandate"]["status"] == "active"
    assert proof["chain_integrity"]["actions_chain_valid"] is True


async def test_contest_appends_an_event() -> None:
    root = await _create()
    action = await _log(root["mandate_id"])
    await _contest(root["mandate_id"], action["action_id"])
    events = (await _proof(root["mandate_id"]))["events"]
    contested = [e for e in events if e["event_type"] == "action_contested"]
    assert len(contested) == 1
    assert contested[0]["reason"] == f"action {action['action_id']}: {REASON}"


async def test_contest_chain_links_each_contest_to_the_previous(temp_db: Path) -> None:
    root = await _create()
    first = await _log(root["mandate_id"], "first order")
    second = await _log(root["mandate_id"], "second order")
    one = await _contest(root["mandate_id"], first["action_id"])
    two = await _contest(root["mandate_id"], second["action_id"], response_days=3)
    row = _sql(
        temp_db,
        "SELECT mandate_id, action_id, action_chain_hash, contested_by, reason, "
        "response_days, contested_at, respond_by FROM action_contests WHERE action_id = ?",
        (second["action_id"],),
    )[0]
    mandate_hash = _sql(temp_db, "SELECT chain_hash FROM mandates")[0][0]
    expected = compute_hash(
        {
            "mandate_id": row[0],
            "mandate_chain_hash": mandate_hash,
            "action_id": row[1],
            "action_chain_hash": row[2],
            "contested_by": row[3],
            "reason": row[4],
            "response_days": row[5],
            "contested_at": row[6],
            "respond_by": row[7],
        },
        one["chain_hash"],
    )
    assert two["chain_hash"] == expected
    assert one["chain_hash"] != two["chain_hash"]


async def test_a_revoked_mandate_can_still_be_contested() -> None:
    root = await _create()
    action = await _log(root["mandate_id"])
    revoked = json.loads(await revoke_mandate(root["mandate_id"], "stop"))
    assert revoked["status"] == "revoked"
    result = await _contest(root["mandate_id"], action["action_id"])
    assert result["status"] == "contested"


# --- Refusals -----------------------------------------------------------------------


async def test_one_contest_per_action() -> None:
    root = await _create()
    action = await _log(root["mandate_id"])
    await _contest(root["mandate_id"], action["action_id"])
    again = await _contest(root["mandate_id"], action["action_id"], reason="other reason")
    assert again["code"] == "action_already_contested"


async def test_unknown_mandate_is_refused() -> None:
    result = await _contest(str(uuid4()), str(uuid4()))
    assert result["code"] == "mandate_not_found"


async def test_unknown_action_is_refused() -> None:
    root = await _create()
    result = await _contest(root["mandate_id"], str(uuid4()))
    assert result["code"] == "action_not_found"


async def test_action_of_another_mandate_is_refused() -> None:
    root = await _create()
    other = await _create(agent_id="agent:other")
    action = await _log(other["mandate_id"])
    result = await _contest(root["mandate_id"], action["action_id"])
    assert result["code"] == "action_not_found"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("response_days", 0),
        ("response_days", 366),
        ("response_days", True),
        ("response_days", "14"),
        ("response_days", 1.5),
        ("reason", ""),
        ("reason", "x" * 501),
        ("contested_by", ""),
    ],
)
async def test_invalid_input_is_refused(field: str, value: object) -> None:
    root = await _create()
    action = await _log(root["mandate_id"])
    result = await _contest(root["mandate_id"], action["action_id"], **{field: value})
    assert result["code"] == "invalid_input", result


async def test_bad_uuids_are_refused() -> None:
    assert (await _contest("not-a-uuid", str(uuid4())))["code"] == "invalid_input"
    root = await _create()
    assert (await _contest(root["mandate_id"], "not-a-uuid"))["code"] == "invalid_input"


async def test_bounds_are_accepted() -> None:
    root = await _create()
    one = await _log(root["mandate_id"], "a")
    two = await _log(root["mandate_id"], "b")
    assert (await _contest(root["mandate_id"], one["action_id"], response_days=1))[
        "status"
    ] == "contested"
    assert (await _contest(root["mandate_id"], two["action_id"], response_days=365))[
        "status"
    ] == "contested"


# --- Who contests -------------------------------------------------------------------


async def test_a_stranger_cannot_contest() -> None:
    root = await _create()
    action = await _log(root["mandate_id"])
    result = await _contest(root["mandate_id"], action["action_id"], contested_by="org:rival")
    assert result["code"] == "contester_not_in_chain"


async def test_the_agent_cannot_contest_its_own_root_mandate() -> None:
    root = await _create()
    action = await _log(root["mandate_id"])
    result = await _contest(root["mandate_id"], action["action_id"], contested_by=AGENT)
    assert result["code"] == "contester_not_in_chain"


async def test_root_principal_contests_an_act_of_a_sub_agent() -> None:
    root = await _create()
    child = await _sub(root["mandate_id"])
    action = await _log(child["mandate_id"])
    result = await _contest(child["mandate_id"], action["action_id"], contested_by=PRINCIPAL)
    assert result["status"] == "contested"
    assert result["contested_by"] == PRINCIPAL
    default = await _contest(child["mandate_id"], (await _log(child["mandate_id"]))["action_id"])
    assert default["contested_by"] == AGENT


async def test_root_principal_contests_after_the_branch_is_cut() -> None:
    root = await _create()
    child = await _sub(root["mandate_id"])
    action = await _log(child["mandate_id"])
    await revoke_mandate(root["mandate_id"], "stop")
    result = await _contest(child["mandate_id"], action["action_id"], contested_by=PRINCIPAL)
    assert result["status"] == "contested"


async def test_grandparent_principal_contests_a_leaf_act() -> None:
    root = await _create()
    middle = await _sub(
        root["mandate_id"], allowed_actions=["order.*"], delegation_allowed=True
    )
    leaf = await _sub(
        middle["mandate_id"], principal_id=HELPER, agent_id="agent:leaf", duration_hours=6.0
    )
    action = await _log(leaf["mandate_id"])
    result = await _contest(leaf["mandate_id"], action["action_id"], contested_by=PRINCIPAL)
    assert result["status"] == "contested"
    fresh = await _log(leaf["mandate_id"], "another order")
    sideways = await _contest(
        leaf["mandate_id"], fresh["action_id"], contested_by="agent:leaf"
    )
    assert sideways["code"] == "contester_not_in_chain"


async def test_a_sub_principal_cannot_contest_the_parent_act() -> None:
    root = await _create()
    await _sub(root["mandate_id"])
    action = await _log(root["mandate_id"])
    result = await _contest(root["mandate_id"], action["action_id"], contested_by=HELPER)
    assert result["code"] == "contester_not_in_chain"


# --- Signatures ---------------------------------------------------------------------


async def test_a_principal_with_a_key_must_sign() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    await _register(key)
    root = await _signed_root(key)
    action = await _log(root["mandate_id"])
    result = await _contest(root["mandate_id"], action["action_id"])
    assert result["code"] == "principal_signature_required"


async def test_signed_contest_is_recorded_and_verified() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    await _register(key)
    root = await _signed_root(key)
    action = await _log(root["mandate_id"])
    signature = await _signature(key, root["mandate_id"], action["action_id"])
    result = await _contest(root["mandate_id"], action["action_id"], **signature)
    assert result["status"] == "contested", result
    assert result["principal_signature"]["signed_at"] == signature["signed_at"]
    proof = await _proof(root["mandate_id"])
    contest = proof["action_contests"][0]
    assert contest["principal_signature"]["signature"] == signature["principal_signature"]
    assert contest["principal_signature_valid"] is True
    assert proof["chain_integrity"]["contests_intact"] is True


async def test_signature_over_other_terms_is_refused() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    await _register(key)
    root = await _signed_root(key)
    action = await _log(root["mandate_id"])
    signature = await _signature(key, root["mandate_id"], action["action_id"], response_days=30)
    result = await _contest(root["mandate_id"], action["action_id"], **signature)
    assert result["code"] == "principal_signature_invalid"
    signature = await _signature(key, root["mandate_id"], action["action_id"], reason="other")
    result = await _contest(root["mandate_id"], action["action_id"], **signature)
    assert result["code"] == "principal_signature_invalid"


async def test_signature_by_another_key_is_refused() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    await _register(key)
    root = await _signed_root(key)
    action = await _log(root["mandate_id"])
    intruder = ed25519.Ed25519PrivateKey.generate()
    signature = await _signature(intruder, root["mandate_id"], action["action_id"])
    result = await _contest(root["mandate_id"], action["action_id"], **signature)
    assert result["code"] == "principal_signature_invalid"


async def test_incomplete_signature_is_refused() -> None:
    root = await _create()
    action = await _log(root["mandate_id"])
    result = await _contest(
        root["mandate_id"], action["action_id"], signed_at=datetime.now(UTC).isoformat()
    )
    assert result["code"] == "principal_signature_incomplete"


async def test_signature_without_registered_key_is_refused() -> None:
    root = await _create()
    action = await _log(root["mandate_id"])
    key = ed25519.Ed25519PrivateKey.generate()
    signature = await _signature(key, root["mandate_id"], action["action_id"])
    result = await _contest(root["mandate_id"], action["action_id"], **signature)
    assert result["code"] == "principal_key_not_registered"


async def test_stale_signature_is_refused() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    await _register(key)
    root = await _signed_root(key)
    action = await _log(root["mandate_id"])
    old = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    signature = await _signature(key, root["mandate_id"], action["action_id"], signed_at=old)
    result = await _contest(root["mandate_id"], action["action_id"], **signature)
    assert result["code"] == "principal_signature_stale"


async def test_root_principal_signs_for_a_sub_agent_act() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    await _register(key)
    root = await _signed_root(key)
    child = await _sub(root["mandate_id"])
    action = await _log(child["mandate_id"])
    unsigned = await _contest(child["mandate_id"], action["action_id"], contested_by=PRINCIPAL)
    assert unsigned["code"] == "principal_signature_required"
    signature = await _signature(
        key, child["mandate_id"], action["action_id"], contested_by=PRINCIPAL
    )
    result = await _contest(
        child["mandate_id"], action["action_id"], contested_by=PRINCIPAL, **signature
    )
    assert result["status"] == "contested", result
    proof = await _proof(child["mandate_id"])
    assert proof["action_contests"][0]["principal_signature_valid"] is True


async def test_registry_requiring_signatures_refuses_unsigned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = await _create()
    action = await _log(root["mandate_id"])
    monkeypatch.setattr("amr.config.settings.require_principal_signature", True)
    result = await _contest(root["mandate_id"], action["action_id"])
    assert result["code"] == "principal_signature_required"


async def test_prepare_names_the_default_contester() -> None:
    root = await _create()
    action = await _log(root["mandate_id"])
    prepared = json.loads(
        await prepare_contest_signature(root["mandate_id"], action["action_id"], REASON, 14)
    )
    assert prepared["contested_by"] == PRINCIPAL
    payload = json.loads(prepared["payload"])
    assert payload == {
        "context": "amr.action_contest.v1",
        "mandate_id": root["mandate_id"],
        "action_id": action["action_id"],
        "contested_by": PRINCIPAL,
        "reason": REASON,
        "response_days": 14,
        "signed_at": prepared["signed_at"],
    }


async def test_prepare_refuses_a_stranger_and_bad_input() -> None:
    root = await _create()
    action = await _log(root["mandate_id"])
    stranger = json.loads(
        await prepare_contest_signature(
            root["mandate_id"], action["action_id"], REASON, 14, contested_by="org:rival"
        )
    )
    assert stranger["code"] == "contester_not_in_chain"
    bad = json.loads(
        await prepare_contest_signature(root["mandate_id"], action["action_id"], REASON, 0)
    )
    assert bad["code"] == "invalid_input"


# --- The reminder -------------------------------------------------------------------


async def test_list_requires_a_filter() -> None:
    result = json.loads(await list_action_contests())
    assert result["code"] == "invalid_input"


async def test_list_orders_by_nearest_deadline(temp_db: Path) -> None:
    root = await _create()
    late = await _log(root["mandate_id"], "a")
    soon = await _log(root["mandate_id"], "b")
    await _contest(root["mandate_id"], late["action_id"], response_days=30)
    await _contest(root["mandate_id"], soon["action_id"], response_days=2)
    result = json.loads(await list_action_contests(mandate_id=root["mandate_id"]))
    assert result["count"] == 2
    assert result["truncated"] is False
    assert [c["action_id"] for c in result["contests"]] == [
        soon["action_id"],
        late["action_id"],
    ]
    assert result["contests"][0]["reminder"]["days_left"] in {1, 2}


async def test_list_due_within_keeps_near_and_passed(temp_db: Path) -> None:
    root = await _create()
    far = await _log(root["mandate_id"], "far")
    near = await _log(root["mandate_id"], "near")
    past = await _log(root["mandate_id"], "past")
    await _contest(root["mandate_id"], far["action_id"], response_days=60)
    await _contest(root["mandate_id"], near["action_id"], response_days=3)
    await _contest(root["mandate_id"], past["action_id"], response_days=5)
    gone = (datetime.now(UTC) - timedelta(days=2, hours=1)).isoformat()
    _sql(
        temp_db,
        "UPDATE action_contests SET respond_by = ? WHERE action_id = ?",
        (gone, past["action_id"]),
    )
    result = json.loads(
        await list_action_contests(mandate_id=root["mandate_id"], due_within_days=7)
    )
    ids = [c["action_id"] for c in result["contests"]]
    assert ids == [past["action_id"], near["action_id"]]
    passed = result["contests"][0]["reminder"]
    assert passed["deadline_passed"] is True
    assert passed["days_left"] == -2
    zero = json.loads(
        await list_action_contests(mandate_id=root["mandate_id"], due_within_days=0)
    )
    assert [c["action_id"] for c in zero["contests"]] == [past["action_id"]]


async def test_list_by_contester_spans_mandates() -> None:
    root = await _create()
    child = await _sub(root["mandate_id"])
    other = await _create(principal_id="org:other", agent_id="agent:other")
    a = await _log(root["mandate_id"])
    b = await _log(child["mandate_id"])
    c = await _log(other["mandate_id"])
    await _contest(root["mandate_id"], a["action_id"])
    await _contest(child["mandate_id"], b["action_id"], contested_by=PRINCIPAL)
    await _contest(other["mandate_id"], c["action_id"])
    mine = json.loads(await list_action_contests(contested_by=PRINCIPAL))
    assert {x["action_id"] for x in mine["contests"]} == {a["action_id"], b["action_id"]}
    both = json.loads(
        await list_action_contests(mandate_id=child["mandate_id"], contested_by=PRINCIPAL)
    )
    assert [x["action_id"] for x in both["contests"]] == [b["action_id"]]
    none = json.loads(
        await list_action_contests(mandate_id=child["mandate_id"], contested_by=AGENT)
    )
    assert none["count"] == 0


async def test_list_is_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("amr.tools.contest_action.MAX_LISTED_CONTESTS", 2)
    root = await _create()
    for days in (9, 3, 5):
        action = await _log(root["mandate_id"], f"order {days}")
        await _contest(root["mandate_id"], action["action_id"], response_days=days)
    result = json.loads(await list_action_contests(mandate_id=root["mandate_id"]))
    assert result["truncated"] is True
    assert [c["response_days"] for c in result["contests"]] == [3, 5]


@pytest.mark.parametrize("value", [-1, 366, True])
async def test_list_invalid_horizon(value: object) -> None:
    root = await _create()
    result = json.loads(
        await list_action_contests(mandate_id=root["mandate_id"], due_within_days=value)  # type: ignore[arg-type]
    )
    assert result["code"] == "invalid_input"


# --- Proof Pack and tampering --------------------------------------------------------


async def test_proof_without_contest_is_unchanged_in_meaning() -> None:
    root = await _create()
    await _log(root["mandate_id"])
    proof = await _proof(root["mandate_id"])
    assert proof["action_contests"] == []
    assert proof["chain_integrity"]["contests_intact"] is True


async def test_proof_lists_contests() -> None:
    root = await _create()
    action = await _log(root["mandate_id"])
    await _contest(root["mandate_id"], action["action_id"])
    proof = await _proof(root["mandate_id"])
    (contest,) = proof["action_contests"]
    assert contest["action_id"] == action["action_id"]
    assert contest["reason"] == REASON
    assert contest["principal_signature"] is None
    assert contest["principal_signature_valid"] is None
    assert contest["reminder"]["deadline_passed"] is False
    assert proof["chain_integrity"]["contests_intact"] is True


async def test_deleted_contest_is_detected(temp_db: Path) -> None:
    root = await _create()
    action = await _log(root["mandate_id"])
    await _contest(root["mandate_id"], action["action_id"])
    _sql(temp_db, "DELETE FROM action_contests")
    proof = await _proof(root["mandate_id"])
    assert proof["action_contests"] == []
    assert proof["chain_integrity"]["contests_intact"] is False


async def test_changed_recorded_action_hash_breaks_the_contest_hash(temp_db: Path) -> None:
    root = await _create()
    action = await _log(root["mandate_id"])
    await _contest(root["mandate_id"], action["action_id"])
    _sql(temp_db, "UPDATE action_contests SET action_chain_hash = ?", ("f" * 64,))
    proof = await _proof(root["mandate_id"])
    assert proof["chain_integrity"]["contests_intact"] is False


async def test_tampered_signed_contest_is_detected(temp_db: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    await _register(key)
    root = await _signed_root(key)
    action = await _log(root["mandate_id"])
    signature = await _signature(key, root["mandate_id"], action["action_id"])
    await _contest(root["mandate_id"], action["action_id"], **signature)
    _sql(temp_db, "UPDATE action_contests SET reason = ?", ("softened reason",))
    proof = await _proof(root["mandate_id"])
    assert proof["action_contests"][0]["principal_signature_valid"] is False
    assert proof["chain_integrity"]["contests_intact"] is False


async def test_stripped_signature_is_detected(temp_db: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    await _register(key)
    root = await _signed_root(key)
    action = await _log(root["mandate_id"])
    signature = await _signature(key, root["mandate_id"], action["action_id"])
    await _contest(root["mandate_id"], action["action_id"], **signature)
    _sql(
        temp_db,
        "UPDATE action_contests SET principal_signature = NULL, principal_signed_at = NULL, "
        "principal_key_id = NULL, principal_signed_payload = NULL",
    )
    proof = await _proof(root["mandate_id"])
    assert proof["action_contests"][0]["principal_signature_valid"] is False
    assert proof["chain_integrity"]["contests_intact"] is False


async def test_moved_respond_by_is_detected_when_signed(temp_db: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    await _register(key)
    root = await _signed_root(key)
    action = await _log(root["mandate_id"])
    signature = await _signature(key, root["mandate_id"], action["action_id"])
    await _contest(root["mandate_id"], action["action_id"], **signature)
    later = (datetime.now(UTC) + timedelta(days=60)).isoformat()
    _sql(temp_db, "UPDATE action_contests SET respond_by = ?", (later,))
    proof = await _proof(root["mandate_id"])
    assert proof["chain_integrity"]["contests_intact"] is False


async def test_changed_response_days_breaks_the_signature(temp_db: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    await _register(key)
    root = await _signed_root(key)
    action = await _log(root["mandate_id"])
    signature = await _signature(key, root["mandate_id"], action["action_id"])
    await _contest(root["mandate_id"], action["action_id"], **signature)
    _sql(temp_db, "UPDATE action_contests SET response_days = ?", (60,))
    proof = await _proof(root["mandate_id"])
    assert proof["action_contests"][0]["principal_signature_valid"] is False


# --- Schema and compatibility ---------------------------------------------------------


async def test_schema_v8_is_recorded_and_idempotent(temp_db: Path) -> None:
    root = await _create()
    before = _sql(temp_db, "SELECT id, chain_hash FROM mandates")
    await init_db(temp_db)
    await init_db(temp_db)
    versions = {row[0] for row in _sql(temp_db, "SELECT version FROM schema_version")}
    assert 8 in versions
    assert _sql(temp_db, "SELECT id, chain_hash FROM mandates") == before
    assert before[0][0] == root["mandate_id"]


def test_tools_are_registered() -> None:
    server = (Path(__file__).resolve().parent.parent / "src" / "amr" / "server.py").read_text(
        encoding="utf-8"
    )
    for tool in ("contest_action", "prepare_contest_signature", "list_action_contests"):
        assert f"mcp.tool()({tool})" in server


async def test_edited_unsigned_contest_is_detected(temp_db: Path) -> None:
    root = await _create()
    action = await _log(root["mandate_id"])
    await _contest(root["mandate_id"], action["action_id"])
    later = (datetime.now(UTC) + timedelta(days=90)).isoformat()
    _sql(temp_db, "UPDATE action_contests SET respond_by = ?", (later,))
    proof = await _proof(root["mandate_id"])
    assert proof["chain_integrity"]["contests_intact"] is False


async def test_removed_earlier_contest_breaks_the_next_link(temp_db: Path) -> None:
    root = await _create()
    other = await _create(agent_id="agent:other")
    first = await _log(other["mandate_id"])
    second = await _log(root["mandate_id"])
    await _contest(other["mandate_id"], first["action_id"])
    await _contest(root["mandate_id"], second["action_id"])
    assert (await _proof(root["mandate_id"]))["chain_integrity"]["contests_intact"] is True
    _sql(temp_db, "DELETE FROM action_contests WHERE action_id = ?", (first["action_id"],))
    assert (await _proof(root["mandate_id"]))["chain_integrity"]["contests_intact"] is False


async def test_several_contests_in_one_mandate_stay_intact() -> None:
    root = await _create()
    for label in ("a", "b", "c"):
        action = await _log(root["mandate_id"], label)
        await _contest(root["mandate_id"], action["action_id"])
    proof = await _proof(root["mandate_id"])
    assert len(proof["action_contests"]) == 3
    assert proof["chain_integrity"]["contests_intact"] is True


async def test_second_contest_is_refused_before_any_signature_check() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    await _register(key)
    root = await _signed_root(key)
    action = await _log(root["mandate_id"])
    signature = await _signature(key, root["mandate_id"], action["action_id"])
    assert (await _contest(root["mandate_id"], action["action_id"], **signature))[
        "status"
    ] == "contested"
    again = await _contest(root["mandate_id"], action["action_id"])
    assert again["code"] == "action_already_contested"


async def test_action_log_edited_after_contest_is_detected(temp_db: Path) -> None:
    root = await _create()
    action = await _log(root["mandate_id"])
    await _contest(root["mandate_id"], action["action_id"])
    _sql(
        temp_db,
        "UPDATE action_logs SET chain_hash = ? WHERE id = ?",
        ("e" * 64, action["action_id"]),
    )
    proof = await _proof(root["mandate_id"])
    assert proof["chain_integrity"]["contests_intact"] is False


async def test_database_allows_one_contest_per_action(temp_db: Path) -> None:
    root = await _create()
    action = await _log(root["mandate_id"])
    await _contest(root["mandate_id"], action["action_id"])
    with pytest.raises(sqlite3.IntegrityError):
        _sql(
            temp_db,
            "INSERT INTO action_contests (action_id, mandate_id, action_chain_hash, "
            "contested_by, reason, response_days, contested_at, respond_by, chain_hash) "
            "SELECT action_id, mandate_id, action_chain_hash, contested_by, reason, "
            "response_days, contested_at, respond_by, chain_hash FROM action_contests",
        )


async def test_concurrent_contests_keep_the_chain_intact() -> None:
    import asyncio

    root = await _create()
    actions = [await _log(root["mandate_id"], f"order {i}") for i in range(6)]
    results = await asyncio.gather(
        *(_contest(root["mandate_id"], a["action_id"]) for a in actions)
    )
    assert all(r.get("status") == "contested" for r in results), results
    proof = await _proof(root["mandate_id"])
    assert len(proof["action_contests"]) == 6
    assert proof["chain_integrity"]["contests_intact"] is True


async def test_concurrent_double_contest_records_one() -> None:
    import asyncio

    root = await _create()
    action = await _log(root["mandate_id"])
    results = await asyncio.gather(
        *(_contest(root["mandate_id"], action["action_id"]) for _ in range(4))
    )
    assert sum(r.get("status") == "contested" for r in results) == 1
    assert {r.get("code") for r in results if "code" in r} == {"action_already_contested"}


async def test_key_registered_after_an_unsigned_contest_reads_null() -> None:
    root = await _create()
    action = await _log(root["mandate_id"])
    await _contest(root["mandate_id"], action["action_id"])
    await _register(ed25519.Ed25519PrivateKey.generate())
    proof = await _proof(root["mandate_id"])
    assert proof["action_contests"][0]["principal_signature_valid"] is None
    assert proof["chain_integrity"]["contests_intact"] is True


async def test_contest_whose_event_was_deleted_is_detected(temp_db: Path) -> None:
    root = await _create()
    action = await _log(root["mandate_id"])
    await _contest(root["mandate_id"], action["action_id"])
    _sql(temp_db, "DELETE FROM mandate_events WHERE event_type = 'action_contested'")
    proof = await _proof(root["mandate_id"])
    assert proof["chain_integrity"]["contests_intact"] is False


async def test_prepare_refuses_an_action_already_contested() -> None:
    root = await _create()
    action = await _log(root["mandate_id"])
    await _contest(root["mandate_id"], action["action_id"])
    prepared = json.loads(
        await prepare_contest_signature(root["mandate_id"], action["action_id"], REASON, 14)
    )
    assert prepared["code"] == "action_already_contested"


async def test_insurer_dossier_reports_contests() -> None:
    from amr.tools.export_insurer_dossier import export_insurer_dossier

    root = await _create()
    action = await _log(root["mandate_id"])
    await _contest(root["mandate_id"], action["action_id"])
    result = json.loads(await export_insurer_dossier(root["mandate_id"]))
    assert "error" not in result, result
    text = json.dumps(result)
    assert '"contested_actions": 1' in text
    assert '"contests_intact": true' in text


async def test_v7_database_migrates_without_changing_hashes(temp_db: Path) -> None:
    root = await _create()
    action = await _log(root["mandate_id"])
    # Make it a v7 database again: no contest table, no v8 row.
    _sql(temp_db, "DROP TABLE action_contests")
    _sql(temp_db, "DELETE FROM schema_version WHERE version = 8")
    mandates = _sql(temp_db, "SELECT * FROM mandates")
    logs = _sql(temp_db, "SELECT * FROM action_logs")
    await init_db(temp_db)
    assert 8 in {row[0] for row in _sql(temp_db, "SELECT version FROM schema_version")}
    assert _sql(temp_db, "SELECT * FROM mandates") == mandates
    assert _sql(temp_db, "SELECT * FROM action_logs") == logs
    proof = await _proof(root["mandate_id"])
    assert proof["action_contests"] == []
    assert proof["chain_integrity"]["contests_intact"] is True
    assert (await _contest(root["mandate_id"], action["action_id"]))["status"] == "contested"


async def test_insurer_dossier_reports_a_broken_contest(temp_db: Path) -> None:
    from amr.tools.export_insurer_dossier import export_insurer_dossier

    root = await _create()
    action = await _log(root["mandate_id"])
    await _contest(root["mandate_id"], action["action_id"])
    _sql(temp_db, "UPDATE action_contests SET reason = ?", ("softened",))
    text = json.dumps(json.loads(await export_insurer_dossier(root["mandate_id"])))
    assert '"contests_intact": false' in text
