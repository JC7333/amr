"""Cumulative amount ceiling over a rolling period, enforced on the whole delegation branch."""

import asyncio
import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from pydantic import ValidationError

from amr.crypto.principal import b64url_encode, key_registration_payload
from amr.crypto.signing import generate_signing_key
from amr.db.engine import init_db
from amr.models.perimeter import Perimeter, PerimeterError
from amr.proof.insurer_dossier import _perimeter_rows
from amr.tools import issue_action_token as issue_module
from amr.tools.create_mandate import create_mandate
from amr.tools.get_proof import get_proof
from amr.tools.issue_action_token import issue_action_token
from amr.tools.principal_keys import prepare_mandate_signature, register_principal_key
from amr.tools.verify_mandate import verify_mandate

PRINCIPAL = "org:clinic"
AGENT = "agent:buyer"
HELPER = "agent:helper"

BASE = {
    "scope": "Buy supplies",
    "legal_basis_regulation": "Mandate contract",
    "legal_basis_article": "Clause 1",
}


@pytest.fixture(autouse=True)
def isolated_signing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    priv = tmp_path / "test_key.pem"
    pub = tmp_path / "test_key.pub"
    monkeypatch.setattr("amr.config.settings.signing_key_path", priv)
    monkeypatch.setattr("amr.config.settings.public_key_path", pub)
    generate_signing_key(priv, pub)


async def _root(**perimeter: object) -> dict:
    args: dict = {
        "allowed_actions": ["order.*"],
        "delegation_allowed": True,
        "period_max_amount": "100",
        "period_days": 30,
    }
    args.update(perimeter)
    result = json.loads(await create_mandate(
        principal_id=PRINCIPAL, agent_id=AGENT, duration_hours=24.0, **BASE, **args,
    ))
    assert result.get("status") == "created", result
    return result


async def _child(parent_id: str, **perimeter: object) -> dict:
    args: dict = {"allowed_actions": ["order.place"]}
    args.update(perimeter)
    result = json.loads(await create_mandate(
        principal_id=AGENT, agent_id=HELPER, duration_hours=12.0,
        parent_mandate_id=parent_id, **BASE, **args,
    ))
    assert result.get("status") == "created", result
    return result


async def _spend(
    mandate_id: str,
    amount: str | None,
    agent_id: str = AGENT,
    action_type: str = "order.place",
    currency: str = "EUR",
) -> dict:
    metadata = {} if amount is None else {"amount": amount, "currency": currency}
    return json.loads(await issue_action_token(
        mandate_id=mandate_id,
        agent_id=agent_id,
        action=f"order {uuid4()}",
        audience="runtime://shop",
        action_metadata_json=json.dumps(metadata),
        action_type=action_type,
    ))


def _ok(result: dict) -> None:
    assert "token" in result, result


def _refused(result: dict, refused_by: str, detail: str = "period_amount_above_limit:100 EUR/30d"):
    assert result.get("denied") is True, result
    assert result["reason"] == "action_out_of_scope"
    assert result["detail"] == detail
    assert result["refused_by"] == refused_by


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


def test_perimeter_without_ceiling_keeps_its_exact_canonical_form() -> None:
    p = Perimeter(allowed_actions=("order.place",), max_amount="50", amount_actions=("order.*",))
    legacy = {
        "allowed_actions": ["order.place"],
        "forbidden_actions": [],
        "delegation_allowed": False,
        "max_amount": "50",
        "currency": "EUR",
        "amount_actions": ["order.*"],
    }
    assert p.canonical() == legacy
    expected = hashlib.sha256(
        json.dumps(legacy, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert p.digest() == expected


def test_ceiling_is_in_the_canonical_form_and_round_trips() -> None:
    p = Perimeter(allowed_actions=("order.place",), period_max_amount="2000.50", period_days=30)
    canonical = p.canonical()
    assert canonical["period_max_amount"] == "2000.5"
    assert canonical["period_days"] == 30
    assert Perimeter.from_json(p.to_json()) == p
    assert Perimeter.from_json(p.to_json()).digest() == p.digest()


@pytest.mark.parametrize(
    "fields",
    [
        {"period_max_amount": "100"},
        {"period_days": 30},
        {"period_max_amount": "100", "period_days": 0},
        {"period_max_amount": "100", "period_days": 367},
        {"period_max_amount": "100", "period_days": "30"},
        {"period_max_amount": "100", "period_days": 7.5},
        {"period_max_amount": "0", "period_days": 30},
        {"period_max_amount": "1e3", "period_days": 30},
        {"period_max_amount": "-5", "period_days": 30},
    ],
)
def test_invalid_ceiling_is_refused(fields: dict) -> None:
    with pytest.raises(ValidationError):
        Perimeter(allowed_actions=("order.place",), **fields)


def test_amount_actions_accept_a_cumulative_ceiling_alone() -> None:
    Perimeter(
        allowed_actions=("order.*",), amount_actions=("order.place",),
        period_max_amount="100", period_days=7,
    )
    with pytest.raises(ValidationError):
        Perimeter(allowed_actions=("order.*",), amount_actions=("order.place",))


def test_cumulative_ceiling_alone_requires_an_amount() -> None:
    p = Perimeter(allowed_actions=("order.*",), period_max_amount="100", period_days=7)
    assert p.check_action("order.place", {}) == "amount_required"
    assert p.check_action("order.place", {"amount": "1,5", "currency": "EUR"}) == "amount_invalid"
    assert p.check_action("order.place", {"amount": "5"}) == "currency_required"
    assert p.check_action("order.place", {"amount": "5", "currency": "USD"}) == (
        "currency_mismatch:EUR"
    )
    assert p.check_action("order.place", {"amount": "100", "currency": "EUR"}) is None
    assert p.check_action("order.place", {"amount": "100.01", "currency": "EUR"}) == (
        "period_amount_above_limit:100 EUR/7d"
    )


def test_child_ceiling_above_the_parent_ceiling_is_refused() -> None:
    parent = Perimeter(
        allowed_actions=("order.*",), delegation_allowed=True,
        period_max_amount="100", period_days=30,
    )
    child = Perimeter(allowed_actions=("order.place",), period_max_amount="101", period_days=1)
    with pytest.raises(PerimeterError) as exc:
        child.narrowed_by(parent)
    assert exc.value.code == "limit_exceeds_parent"
    lower = Perimeter(allowed_actions=("order.place",), period_max_amount="100", period_days=1)
    assert lower.narrowed_by(parent).period_max_amount == lower.period_max_amount


def test_child_limit_in_another_currency_than_the_parent_ceiling_is_refused() -> None:
    parent = Perimeter(
        allowed_actions=("order.*",), delegation_allowed=True,
        period_max_amount="100", period_days=30,
    )
    for child in (
        Perimeter(allowed_actions=("order.place",), max_amount="10", currency="USD"),
        Perimeter(
            allowed_actions=("order.place",), period_max_amount="10", period_days=1,
            currency="USD",
        ),
    ):
        with pytest.raises(PerimeterError) as exc:
            child.narrowed_by(parent)
        assert exc.value.code == "limit_exceeds_parent"


def test_child_ceiling_under_a_parent_per_action_limit_keeps_its_own_actions() -> None:
    parent = Perimeter(
        allowed_actions=("order.*",), delegation_allowed=True,
        max_amount="50", amount_actions=("order.pay",),
    )
    child = Perimeter(
        allowed_actions=("order.*",), amount_actions=("order.place",),
        period_max_amount="80", period_days=7,
    )
    effective = child.narrowed_by(parent)
    assert effective.max_amount == parent.max_amount
    assert set(effective.amount_actions) == {"order.pay", "order.place"}
    assert effective.period_max_amount == child.period_max_amount
    assert effective.period_days == 7


def test_child_without_limit_still_inherits_the_parent_per_action_limit_as_before() -> None:
    parent = Perimeter(
        allowed_actions=("order.*",), delegation_allowed=True,
        max_amount="50", amount_actions=("order.pay",),
    )
    child = Perimeter(allowed_actions=("order.place",), amount_actions=())
    effective = child.narrowed_by(parent)
    assert effective.amount_actions == ("order.pay",)
    assert effective.period_max_amount is None
    assert "period_max_amount" not in effective.canonical()


# ---------------------------------------------------------------------------
# Token issuance
# ---------------------------------------------------------------------------


async def test_tokens_are_issued_up_to_the_ceiling_and_not_beyond() -> None:
    root = await _root()
    _ok(await _spend(root["mandate_id"], "60"))
    _ok(await _spend(root["mandate_id"], "40"))
    _refused(await _spend(root["mandate_id"], "0.01"), root["mandate_id"])


async def test_a_single_action_above_the_ceiling_is_refused() -> None:
    root = await _root()
    _refused(await _spend(root["mandate_id"], "100.5"), root["mandate_id"])


async def test_a_refused_token_does_not_consume_the_ceiling() -> None:
    root = await _root()
    _ok(await _spend(root["mandate_id"], "70"))
    _refused(await _spend(root["mandate_id"], "50"), root["mandate_id"])
    _ok(await _spend(root["mandate_id"], "30"))


async def test_spending_by_a_sub_mandate_counts_against_the_parent_ceiling() -> None:
    root = await _root()
    child = await _child(root["mandate_id"])
    assert "period_max_amount" not in child["perimeter"]
    _ok(await _spend(child["mandate_id"], "70", agent_id=HELPER))
    _refused(await _spend(root["mandate_id"], "40"), root["mandate_id"])
    _refused(await _spend(child["mandate_id"], "40", agent_id=HELPER), root["mandate_id"])
    _ok(await _spend(child["mandate_id"], "30", agent_id=HELPER))


async def test_a_grandchild_counts_against_every_ceiling_above_it() -> None:
    root = await _root()
    child = await _child(
        root["mandate_id"], allowed_actions=["order.place"], delegation_allowed=True,
        period_max_amount="50", period_days=7,
    )
    grandchild = json.loads(await create_mandate(
        principal_id=HELPER, agent_id="agent:sub", duration_hours=6.0,
        parent_mandate_id=child["mandate_id"], allowed_actions=["order.place"], **BASE,
    ))
    assert grandchild.get("status") == "created", grandchild
    _ok(await _spend(grandchild["mandate_id"], "45", agent_id="agent:sub"))
    _refused(
        await _spend(grandchild["mandate_id"], "10", agent_id="agent:sub"),
        child["mandate_id"],
        "period_amount_above_limit:50 EUR/7d",
    )
    _ok(await _spend(root["mandate_id"], "50"))
    _refused(await _spend(root["mandate_id"], "10"), root["mandate_id"])


async def test_a_sibling_branch_does_not_spend_another_branch_ceiling() -> None:
    root = await _root(period_max_amount="1000")
    first = await _child(root["mandate_id"], period_max_amount="50", period_days=30)
    second = await _child(root["mandate_id"], period_max_amount="50", period_days=30)
    _ok(await _spend(first["mandate_id"], "50", agent_id=HELPER))
    _ok(await _spend(second["mandate_id"], "50", agent_id=HELPER))


async def test_only_tokens_inside_the_window_count(temp_db: Path) -> None:
    root = await _root()
    _ok(await _spend(root["mandate_id"], "90"))
    _refused(await _spend(root["mandate_id"], "20"), root["mandate_id"])
    # Test-only: age the recorded spending past the 30-day window.
    with sqlite3.connect(temp_db) as conn:
        changed = conn.execute(
            "UPDATE token_amounts SET issued_at = ?",
            ((datetime.now(UTC) - timedelta(days=30, minutes=1)).isoformat(),),
        ).rowcount
    assert changed == 1
    _ok(await _spend(root["mandate_id"], "20"))


async def test_tokens_just_inside_the_window_still_count(temp_db: Path) -> None:
    root = await _root()
    _ok(await _spend(root["mandate_id"], "90"))
    with sqlite3.connect(temp_db) as conn:
        conn.execute(
            "UPDATE token_amounts SET issued_at = ?",
            ((datetime.now(UTC) - timedelta(days=29, hours=23)).isoformat(),),
        )
    _refused(await _spend(root["mandate_id"], "20"), root["mandate_id"])


async def test_actions_outside_amount_actions_without_amount_do_not_count() -> None:
    root = await _root(allowed_actions=["order.*"], amount_actions=["order.place"])
    for _ in range(3):
        _ok(await _spend(root["mandate_id"], None, action_type="order.read"))
    _ok(await _spend(root["mandate_id"], "100"))
    _refused(await _spend(root["mandate_id"], "1", action_type="order.read"), root["mandate_id"])


async def test_an_amount_action_without_amount_is_refused() -> None:
    root = await _root()
    result = await _spend(root["mandate_id"], None)
    assert result.get("denied") is True and result["detail"] == "amount_required", result


async def test_a_replayed_action_is_not_counted_twice(temp_db: Path) -> None:
    root = await _root()
    metadata = json.dumps({"amount": "60", "currency": "EUR"})
    params = {
        "mandate_id": root["mandate_id"], "agent_id": AGENT, "action": "order 42",
        "audience": "runtime://shop", "action_metadata_json": metadata,
        "action_type": "order.place",
    }
    _ok(json.loads(await issue_action_token(**params)))
    replay = json.loads(await issue_action_token(**params))
    assert replay["reason"] == "replay_detected_active_token_exists"
    with sqlite3.connect(temp_db) as conn:
        rows = conn.execute("SELECT amount, currency FROM token_amounts").fetchall()
    assert rows == [("60", "EUR")]
    _ok(await _spend(root["mandate_id"], "40"))


async def test_each_token_amount_is_recorded_against_its_whole_chain(temp_db: Path) -> None:
    root = await _root()
    child = await _child(root["mandate_id"])
    token = await _spend(child["mandate_id"], "12.50", agent_id=HELPER)
    _ok(token)
    with sqlite3.connect(temp_db) as conn:
        rows = conn.execute(
            "SELECT jti, mandate_id, amount, currency FROM token_amounts ORDER BY mandate_id"
        ).fetchall()
    assert sorted(rows) == sorted([
        (token["jti"], root["mandate_id"], "12.50", "EUR"),
        (token["jti"], child["mandate_id"], "12.50", "EUR"),
    ])


async def test_concurrent_requests_cannot_both_spend_the_remainder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = await _root()
    real_spend = issue_module.get_period_spend

    async def slow_spend(*args: object) -> Decimal:
        # Widen the gap between the read and the insert, so that without the write
        # lock every request would read the same, empty, spending.
        spent = await real_spend(*args)
        await asyncio.sleep(0.05)
        return spent

    monkeypatch.setattr(issue_module, "get_period_spend", slow_spend)
    results = await asyncio.gather(*(_spend(root["mandate_id"], "60") for _ in range(4)))
    issued = [r for r in results if "token" in r]
    refused = [r for r in results if r.get("denied")]
    assert len(issued) == 1, results
    assert len(refused) == 3
    assert all(r["detail"] == "period_amount_above_limit:100 EUR/30d" for r in refused)


async def test_mandates_without_ceiling_issue_tokens_as_before() -> None:
    result = json.loads(await create_mandate(
        principal_id=PRINCIPAL, agent_id=AGENT, duration_hours=24.0,
        allowed_actions=["order.*"], max_amount="100", **BASE,
    ))
    assert set(result["perimeter"]) == {
        "allowed_actions", "forbidden_actions", "delegation_allowed",
        "max_amount", "currency", "amount_actions",
    }
    for _ in range(5):
        _ok(await _spend(result["mandate_id"], "100"))


# ---------------------------------------------------------------------------
# Mandate creation, signature, proof, schema
# ---------------------------------------------------------------------------


async def test_ceiling_is_returned_and_shown_by_verify_mandate() -> None:
    root = await _root(period_max_amount="250.00", period_days=7)
    assert root["perimeter"]["period_max_amount"] == "250"
    assert root["perimeter"]["period_days"] == 7
    verified = json.loads(await verify_mandate(AGENT, "buy supplies"))
    shown = json.dumps(verified)
    assert '"period_max_amount": "250"' in shown and '"period_days": 7' in shown


@pytest.mark.parametrize(
    ("fields", "code"),
    [
        ({"period_max_amount": "100"}, "perimeter_invalid"),
        ({"period_days": 30}, "perimeter_invalid"),
        ({"period_max_amount": "abc", "period_days": 30}, "perimeter_invalid"),
    ],
)
async def test_create_mandate_refuses_an_incomplete_ceiling(fields: dict, code: str) -> None:
    result = json.loads(await create_mandate(
        principal_id=PRINCIPAL, agent_id=AGENT, duration_hours=24.0,
        allowed_actions=["order.*"], **BASE, **fields,
    ))
    assert result.get("code") == code, result


async def test_a_ceiling_alone_asks_for_a_perimeter() -> None:
    result = json.loads(await create_mandate(
        principal_id=PRINCIPAL, agent_id=AGENT, duration_hours=24.0,
        period_max_amount="100", period_days=30, **BASE,
    ))
    assert result.get("code") == "perimeter_invalid", result
    assert "allowed_actions is required" in result["error"]


async def test_sub_mandate_ceiling_above_the_parent_is_refused() -> None:
    root = await _root()
    result = json.loads(await create_mandate(
        principal_id=AGENT, agent_id=HELPER, duration_hours=12.0,
        parent_mandate_id=root["mandate_id"], allowed_actions=["order.place"],
        period_max_amount="150", period_days=1, **BASE,
    ))
    assert result.get("code") == "limit_exceeds_parent", result


def _new_key() -> ed25519.Ed25519PrivateKey:
    return ed25519.Ed25519PrivateKey.generate()


def _pub(key: ed25519.Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return b64url_encode(raw)


async def _register(key: ed25519.Ed25519PrivateKey, principal_id: str) -> None:
    proof = b64url_encode(key.sign(key_registration_payload(principal_id, _pub(key))))
    result = json.loads(await register_principal_key(principal_id, _pub(key), proof))
    assert "error" not in result, result


async def test_signed_mandate_covers_the_ceiling() -> None:
    key = _new_key()
    await _register(key, PRINCIPAL)
    args = {
        "principal_id": PRINCIPAL, "agent_id": AGENT, "duration_hours": 24.0, **BASE,
        "allowed_actions": ["order.*"], "period_max_amount": "100", "period_days": 30,
    }
    prepared = json.loads(await prepare_mandate_signature(**args))
    assert '"period_days":30' in prepared["payload"]
    assert '"period_max_amount":"100"' in prepared["payload"]
    signature = b64url_encode(key.sign(prepared["payload"].encode("utf-8")))
    signed = {**args, "principal_signature": signature, "signed_at": prepared["signed_at"]}
    widened = json.loads(await create_mandate(**{**signed, "period_days": 31}))
    assert widened.get("code") == "principal_signature_invalid", widened
    raised = json.loads(await create_mandate(**{**signed, "period_max_amount": "1000"}))
    assert raised.get("code") == "principal_signature_invalid", raised
    created = json.loads(await create_mandate(**signed))
    assert created.get("status") == "created", created


async def test_unsigned_payload_without_ceiling_has_no_ceiling_keys() -> None:
    prepared = json.loads(await prepare_mandate_signature(
        principal_id=PRINCIPAL, agent_id=AGENT, duration_hours=24.0, **BASE,
        allowed_actions=["order.*"], max_amount="10",
    ))
    assert "period_" not in prepared["payload"]


async def test_proof_of_a_signed_sub_mandate_with_a_ceiling_stays_valid() -> None:
    root = await _root()
    key = _new_key()
    await _register(key, AGENT)
    args = {
        "principal_id": AGENT, "agent_id": HELPER, "duration_hours": 12.0, **BASE,
        "parent_mandate_id": root["mandate_id"], "allowed_actions": ["order.place"],
        "period_max_amount": "40", "period_days": 7,
    }
    prepared = json.loads(await prepare_mandate_signature(**args))
    signature = b64url_encode(key.sign(prepared["payload"].encode("utf-8")))
    child = json.loads(await create_mandate(
        **args, principal_signature=signature, signed_at=prepared["signed_at"]
    ))
    assert child.get("status") == "created", child
    proof = json.loads(await get_proof(child["mandate_id"]))
    assert proof["chain_integrity"]["principal_signature_valid"] is True, proof


async def test_schema_version_7_is_recorded(temp_db: Path) -> None:
    await init_db(temp_db)
    await init_db(temp_db)
    with sqlite3.connect(temp_db) as conn:
        versions = {row[0] for row in conn.execute("SELECT version FROM schema_version")}
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
    assert 7 in versions
    assert "token_amounts" in tables


def test_insurer_dossier_shows_the_ceiling() -> None:
    with_ceiling = dict(_perimeter_rows(
        Perimeter(allowed_actions=("order.*",), period_max_amount="100", period_days=30)
        .canonical()
    ))
    assert with_ceiling["Cumulative amount limit"].startswith("100 EUR per 30 days")
    without = dict(_perimeter_rows(Perimeter(allowed_actions=("order.*",)).canonical()))
    assert without["Cumulative amount limit"] == "none"


def test_template_kwargs_carry_a_cumulative_ceiling() -> None:
    from amr.templates import get_template

    sante = get_template("agent-sante-rgpd")
    assert not any(k.startswith("period_") for k in sante.create_mandate_kwargs())
    capped = sante.model_copy(update={"perimeter": sante.perimeter.model_copy(
        update={"period_max_amount": Decimal("300"), "period_days": 30}
    )})
    kwargs = capped.create_mandate_kwargs()
    assert kwargs["period_max_amount"] == "300"
    assert kwargs["period_days"] == 30



async def test_tiny_amounts_cannot_slip_past_a_huge_ceiling_by_rounding() -> None:
    root = await _root(period_max_amount="100000000000000000")
    _ok(await _spend(root["mandate_id"], "100000000000000000"))
    _refused(
        await _spend(root["mandate_id"], "0.000000000000000001"),
        root["mandate_id"],
        "period_amount_above_limit:100000000000000000 EUR/30d",
    )


async def test_a_v6_database_upgrades_and_enforces_the_ceiling(temp_db: Path) -> None:
    await init_db(temp_db)
    # Test-only: bring the database back to schema v6 (no token_amounts table).
    with sqlite3.connect(temp_db) as conn:
        conn.execute("DROP TABLE token_amounts")
        conn.execute("DELETE FROM schema_version WHERE version = 7")
    root = await _root()
    _ok(await _spend(root["mandate_id"], "100"))
    _refused(await _spend(root["mandate_id"], "1"), root["mandate_id"])
    with sqlite3.connect(temp_db) as conn:
        assert 7 in {row[0] for row in conn.execute("SELECT version FROM schema_version")}


async def test_the_recorded_spending_is_summed_without_rounding() -> None:
    root = await _root(period_max_amount="100000000000000000")
    _ok(await _spend(root["mandate_id"], "50000000000000000.000000000000000001"))
    _refused(
        await _spend(root["mandate_id"], "50000000000000000"),
        root["mandate_id"],
        "period_amount_above_limit:100000000000000000 EUR/30d",
    )
