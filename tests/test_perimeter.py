"""Tests for the structured mandate perimeter and delegation control.

Covers the question a practitioner asked on 13/10/2026: does the token check the
requested action against the mandate's perimeter, or only that a mandate exists?
With a structured perimeter, it checks the action, at every level of a delegation chain.
"""

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import aiosqlite
import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from pydantic import ValidationError

from amr.crypto.chain import compute_hash
from amr.crypto.signing import generate_signing_key, load_public_key
from amr.db.engine import init_db
from amr.models.perimeter import Perimeter, pattern_covers, pattern_matches, pattern_reaches
from amr.tools.create_mandate import create_mandate
from amr.tools.get_proof import get_proof
from amr.tools.issue_action_token import _canonical_action_hash, issue_action_token
from amr.tools.verify_mandate import verify_mandate
from tests._helpers import insert_mandate_directly


@pytest.fixture(autouse=True)
def isolated_signing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    priv = tmp_path / "test_key.pem"
    pub = tmp_path / "test_key.pub"
    monkeypatch.setattr("amr.config.settings.signing_key_path", priv)
    monkeypatch.setattr("amr.config.settings.public_key_path", pub)
    generate_signing_key(priv, pub)


def _public_key_pem() -> bytes:
    return load_public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


async def _mandate(**overrides: object) -> dict:
    params: dict = {
        "principal_id": "org:clinic",
        "agent_id": "agent:billing",
        "scope": "Handle supplier invoices",
        "legal_basis_regulation": "Mandat de gestion",
        "legal_basis_article": "Art. 1984 Code civil",
        "duration_hours": 24,
    }
    params.update(overrides)
    return json.loads(await create_mandate(**params))


async def _token(mandate_id: str, agent_id: str, **overrides: object) -> dict:
    params: dict = {
        "mandate_id": mandate_id,
        "agent_id": agent_id,
        "action": "pay invoice 2026-118",
        "audience": "runtime://erp",
    }
    params.update(overrides)
    return json.loads(await issue_action_token(**params))


# --- Pattern semantics ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("pattern", "action_type", "expected"),
    [
        ("*", "anything.at.all", True),
        ("invoice.pay", "invoice.pay", True),
        ("invoice.pay", "invoice.payx", False),
        ("invoice.*", "invoice.pay", True),
        ("invoice.*", "invoice.pay.partial", True),
        ("invoice.*", "invoice", False),
        ("invoice.*", "invoices.pay", False),
    ],
)
def test_pattern_matches(pattern: str, action_type: str, expected: bool) -> None:
    assert pattern_matches(pattern, action_type) is expected


@pytest.mark.parametrize(
    ("outer", "inner", "expected"),
    [
        ("*", "*", True),
        ("*", "invoice.*", True),
        ("invoice.*", "*", False),
        ("invoice.*", "invoice.*", True),
        ("invoice.*", "invoice.pay.*", True),
        ("invoice.*", "invoice.pay", True),
        ("invoice.*", "invoices.pay", False),
        ("invoice.*", "invoices.*", False),
        ("invoice.pay", "invoice.pay", True),
        ("invoice.pay", "invoice.*", False),
    ],
)
def test_pattern_covers(outer: str, inner: str, expected: bool) -> None:
    assert pattern_covers(outer, inner) is expected


@pytest.mark.parametrize(
    ("pattern", "action_type", "expected"),
    [
        ("agent.create", "agent.create", True),
        ("agent.create", "agent.create.batch", True),
        ("agent.create", "agent.created", False),
        ("agent.*", "agent", True),
        ("agent.*", "agent.create", True),
        ("agent.*", "agents", False),
        ("*", "anything", True),
    ],
)
def test_pattern_reaches_sub_types(pattern: str, action_type: str, expected: bool) -> None:
    assert pattern_reaches(pattern, action_type) is expected


@pytest.mark.parametrize(
    "bad",
    ["Invoice.pay", "invoice pay", "invoice.**", "", ".pay", "a..b", "agent.create\n", "é.x"],
)
def test_invalid_patterns_rejected(bad: str) -> None:
    with pytest.raises(ValidationError):
        Perimeter(allowed_actions=(bad,))


def test_canonical_form_is_order_independent() -> None:
    a = Perimeter(allowed_actions=("b.x", "a.*"), forbidden_actions=("a.delete",))
    b = Perimeter(allowed_actions=("a.*", "b.x", "a.*"), forbidden_actions=("a.delete",))
    assert a.to_json() == b.to_json()
    assert a.digest() == b.digest()
    assert Perimeter.from_json(a.to_json()) == a


def test_forbidden_wins_over_allowed_and_reaches_sub_types() -> None:
    p = Perimeter(allowed_actions=("*",), forbidden_actions=("agent.create",))
    assert p.check_action("report.write", {}) is None
    assert p.check_action("agent.create", {}) == "forbidden:agent.create"
    assert p.check_action("agent.create.batch", {}) == "forbidden:agent.create"


def test_amount_actions_scope_the_limit() -> None:
    p = Perimeter(
        allowed_actions=("invoice.*",), max_amount=Decimal("500"), amount_actions=("invoice.pay",)
    )
    assert p.check_action("invoice.read", {}) is None
    assert p.check_action("invoice.pay", {}) == "amount_required"
    assert p.check_action("invoice.pay.bulk", {}) == "amount_required"
    over = {"amount": "900", "currency": "EUR"}
    assert p.check_action("invoice.read", over) == "amount_above_limit:500 EUR"
    with pytest.raises(ValidationError):
        Perimeter(allowed_actions=("invoice.*",), amount_actions=("invoice.pay",))


def test_amount_limit() -> None:
    p = Perimeter(allowed_actions=("invoice.pay",), max_amount=Decimal("500"))
    eur = {"currency": "EUR"}
    assert p.check_action("invoice.pay", {"amount": "500", **eur}) is None
    assert p.check_action("invoice.pay", {"amount": "120.50", **eur}) is None
    assert p.check_action("invoice.pay", {"amount": "500.01", **eur}) == (
        "amount_above_limit:500 EUR"
    )
    assert p.check_action("invoice.pay", {}) == "amount_required"
    assert p.check_action("invoice.pay", {"amount": "400"}) == "currency_required"
    assert p.check_action("invoice.pay", {"amount": "400", "Currency": "EUR"}) == (
        "currency_required"
    )
    assert p.check_action("invoice.pay", {"amount": "10", "currency": "eur"}) == (
        "currency_mismatch:EUR"
    )
    assert p.check_action("invoice.pay", {"amount": "10", "currency": "USD"}) == (
        "currency_mismatch:EUR"
    )


@pytest.mark.parametrize(
    "raw",
    ["cinq cents", "-1", "+500", " 500", "5_00", "1e3", "NaN", "Infinity", "0x10", "500,00",
     "\uff15\uff10\uff10", "\u0664\u0660\u0660", "1.", ".5", ""],
)
def test_amounts_must_be_plain_decimals(raw: str) -> None:
    p = Perimeter(allowed_actions=("invoice.pay",), max_amount=Decimal("500"))
    assert p.check_action("invoice.pay", {"amount": raw, "currency": "EUR"}) == "amount_invalid"


def test_ceiling_is_stored_exactly() -> None:
    exact = "123456789012345678.123456789012345678"
    p = Perimeter(allowed_actions=("x.y",), max_amount=exact)
    assert p.canonical()["max_amount"] == exact
    assert Perimeter(allowed_actions=("x.y",), max_amount="500.00").canonical()["max_amount"] == (
        "500"
    )
    with pytest.raises(ValidationError):
        Perimeter(allowed_actions=("x.y",), max_amount="1e3")


# --- Token issuance against the perimeter --------------------------------------------


async def test_in_scope_action_gets_a_token_sealing_type_and_perimeter() -> None:
    m = await _mandate(allowed_actions=["invoice.read", "invoice.pay"], max_amount="500")
    meta = {"amount": "120", "currency": "EUR"}
    res = await _token(
        m["mandate_id"],
        "agent:billing",
        action_type="invoice.pay",
        action_metadata_json=json.dumps(meta),
    )
    assert "token" in res, res
    claims = pyjwt.decode(
        res["token"], _public_key_pem(), algorithms=["EdDSA"], audience="runtime://erp"
    )
    assert claims["amr_action_type"] == "invoice.pay"
    assert claims["amr_perimeter_digest"] == Perimeter.model_validate(m["perimeter"]).digest()
    assert claims["amr_action_hash"] == _canonical_action_hash(
        "pay invoice 2026-118", "runtime://erp", meta, "invoice.pay"
    )
    assert claims["amr_action_hash"] != _canonical_action_hash(
        "pay invoice 2026-118", "runtime://erp", meta
    )


async def test_perimeter_requires_an_action_type() -> None:
    m = await _mandate(allowed_actions=["invoice.read"])
    res = await _token(m["mandate_id"], "agent:billing")
    assert res["denied"] is True
    assert res["reason"] == "action_type_required"


async def test_action_outside_allowed_actions_is_refused() -> None:
    m = await _mandate(allowed_actions=["invoice.read"])
    res = await _token(m["mandate_id"], "agent:billing", action_type="invoice.pay")
    assert res["reason"] == "action_out_of_scope"
    assert res["detail"] == "not_allowed:invoice.pay"
    assert res["refused_by"] == m["mandate_id"]


async def test_forbidden_action_is_refused() -> None:
    m = await _mandate(allowed_actions=["*"], forbidden_actions=["agent.create"])
    res = await _token(m["mandate_id"], "agent:billing", action_type="agent.create")
    assert res["reason"] == "action_out_of_scope"
    assert res["detail"] == "forbidden:agent.create"


async def test_amount_above_limit_is_refused() -> None:
    m = await _mandate(allowed_actions=["invoice.pay"], max_amount="500")
    res = await _token(
        m["mandate_id"],
        "agent:billing",
        action_type="invoice.pay",
        action_metadata_json=json.dumps({"amount": "900", "currency": "EUR"}),
    )
    assert res["reason"] == "action_out_of_scope"
    assert res["detail"] == "amount_above_limit:500 EUR"


async def test_free_text_mandate_still_works_without_action_type() -> None:
    m = await _mandate()
    assert m["perimeter"] is None
    res = await _token(m["mandate_id"], "agent:billing")
    assert "token" in res, res
    claims = pyjwt.decode(
        res["token"], _public_key_pem(), algorithms=["EdDSA"], audience="runtime://erp"
    )
    assert "amr_perimeter_digest" not in claims
    assert "amr_action_type" not in claims


async def test_invalid_perimeter_inputs() -> None:
    no_allowed = await _mandate(forbidden_actions=["agent.create"])
    assert no_allowed["code"] == "perimeter_invalid"
    empty_allowed = await _mandate(allowed_actions=[])
    assert empty_allowed["code"] == "perimeter_invalid"
    empty_allowed_currency = await _mandate(allowed_actions=[], currency="USD")
    assert empty_allowed_currency["code"] == "perimeter_invalid"
    bad_pattern = await _mandate(allowed_actions=["Invoice Pay"])
    assert bad_pattern["code"] == "perimeter_invalid"
    bad_amount = await _mandate(allowed_actions=["invoice.pay"], max_amount="-5")
    assert bad_amount["code"] == "perimeter_invalid"


async def test_free_text_hashes_are_unchanged(temp_db: Path) -> None:
    # Action descriptor without action_type: exactly the v1.0 canonical form.
    legacy = '{"action":"a","audience":"b","metadata":{}}'
    assert _canonical_action_hash("a", "b", {}) == hashlib.sha256(legacy.encode()).hexdigest()
    # Free-text mandate: the chain payload has no perimeter key at all.
    m = await _mandate()
    async with aiosqlite.connect(str(temp_db)) as db:
        db.row_factory = aiosqlite.Row
        row = await (
            await db.execute("SELECT * FROM mandates WHERE id = ?", (m["mandate_id"],))
        ).fetchone()
    legal = json.loads(row["legal_basis_json"])
    data = {
        "id": row["id"],
        "principal_id": row["principal_id"],
        "agent_id": row["agent_id"],
        "scope": row["scope"],
        "legal_basis_regulation": legal["regulation"],
        "legal_basis_article": legal["article"],
        "legal_basis_jurisdiction": legal["jurisdiction"],
        "duration_hours": 24,
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "parent_mandate_id": None,
    }
    assert compute_hash(data, "") == row["chain_hash"]
    assert row["perimeter_json"] is None


async def test_perimeter_is_sealed_in_the_mandate_chain_hash(temp_db: Path) -> None:
    m = await _mandate(allowed_actions=["invoice.read"], forbidden_actions=["agent.create"])
    async with aiosqlite.connect(str(temp_db)) as db:
        db.row_factory = aiosqlite.Row
        row = await (
            await db.execute("SELECT * FROM mandates WHERE id = ?", (m["mandate_id"],))
        ).fetchone()
    legal = json.loads(row["legal_basis_json"])
    data = {
        "id": row["id"],
        "principal_id": row["principal_id"],
        "agent_id": row["agent_id"],
        "scope": row["scope"],
        "legal_basis_regulation": legal["regulation"],
        "legal_basis_article": legal["article"],
        "legal_basis_jurisdiction": legal["jurisdiction"],
        "duration_hours": 24,
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "parent_mandate_id": None,
    }
    assert compute_hash(data, "") != row["chain_hash"]
    data["perimeter"] = json.loads(row["perimeter_json"])
    assert compute_hash(data, "") == row["chain_hash"]


# --- Delegation (sub-mandates) -------------------------------------------------------


async def _delegating_parent(**perimeter: object) -> dict:
    params: dict = {
        "allowed_actions": ["invoice.*", "agent.create"],
        "forbidden_actions": ["invoice.delete"],
        "delegation_allowed": True,
        "max_amount": "1000",
        "amount_actions": ["invoice.pay"],
    }
    params.update(perimeter)
    return await _mandate(agent_id="agent:lead", duration_hours=48, **params)


async def _sub(parent: dict, **overrides: object) -> dict:
    params: dict = {
        "principal_id": parent["agent_id"],
        "agent_id": "agent:helper",
        "parent_mandate_id": parent["mandate_id"],
        "allowed_actions": ["invoice.read"],
    }
    params.update(overrides)
    return await _mandate(**params)


async def test_sub_mandate_inherits_prohibitions_and_limit() -> None:
    parent = await _delegating_parent()
    child = await _sub(parent, allowed_actions=["invoice.read", "invoice.pay"])
    assert child["status"] == "created", child
    assert child["parent_mandate_id"] == parent["mandate_id"]
    assert child["perimeter"]["forbidden_actions"] == ["invoice.delete"]
    assert child["perimeter"]["max_amount"] == "1000"
    assert child["perimeter"]["amount_actions"] == ["invoice.pay"]
    assert child["perimeter"]["delegation_allowed"] is False


async def test_parent_without_perimeter_cannot_delegate() -> None:
    parent = await _mandate(agent_id="agent:lead")
    child = await _sub(parent)
    assert child["code"] == "delegation_not_allowed"


async def test_parent_forbidding_delegation_cannot_delegate() -> None:
    parent = await _delegating_parent(delegation_allowed=False)
    child = await _sub(parent)
    assert child["code"] == "delegation_not_allowed"


async def test_only_the_parent_agent_can_delegate() -> None:
    parent = await _delegating_parent()
    child = await _sub(parent, principal_id="org:someone-else")
    assert child["code"] == "delegator_mismatch"


async def test_sub_mandate_must_declare_a_perimeter() -> None:
    parent = await _delegating_parent()
    child = await _sub(parent, allowed_actions=None)
    assert child["code"] == "sub_mandate_requires_perimeter"


async def test_sub_mandate_cannot_widen_the_parent() -> None:
    parent = await _delegating_parent()
    wider = await _sub(parent, allowed_actions=["invoice.read", "bank.transfer"])
    assert wider["code"] == "perimeter_exceeds_parent"
    star = await _sub(parent, allowed_actions=["*"])
    assert star["code"] == "perimeter_exceeds_parent"


async def test_sub_mandate_limit_cannot_exceed_parent() -> None:
    parent = await _delegating_parent()
    higher = await _sub(parent, allowed_actions=["invoice.pay"], max_amount="5000")
    assert higher["code"] == "limit_exceeds_parent"
    other_currency = await _sub(
        parent, allowed_actions=["invoice.pay"], max_amount="10", currency="USD"
    )
    assert other_currency["code"] == "limit_exceeds_parent"


async def test_sub_mandate_cannot_outlive_parent() -> None:
    parent = await _delegating_parent()
    child = await _sub(parent, duration_hours=72)
    assert child["code"] == "expires_after_parent"


async def test_grandparent_revoked_blocks_new_and_existing_sub_mandates(temp_db: Path) -> None:
    root = await _delegating_parent()
    middle = await _sub(
        root, agent_id="agent:middle", allowed_actions=["invoice.*"], delegation_allowed=True
    )
    assert middle["status"] == "created", middle
    leaf = await _sub(middle, allowed_actions=["invoice.read"], duration_hours=12)
    assert leaf["status"] == "created", leaf
    async with aiosqlite.connect(str(temp_db)) as db:
        await db.execute(
            "UPDATE mandates SET status = 'revoked' WHERE id = ?", (root["mandate_id"],)
        )
        await db.commit()
    again = await _sub(middle, allowed_actions=["invoice.read"], duration_hours=12)
    assert again["code"] == "parent_mandate_revoked"
    res = await _token(leaf["mandate_id"], "agent:helper", action_type="invoice.read")
    assert res["reason"] == "parent_mandate_revoked"
    assert res["refused_by"] == root["mandate_id"]
    verified = json.loads(await verify_mandate("agent:helper", "read invoices"))
    assert verified["authorized"] is False
    assert "parent_mandate_revoked" in verified["reason"]


async def test_free_text_sub_mandate_is_cut_when_its_parent_expires(temp_db: Path) -> None:
    """Breaking change of v1.1: sub-mandates written before perimeters existed now
    require every parent to be active and unexpired."""
    parent_id, child_id = str(uuid4()), str(uuid4())
    await insert_mandate_directly(temp_db, parent_id, agent_id="agent:lead",
                                  hours_until_expiry=-1.0)
    await insert_mandate_directly(temp_db, child_id, principal_id="agent:lead",
                                  agent_id="agent:helper", hours_until_expiry=720,
                                  parent_mandate_id=parent_id)
    res = await _token(child_id, "agent:helper")
    assert res["reason"] == "parent_mandate_expired"
    assert res["refused_by"] == parent_id


async def test_parent_id_is_stored_in_canonical_form() -> None:
    parent = await _delegating_parent()
    child = await _sub(parent, parent_mandate_id=parent["mandate_id"].upper())
    assert child["status"] == "created", child
    assert child["parent_mandate_id"] == parent["mandate_id"]


async def test_unknown_parent_is_refused() -> None:
    child = await _mandate(
        principal_id="agent:lead",
        parent_mandate_id=str(uuid4()),
        allowed_actions=["invoice.read"],
    )
    assert child["code"] == "parent_mandate_not_found"


async def test_revoking_the_parent_cuts_the_sub_mandate(temp_db: Path) -> None:
    parent = await _delegating_parent()
    child = await _sub(parent)
    ok = await _token(child["mandate_id"], "agent:helper", action_type="invoice.read")
    assert "token" in ok, ok
    # Revocation is a status change on the parent (tests write it directly).
    async with aiosqlite.connect(str(temp_db)) as db:
        await db.execute(
            "UPDATE mandates SET status = 'revoked' WHERE id = ?", (parent["mandate_id"],)
        )
        await db.commit()
    res = await _token(
        child["mandate_id"], "agent:helper", action_type="invoice.read", action="read again"
    )
    assert res["reason"] == "parent_mandate_revoked"
    assert res["refused_by"] == parent["mandate_id"]


async def test_parent_perimeter_is_enforced_even_if_the_child_record_is_wider(
    temp_db: Path,
) -> None:
    parent = await _delegating_parent()
    rogue_id = str(uuid4())
    await insert_mandate_directly(
        temp_db,
        rogue_id,
        principal_id="agent:lead",
        agent_id="agent:helper",
        perimeter_json=Perimeter(allowed_actions=("*",)).to_json(),
        parent_mandate_id=parent["mandate_id"],
    )
    own = await _token(rogue_id, "agent:helper", action_type="bank.transfer")
    assert own["reason"] == "action_out_of_scope"
    assert own["refused_by"] == parent["mandate_id"]
    forbidden = await _token(rogue_id, "agent:helper", action_type="invoice.delete")
    assert forbidden["detail"] == "forbidden:invoice.delete"
    assert forbidden["refused_by"] == parent["mandate_id"]


async def test_practitioner_case_sub_agent_creation_despite_instruction() -> None:
    """An agent told not to create sub-agents gets no token for it (forbidden action)
    and cannot register a sub-mandate (its mandate does not grant delegation)."""
    m = await _mandate(
        agent_id="agent:assistant",
        allowed_actions=["report.*"],
        forbidden_actions=["agent.create"],
    )
    token = await _token(
        m["mandate_id"], "agent:assistant", action="spawn helper", action_type="agent.create"
    )
    assert token["denied"] is True
    assert token["detail"] == "forbidden:agent.create"
    sub = await _mandate(
        principal_id="agent:assistant",
        agent_id="agent:spawned",
        parent_mandate_id=m["mandate_id"],
        allowed_actions=["report.read"],
    )
    assert sub["code"] == "delegation_not_allowed"


# --- Visibility and migration ----------------------------------------------------------


async def test_verify_and_proof_show_the_perimeter() -> None:
    m = await _mandate(allowed_actions=["invoice.read"])
    verified = json.loads(await verify_mandate("agent:billing", "read invoices"))
    assert verified["perimeter"]["allowed_actions"] == ["invoice.read"]
    proof = json.loads(await get_proof(m["mandate_id"]))
    assert proof["mandate"]["perimeter"]["allowed_actions"] == ["invoice.read"]


OLD_ID = "00000000-0000-4000-8000-000000000001"


async def test_existing_database_is_upgraded_in_place(temp_db: Path) -> None:
    async with aiosqlite.connect(str(temp_db)) as db:
        await db.executescript(
            """
            CREATE TABLE mandates (
                id TEXT PRIMARY KEY, principal_id TEXT NOT NULL, agent_id TEXT NOT NULL,
                scope TEXT NOT NULL, legal_basis_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL, parent_mandate_id TEXT REFERENCES mandates(id),
                metadata_json TEXT NOT NULL DEFAULT '{}', chain_hash TEXT NOT NULL
            );
            INSERT INTO mandates VALUES (
                '00000000-0000-4000-8000-000000000001', 'p', 'agent:old', 's', '{}', 'active',
                '2026-01-01T00:00:00+00:00', '2999-01-01T00:00:00+00:00', NULL, '{}', 'h');
            """
        )
        await db.commit()
    await init_db(temp_db)
    async with aiosqlite.connect(str(temp_db)) as db:
        db.row_factory = aiosqlite.Row
        info = await (await db.execute("PRAGMA table_info(mandates)")).fetchall()
        cols = {r["name"] for r in info}
        old = await (
            await db.execute("SELECT * FROM mandates WHERE id = ?", (OLD_ID,))
        ).fetchone()
    assert "perimeter_json" in cols
    assert old["chain_hash"] == "h"
    assert old["perimeter_json"] is None
    res = await _token(OLD_ID, "agent:old")
    assert "token" in res, res
