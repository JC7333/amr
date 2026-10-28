"""Risk classes: the principal bounds token lifetime by action, along the whole chain."""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from pydantic import ValidationError

from amr.attestation import verify_attestation
from amr.crypto.chain import compute_hash
from amr.crypto.principal import b64url_encode, key_registration_payload
from amr.crypto.signing import generate_signing_key
from amr.models.perimeter import MAX_RISK_CLASSES, Perimeter, RiskClass
from amr.templates import AGENT_SANTE_RGPD
from amr.tools.create_mandate import create_mandate
from amr.tools.export_insurer_dossier import export_insurer_dossier
from amr.tools.get_proof import get_proof
from amr.tools.issue_action_token import issue_action_token
from amr.tools.issue_mandate_attestation import (
    get_registry_public_key,
    issue_mandate_attestation,
)
from amr.tools.principal_keys import prepare_mandate_signature, register_principal_key
from amr.tools.verify_mandate import verify_mandate

PRINCIPAL = "org:clinic"
AGENT = "agent:billing"
HELPER = "agent:helper"

IRREVERSIBLE = {"name": "irreversible", "actions": ["invoice.pay"], "max_token_seconds": 30}

BASE = {
    "principal_id": PRINCIPAL,
    "agent_id": AGENT,
    "scope": "Handle supplier invoices",
    "legal_basis_regulation": "Mandate contract",
    "legal_basis_article": "Clause 1",
    "duration_hours": 24.0,
}


@pytest.fixture(autouse=True)
def isolated_signing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    priv = tmp_path / "test_key.pem"
    pub = tmp_path / "test_key.pub"
    monkeypatch.setattr("amr.config.settings.signing_key_path", priv)
    monkeypatch.setattr("amr.config.settings.public_key_path", pub)
    generate_signing_key(priv, pub)


async def _create(**overrides: object) -> dict:
    params: dict = {**BASE, "allowed_actions": ["invoice.*"], **overrides}
    return json.loads(await create_mandate(**params))


async def _root(**overrides: object) -> dict:
    result = await _create(**overrides)
    assert result.get("status") == "created", result
    return result


async def _child(parent_id: str, **overrides: object) -> dict:
    params: dict = {
        "principal_id": AGENT,
        "agent_id": HELPER,
        "scope": "Pay and read invoices",
        "legal_basis_regulation": "Service contract",
        "legal_basis_article": "Clause 4",
        "duration_hours": 12.0,
        "parent_mandate_id": parent_id,
        "allowed_actions": ["invoice.read", "invoice.pay"],
    }
    params.update(overrides)
    result = json.loads(await create_mandate(**params))
    assert result.get("status") == "created", result
    return result


async def _token(mandate_id: str, action_type: str, agent_id: str = AGENT, **kw: object) -> dict:
    params: dict = {
        "mandate_id": mandate_id,
        "agent_id": agent_id,
        "action": f"{action_type} {uuid4()}",
        "audience": "runtime://erp",
        "action_type": action_type,
    }
    params.update(kw)
    result = json.loads(await issue_action_token(**params))
    assert "token" in result, result
    return result


def _claims(token: dict) -> dict:
    return jwt.decode(token["token"], options={"verify_signature": False})


def _lifetime(token: dict) -> int:
    claims = _claims(token)
    return claims["exp"] - claims["iat"]


# --- Model --------------------------------------------------------------------------


def test_perimeter_without_classes_keeps_its_canonical_form() -> None:
    perimeter = Perimeter(allowed_actions=("invoice.*",), forbidden_actions=("agent.create",))
    assert set(perimeter.canonical()) == {
        "allowed_actions",
        "forbidden_actions",
        "delegation_allowed",
        "max_amount",
        "currency",
        "amount_actions",
    }
    # Digest of this perimeter before risk classes existed (frozen value).
    legacy = json.dumps(
        {
            "allowed_actions": ["invoice.*"],
            "amount_actions": [],
            "currency": "EUR",
            "delegation_allowed": False,
            "forbidden_actions": ["agent.create"],
            "max_amount": None,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    assert perimeter.to_json() == legacy


def test_classes_are_canonical_sorted_and_deduplicated() -> None:
    perimeter = Perimeter(
        allowed_actions=("invoice.*",),
        risk_classes=(
            {"name": "sensitive", "actions": ["invoice.read", "invoice.read"],
             "max_token_seconds": 120},
            {"name": "irreversible", "actions": ["invoice.pay", "invoice.cancel"],
             "max_token_seconds": 30},
        ),
    )
    assert perimeter.canonical()["risk_classes"] == [
        {"name": "irreversible", "actions": ["invoice.cancel", "invoice.pay"],
         "max_token_seconds": 30},
        {"name": "sensitive", "actions": ["invoice.read"], "max_token_seconds": 120},
    ]


def test_order_of_classes_does_not_change_the_digest() -> None:
    a = {"name": "a", "actions": ["invoice.pay"], "max_token_seconds": 10}
    b = {"name": "b", "actions": ["invoice.read"], "max_token_seconds": 20}
    one = Perimeter(allowed_actions=("invoice.*",), risk_classes=(a, b))
    two = Perimeter(allowed_actions=("invoice.*",), risk_classes=(b, a))
    assert one.digest() == two.digest()


def test_classes_survive_a_json_round_trip() -> None:
    perimeter = Perimeter(allowed_actions=("invoice.*",), risk_classes=(IRREVERSIBLE,))
    again = Perimeter.from_json(perimeter.to_json())
    assert again == perimeter
    assert again.digest() == perimeter.digest()


def test_duplicate_class_names_are_refused() -> None:
    with pytest.raises(ValidationError, match="unique"):
        Perimeter(
            allowed_actions=("invoice.*",),
            risk_classes=(IRREVERSIBLE, {**IRREVERSIBLE, "max_token_seconds": 3600}),
        )


@pytest.mark.parametrize("name", ["", "Irreversible", "1st", "with space", "x" * 41])
def test_invalid_class_name_is_refused(name: str) -> None:
    with pytest.raises(ValidationError):
        RiskClass(name=name, actions=("invoice.pay",), max_token_seconds=30)


@pytest.mark.parametrize("seconds", [0, -5, 86401, True, "30", 30.0])
def test_invalid_max_token_seconds_is_refused(seconds: object) -> None:
    with pytest.raises(ValidationError):
        RiskClass(name="irreversible", actions=("invoice.pay",), max_token_seconds=seconds)


@pytest.mark.parametrize("seconds", [1, 86400])
def test_max_token_seconds_bounds_are_accepted(seconds: int) -> None:
    rc = RiskClass(name="irreversible", actions=("invoice.pay",), max_token_seconds=seconds)
    assert rc.max_token_seconds == seconds


@pytest.mark.parametrize("actions", [(), ("Invoice.Pay",), ("invoice..pay",)])
def test_invalid_class_actions_are_refused(actions: tuple[str, ...]) -> None:
    with pytest.raises(ValidationError):
        RiskClass(name="irreversible", actions=actions, max_token_seconds=30)


def test_unknown_class_field_is_refused() -> None:
    with pytest.raises(ValidationError):
        RiskClass.model_validate({**IRREVERSIBLE, "min_token_seconds": 1})


def test_too_many_classes_are_refused() -> None:
    classes = tuple(
        {"name": f"c{i}", "actions": ["invoice.pay"], "max_token_seconds": 30}
        for i in range(MAX_RISK_CLASSES + 1)
    )
    with pytest.raises(ValidationError):
        Perimeter(allowed_actions=("invoice.*",), risk_classes=classes)


def test_class_reaches_the_type_and_its_sub_types_only() -> None:
    perimeter = Perimeter(allowed_actions=("invoice.*",), risk_classes=(IRREVERSIBLE,))
    assert perimeter.token_lifetime_cap("invoice.pay") == (30, ("irreversible",))
    assert perimeter.token_lifetime_cap("invoice.pay.partial") == (30, ("irreversible",))
    assert perimeter.token_lifetime_cap("invoice.payment") == (None, ())
    assert perimeter.token_lifetime_cap("invoice.read") == (None, ())


def test_prefix_and_star_classes_reach_broadly() -> None:
    perimeter = Perimeter(
        allowed_actions=("invoice.*",),
        risk_classes=(
            {"name": "all", "actions": ["*"], "max_token_seconds": 200},
            {"name": "invoice", "actions": ["invoice.*"], "max_token_seconds": 100},
        ),
    )
    assert perimeter.token_lifetime_cap("invoice") == (100, ("all", "invoice"))
    assert perimeter.token_lifetime_cap("report.read") == (200, ("all",))


def test_shortest_class_wins() -> None:
    perimeter = Perimeter(
        allowed_actions=("invoice.*",),
        risk_classes=(
            {"name": "money", "actions": ["invoice.*"], "max_token_seconds": 120},
            IRREVERSIBLE,
        ),
    )
    assert perimeter.token_lifetime_cap("invoice.pay") == (30, ("irreversible", "money"))
    assert perimeter.token_lifetime_cap("invoice.read") == (120, ("money",))


def test_sub_mandate_keeps_its_own_classes() -> None:
    parent = Perimeter(
        allowed_actions=("invoice.*",), delegation_allowed=True,
        risk_classes=({"name": "parent", "actions": ["invoice.read"], "max_token_seconds": 20},),
    )
    child = Perimeter(allowed_actions=("invoice.pay",), risk_classes=(IRREVERSIBLE,))
    narrowed = child.narrowed_by(parent)
    assert narrowed.risk_classes == child.risk_classes


# --- Token issuance -------------------------------------------------------------------


async def test_class_shortens_the_token_and_is_sealed() -> None:
    root = await _root(risk_classes=[IRREVERSIBLE])
    before = datetime.now(UTC)
    paid = await _token(root["mandate_id"], "invoice.pay")
    assert _lifetime(paid) <= 30
    assert datetime.fromisoformat(paid["expires_at"]) <= before + timedelta(seconds=31)
    assert _claims(paid)["amr_risk_classes"] == ["irreversible"]


async def test_action_outside_every_class_keeps_the_default(monkeypatch) -> None:
    monkeypatch.setattr("amr.config.settings.token_lifetime_seconds", 300)
    root = await _root(risk_classes=[IRREVERSIBLE])
    read = await _token(root["mandate_id"], "invoice.read")
    assert _lifetime(read) == 300
    assert "amr_risk_classes" not in _claims(read)


async def test_overlapping_classes_take_the_shortest_and_name_both() -> None:
    root = await _root(risk_classes=[
        {"name": "money", "actions": ["invoice.*"], "max_token_seconds": 120},
        IRREVERSIBLE,
    ])
    paid = await _token(root["mandate_id"], "invoice.pay")
    assert _lifetime(paid) <= 30
    assert _claims(paid)["amr_risk_classes"] == ["irreversible", "money"]


async def test_parent_class_binds_a_sub_mandate_without_classes() -> None:
    root = await _root(delegation_allowed=True, risk_classes=[IRREVERSIBLE])
    child = await _child(root["mandate_id"])
    paid = await _token(child["mandate_id"], "invoice.pay", agent_id=HELPER)
    assert _lifetime(paid) <= 30
    assert _claims(paid)["amr_risk_classes"] == ["irreversible"]


async def test_sub_mandate_cannot_lengthen_a_parent_class() -> None:
    root = await _root(delegation_allowed=True, risk_classes=[IRREVERSIBLE])
    child = await _child(
        root["mandate_id"],
        risk_classes=[{**IRREVERSIBLE, "max_token_seconds": 3600}],
    )
    paid = await _token(child["mandate_id"], "invoice.pay", agent_id=HELPER)
    assert _lifetime(paid) <= 30


async def test_sub_mandate_can_shorten_with_its_own_class(monkeypatch) -> None:
    monkeypatch.setattr("amr.config.settings.token_lifetime_seconds", 300)
    root = await _root(delegation_allowed=True)
    child = await _child(
        root["mandate_id"],
        risk_classes=[{"name": "strict", "actions": ["invoice.pay"], "max_token_seconds": 10}],
    )
    paid = await _token(child["mandate_id"], "invoice.pay", agent_id=HELPER)
    assert _lifetime(paid) <= 10
    assert _claims(paid)["amr_risk_classes"] == ["strict"]
    # The parent, without a class, still issues a full-length token for itself.
    own = await _token(root["mandate_id"], "invoice.pay")
    assert _lifetime(own) == 300
    assert "amr_risk_classes" not in _claims(own)


async def test_override_can_shorten_below_a_class_never_above() -> None:
    root = await _root(risk_classes=[IRREVERSIBLE])
    shorter = await _token(root["mandate_id"], "invoice.pay", lifetime_override_seconds=5)
    assert _lifetime(shorter) <= 5
    longer = await _token(root["mandate_id"], "invoice.pay", lifetime_override_seconds=3600)
    assert _lifetime(longer) <= 30


async def test_class_longer_than_the_default_does_not_extend(monkeypatch) -> None:
    monkeypatch.setattr("amr.config.settings.token_lifetime_seconds", 300)
    root = await _root(risk_classes=[{**IRREVERSIBLE, "max_token_seconds": 86400}])
    paid = await _token(root["mandate_id"], "invoice.pay")
    assert _lifetime(paid) == 300
    assert _claims(paid)["amr_risk_classes"] == ["irreversible"]


async def test_mandate_without_classes_issues_unchanged_tokens(monkeypatch) -> None:
    monkeypatch.setattr("amr.config.settings.token_lifetime_seconds", 300)
    root = await _root()
    paid = await _token(root["mandate_id"], "invoice.pay")
    assert _lifetime(paid) == 300
    assert "amr_risk_classes" not in _claims(paid)


async def test_free_text_mandate_is_unaffected(monkeypatch) -> None:
    monkeypatch.setattr("amr.config.settings.token_lifetime_seconds", 300)
    result = json.loads(await create_mandate(**BASE))
    paid = await _token(result["mandate_id"], "invoice.pay")
    assert _lifetime(paid) == 300
    assert "amr_risk_classes" not in _claims(paid)


# --- Creation, proof, signature, exports ---------------------------------------------


async def test_classes_are_stored_returned_and_verified() -> None:
    root = await _root(risk_classes=[IRREVERSIBLE])
    assert root["perimeter"]["risk_classes"] == [IRREVERSIBLE]
    verified = json.loads(await verify_mandate(AGENT, "pay an invoice"))
    assert verified["perimeter"]["risk_classes"] == [IRREVERSIBLE]


async def test_classes_are_sealed_into_the_mandate_hash(temp_db: Path) -> None:
    root = await _root(risk_classes=[IRREVERSIBLE])
    with sqlite3.connect(temp_db) as conn:
        created_at, expires_at, perimeter_json, stored = conn.execute(
            "SELECT created_at, expires_at, perimeter_json, chain_hash FROM mandates "
            "WHERE id = ?",
            (root["mandate_id"],),
        ).fetchone()
    data = {
        "id": root["mandate_id"],
        "principal_id": PRINCIPAL,
        "agent_id": AGENT,
        "scope": BASE["scope"],
        "legal_basis_regulation": BASE["legal_basis_regulation"],
        "legal_basis_article": BASE["legal_basis_article"],
        "legal_basis_jurisdiction": "EU",
        "duration_hours": BASE["duration_hours"],
        "created_at": created_at,
        "expires_at": expires_at,
        "parent_mandate_id": None,
        "perimeter": json.loads(perimeter_json),
    }
    assert data["perimeter"]["risk_classes"] == [IRREVERSIBLE]
    assert compute_hash(data, "") == stored
    data["perimeter"].pop("risk_classes")
    assert compute_hash(data, "") != stored


async def test_classes_alone_ask_for_allowed_actions() -> None:
    result = json.loads(await create_mandate(**BASE, risk_classes=[IRREVERSIBLE]))
    assert result["code"] == "perimeter_invalid"


async def test_empty_class_list_asks_for_allowed_actions() -> None:
    result = json.loads(await create_mandate(**BASE, risk_classes=[]))
    assert result["code"] == "perimeter_invalid"


@pytest.mark.parametrize("bad", [
    {"name": "irreversible", "actions": ["invoice.pay"]},
    {"name": "irreversible", "actions": ["invoice.pay"], "max_token_seconds": 0},
    {"name": "Bad Name", "actions": ["invoice.pay"], "max_token_seconds": 30},
    "irreversible",
])
async def test_invalid_class_is_refused_at_creation(bad: object) -> None:
    result = await _create(risk_classes=[bad])
    assert result["code"] == "perimeter_invalid", result


async def test_principal_signature_covers_the_classes() -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    pub = b64url_encode(raw)
    proof = b64url_encode(key.sign(key_registration_payload(PRINCIPAL, pub)))
    assert "key_id" in json.loads(await register_principal_key(PRINCIPAL, pub, proof))

    args = {**BASE, "allowed_actions": ["invoice.*"], "risk_classes": [IRREVERSIBLE]}
    prepared = json.loads(await prepare_mandate_signature(**args))
    assert '"risk_classes"' in prepared["payload"]
    signature = b64url_encode(key.sign(prepared["payload"].encode("utf-8")))

    loosened = {**args, "risk_classes": [{**IRREVERSIBLE, "max_token_seconds": 3600}]}
    refused = json.loads(await create_mandate(
        **loosened, principal_signature=signature, signed_at=prepared["signed_at"]
    ))
    assert refused.get("code") == "principal_signature_invalid", refused

    created = json.loads(await create_mandate(
        **args, principal_signature=signature, signed_at=prepared["signed_at"]
    ))
    assert created.get("status") == "created", created
    pack = json.loads(await get_proof(created["mandate_id"]))
    assert pack["chain_integrity"]["principal_signature_valid"] is True


async def test_attestation_carries_the_classes() -> None:
    root = await _root(risk_classes=[IRREVERSIBLE])
    issued = json.loads(await issue_mandate_attestation(root["mandate_id"], AGENT))
    pem = json.loads(await get_registry_public_key())["public_key_pem"]
    result = verify_attestation(issued["attestation"], pem)
    assert result["valid"] is True, result
    assert result["attestation"]["perimeter"]["risk_classes"] == [IRREVERSIBLE]


async def test_insurer_dossier_lists_the_classes() -> None:
    root = await _root(risk_classes=[IRREVERSIBLE])
    page = json.loads(await export_insurer_dossier(root["mandate_id"], format="html"))["html"]
    assert "Token lifetime by risk class" in page
    assert "irreversible: invoice.pay at most 30 s" in page
    plain = await _root(agent_id="agent:other")
    page = json.loads(await export_insurer_dossier(plain["mandate_id"], format="html"))["html"]
    assert "Token lifetime by risk class" in page


def test_template_passes_its_classes_to_create_mandate() -> None:
    assert "risk_classes" not in AGENT_SANTE_RGPD.create_mandate_kwargs()
    classed = AGENT_SANTE_RGPD.perimeter.model_copy(
        update={"risk_classes": (RiskClass.model_validate(IRREVERSIBLE),)}
    )
    template = AGENT_SANTE_RGPD.model_copy(update={"perimeter": classed})
    assert template.create_mandate_kwargs()["risk_classes"] == [IRREVERSIBLE]
