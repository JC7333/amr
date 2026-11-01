"""Delegation depth fixed by the principal: max_delegation_depth on a mandate."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from amr.crypto.signing import generate_signing_key
from amr.models.perimeter import Perimeter
from amr.tools.create_mandate import create_mandate
from amr.tools.principal_keys import prepare_mandate_signature
from amr.tools.verify_mandate import verify_mandate
from tests._helpers import insert_mandate_directly

BASE = {
    "scope": "Run errands",
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


async def _make(
    principal: str, agent: str, parent: str | None = None, hours: float = 12.0, **kw: object
) -> dict:
    args: dict = {"allowed_actions": ["order.*"]}
    args.update(kw)
    return json.loads(await create_mandate(
        principal_id=principal, agent_id=agent, duration_hours=hours,
        parent_mandate_id=parent, **BASE, **args,
    ))


async def _chain(root_depth: int | None, levels: int) -> list[dict]:
    """Root plus ``levels`` sub-mandates, each allowed to delegate further."""
    root = await _make(
        "org:p", "agent:0", hours=48.0, delegation_allowed=True, max_delegation_depth=root_depth
    )
    assert root["status"] == "created", root
    out = [root]
    for i in range(1, levels + 1):
        child = await _make(
            f"agent:{i - 1}", f"agent:{i}", out[-1]["mandate_id"],
            hours=48.0 - 6 * i, delegation_allowed=True,
        )
        assert child.get("status") == "created", child
        out.append(child)
    return out


# --- model -----------------------------------------------------------------


def test_unset_depth_keeps_exact_canonical_form() -> None:
    p = Perimeter(allowed_actions=("a.b",), delegation_allowed=True)
    assert "max_delegation_depth" not in p.canonical()
    assert p.max_delegation_depth is None


def test_depth_is_sealed_in_canonical_form_and_digest() -> None:
    a = Perimeter(allowed_actions=("a.b",), delegation_allowed=True, max_delegation_depth=2)
    b = Perimeter(allowed_actions=("a.b",), delegation_allowed=True, max_delegation_depth=3)
    assert a.canonical()["max_delegation_depth"] == 2
    assert a.digest() != b.digest()
    assert Perimeter.from_json(a.to_json()) == a


def test_depth_requires_delegation_allowed() -> None:
    with pytest.raises(ValidationError, match="requires delegation_allowed"):
        Perimeter(allowed_actions=("a.b",), max_delegation_depth=1)


@pytest.mark.parametrize("bad", [0, -1, 17, True, 1.5, "2"])
def test_depth_must_be_an_int_from_1_to_16(bad: object) -> None:
    with pytest.raises(ValidationError):
        Perimeter(allowed_actions=("a.b",), delegation_allowed=True, max_delegation_depth=bad)


@pytest.mark.parametrize("ok", [1, 16])
def test_depth_bounds_are_accepted(ok: int) -> None:
    p = Perimeter(allowed_actions=("a.b",), delegation_allowed=True, max_delegation_depth=ok)
    assert p.max_delegation_depth == ok


# --- enforcement -------------------------------------------------------------


async def test_depth_one_allows_a_child_but_not_a_grandchild() -> None:
    chain = await _chain(root_depth=1, levels=1)
    assert chain[1]["status"] == "created", chain[1]
    grand = await _make("agent:1", "agent:2", chain[1]["mandate_id"], hours=20.0)
    assert grand["code"] == "delegation_depth_exceeded"
    assert chain[0]["mandate_id"] in grand["error"]


async def test_depth_two_allows_a_grandchild_but_not_a_great_grandchild() -> None:
    chain = await _chain(root_depth=2, levels=2)
    assert chain[2]["status"] == "created"
    great = await _make("agent:2", "agent:3", chain[2]["mandate_id"], hours=20.0)
    assert great["code"] == "delegation_depth_exceeded"


async def test_no_depth_keeps_unlimited_behaviour() -> None:
    chain = await _chain(root_depth=None, levels=4)
    assert all(m["status"] == "created" for m in chain)


async def test_a_lower_ancestor_limit_applies_even_when_the_root_has_none() -> None:
    root = await _make("org:p", "agent:0", hours=48.0, delegation_allowed=True)
    mid = await _make(
        "agent:0", "agent:1", root["mandate_id"], hours=40.0,
        delegation_allowed=True, max_delegation_depth=1,
    )
    assert mid["status"] == "created"
    low = await _make(
        "agent:1", "agent:2", mid["mandate_id"], hours=30.0, delegation_allowed=True
    )
    assert low["status"] == "created"
    deeper = await _make("agent:2", "agent:3", low["mandate_id"], hours=20.0)
    assert deeper["code"] == "delegation_depth_exceeded"
    assert mid["mandate_id"] in deeper["error"]


async def test_a_child_cannot_widen_what_its_parent_allows() -> None:
    chain = await _chain(root_depth=1, levels=0)
    child = await _make(
        "agent:0", "agent:1", chain[0]["mandate_id"], hours=40.0,
        delegation_allowed=True, max_delegation_depth=10,
    )
    assert child["status"] == "created"
    grand = await _make("agent:1", "agent:2", child["mandate_id"], hours=30.0)
    assert grand["code"] == "delegation_depth_exceeded"


async def test_refused_sub_mandate_is_not_written() -> None:
    chain = await _chain(root_depth=1, levels=1)
    await _make("agent:1", "agent:2", chain[1]["mandate_id"], hours=20.0)
    verdict = json.loads(await verify_mandate(agent_id="agent:2", action="order.place"))
    assert verdict["authorized"] is False


async def test_other_refusals_still_apply_within_the_depth() -> None:
    chain = await _chain(root_depth=2, levels=1)
    wrong_delegator = await _make("agent:9", "agent:2", chain[1]["mandate_id"], hours=20.0)
    assert wrong_delegator["code"] == "delegator_mismatch"
    too_long = await _make("agent:1", "agent:2", chain[1]["mandate_id"], hours=47.0)
    assert too_long["code"] == "expires_after_parent"


async def test_depth_without_delegation_is_refused_at_creation() -> None:
    result = await _make("org:p", "agent:0", max_delegation_depth=1)
    assert result["code"] == "perimeter_invalid"


async def test_depth_alone_asks_for_a_perimeter() -> None:
    result = json.loads(await create_mandate(
        principal_id="org:p", agent_id="agent:0", duration_hours=1.0,
        max_delegation_depth=1, **BASE,
    ))
    assert result["code"] == "perimeter_invalid"


async def test_depth_is_returned_in_the_recorded_perimeter() -> None:
    root = await _make("org:p", "agent:0", delegation_allowed=True, max_delegation_depth=3)
    assert root["perimeter"]["max_delegation_depth"] == 3


async def test_prepare_signature_binds_the_depth() -> None:
    kw = dict(
        principal_id="org:p", agent_id="agent:0", duration_hours=1.0,
        allowed_actions=["a.b"], delegation_allowed=True, signed_at="2026-11-01T10:00:00+00:00",
        **BASE,
    )
    one = json.loads(await prepare_mandate_signature(max_delegation_depth=1, **kw))
    two = json.loads(await prepare_mandate_signature(max_delegation_depth=2, **kw))
    none = json.loads(await prepare_mandate_signature(**kw))
    assert len({one["payload"], two["payload"], none["payload"]}) == 3


async def test_a_limit_above_a_mandate_without_perimeter_still_applies(temp_db: Path) -> None:
    perim = Perimeter(
        allowed_actions=("order.*",), delegation_allowed=True, max_delegation_depth=2
    ).to_json()
    open_perim = Perimeter(allowed_actions=("order.*",), delegation_allowed=True).to_json()
    await insert_mandate_directly(
        temp_db, "00000000-0000-4000-8000-0000000000a1", principal_id="org:p", agent_id="agent:0",
        hours_until_expiry=48.0, perimeter_json=perim,
    )
    await insert_mandate_directly(
        temp_db, "00000000-0000-4000-8000-0000000000a2", principal_id="agent:0", agent_id="agent:1",
        hours_until_expiry=40.0, parent_mandate_id="00000000-0000-4000-8000-0000000000a1",
    )
    await insert_mandate_directly(
        temp_db, "00000000-0000-4000-8000-0000000000a3", principal_id="agent:1", agent_id="agent:2",
        hours_until_expiry=30.0, parent_mandate_id="00000000-0000-4000-8000-0000000000a2", perimeter_json=open_perim,
    )
    refused = await _make("agent:2", "agent:3", "00000000-0000-4000-8000-0000000000a3", hours=20.0)
    assert refused.get("code") == "delegation_depth_exceeded", refused
    assert refused["code"] == "delegation_depth_exceeded"
    assert "0000000000a1" in refused["error"]
