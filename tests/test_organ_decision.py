"""Tests for organ decisions: the decision of a body that authorizes an agent.

Covers the model (form, canonical JSON), the health template (closed list of actions,
reserved key), create_mandate (validation, sealing into the chain hash, unchanged hash
without it, principal signature coverage) and what verify_mandate and get_proof return.
"""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from pydantic import ValidationError

from amr.crypto.chain import compute_hash
from amr.crypto.principal import b64url_encode, key_registration_payload
from amr.db.engine import init_db
from amr.models.organ_decision import (
    ORGAN_DECISION_KEY,
    OrganDecision,
    OrganDecisionError,
    organ_decision_from_metadata,
    recorded_organ_decision,
)
from amr.models.perimeter import Perimeter
from amr.templates import AGENT_SANTE_RGPD_ID, get_template
from amr.templates.base import MandateTemplate
from amr.tools.create_mandate import create_mandate
from amr.tools.get_proof import get_proof
from amr.tools.principal_keys import prepare_mandate_signature, register_principal_key
from amr.tools.verify_mandate import verify_mandate

PRINCIPAL = "org:chu-exemple"
AGENT = "agent:assistant-planification"

BASE = {
    "principal_id": PRINCIPAL,
    "agent_id": AGENT,
    "scope": "Handle the outpatient schedule",
    "legal_basis_regulation": "Mandat de gestion",
    "legal_basis_article": "Art. 1984 Code civil",
    "duration_hours": 24.0,
    "allowed_actions": ["appointment.book"],
}

DECISION = {
    "body": "Digital strategy committee",
    "title": "Use of the scheduling assistant in the outpatient department",
    "decided_on": "2026-10-01",
    "reference": "CSN-2026-14",
    "authorized_personnel": ("Head of outpatient department", "Care coordinator"),
}


def _decision(**changes: object) -> OrganDecision:
    return OrganDecision(**{**DECISION, **changes})  # type: ignore[arg-type]


async def _create(**kwargs: object) -> dict:
    return json.loads(await create_mandate(**{**BASE, **kwargs}))  # type: ignore[arg-type]


def _row(db_path: Path, mandate_id: str) -> sqlite3.Row:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM mandates WHERE id = ?", (mandate_id,)).fetchone()
    finally:
        conn.close()


def _count(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute("SELECT COUNT(*) FROM mandates").fetchone()[0]
    finally:
        conn.close()


def _hash_data(row: sqlite3.Row) -> dict:
    legal = json.loads(row["legal_basis_json"])
    data = {
        "id": row["id"],
        "principal_id": row["principal_id"],
        "agent_id": row["agent_id"],
        "scope": row["scope"],
        "legal_basis_regulation": legal["regulation"],
        "legal_basis_article": legal["article"],
        "legal_basis_jurisdiction": legal["jurisdiction"],
        "duration_hours": BASE["duration_hours"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
        "parent_mandate_id": row["parent_mandate_id"],
    }
    if row["perimeter_json"]:
        data["perimeter"] = Perimeter.from_json(row["perimeter_json"]).canonical()
    return data


# --- Model ---------------------------------------------------------------------------


def test_decision_round_trips_through_canonical_json() -> None:
    decision = _decision()
    raw = decision.to_metadata_value()
    assert json.loads(raw) == {
        **DECISION,
        "authorized_personnel": list(DECISION["authorized_personnel"]),
    }
    assert OrganDecision.from_metadata_value(raw) == decision
    assert raw == json.dumps(json.loads(raw), sort_keys=True, separators=(",", ":"))


def test_reference_is_optional() -> None:
    decision = _decision(reference=None)
    assert decision.canonical()["reference"] is None
    assert OrganDecision.from_metadata_value(decision.to_metadata_value()) == decision


@pytest.mark.parametrize("field", ["body", "title", "reference"])
@pytest.mark.parametrize("bad", ["", "   ", " padded", "padded "])
def test_text_fields_cannot_be_blank_or_padded(field: str, bad: str) -> None:
    with pytest.raises(ValidationError):
        _decision(**{field: bad})


@pytest.mark.parametrize(
    "bad", ["2026-1-01", "01/10/2026", "2026-10-01T00:00:00", "2026-02-30", "20261001", 20261001]
)
def test_decided_on_is_a_real_iso_date(bad: object) -> None:
    with pytest.raises(ValidationError):
        _decision(decided_on=bad)


@pytest.mark.parametrize(
    "bad",
    [
        (),
        ("",),
        (" Care coordinator",),
        ("Care coordinator", "Care coordinator"),
        ("x" * 201,),
        tuple(f"Role {i}" for i in range(51)),
    ],
)
def test_authorized_personnel_is_a_short_list_of_named_entries(bad: tuple) -> None:
    with pytest.raises(ValidationError):
        _decision(authorized_personnel=bad)


def test_fifty_people_and_two_hundred_characters_are_accepted() -> None:
    assert (
        len(_decision(authorized_personnel=tuple(f"R{i}" for i in range(50))).authorized_personnel)
        == 50
    )
    assert _decision(authorized_personnel=("x" * 200,)).authorized_personnel == ("x" * 200,)


def test_unknown_fields_and_wrong_types_are_refused() -> None:
    with pytest.raises(ValidationError):
        OrganDecision(**{**DECISION, "signed_by": "someone"})  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        _decision(body=42)


def test_decision_is_immutable() -> None:
    decision = _decision()
    with pytest.raises(ValidationError):
        decision.body = "Another body"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("not json", "organ_decision_invalid"),
        ("[]", "organ_decision_invalid"),
        ('"text"', "organ_decision_invalid"),
        ('{"body": "x"}', "organ_decision_invalid"),
    ],
)
def test_metadata_value_must_be_a_valid_object(raw: str, code: str) -> None:
    with pytest.raises(OrganDecisionError) as exc:
        OrganDecision.from_metadata_value(raw)
    assert exc.value.code == code


def test_metadata_value_must_be_canonical() -> None:
    pretty = json.dumps(_decision().canonical(), indent=2)
    with pytest.raises(OrganDecisionError) as exc:
        OrganDecision.from_metadata_value(pretty)
    assert exc.value.code == "organ_decision_not_canonical"


def test_metadata_without_the_key_has_no_decision() -> None:
    assert organ_decision_from_metadata({"client_ref": "x"}) is None


@pytest.mark.parametrize(
    "metadata_json",
    ["{}", '{"organ_decision": "junk"}', "[]", '"organ_decision"', "null", "not json"],
)
def test_recorded_decision_reads_anything_else_as_none(metadata_json: str) -> None:
    assert recorded_organ_decision(metadata_json) is None


# --- Template ------------------------------------------------------------------------


@pytest.fixture
def sante() -> MandateTemplate:
    return get_template(AGENT_SANTE_RGPD_ID)


def test_health_template_accepts_an_optional_decision(sante: MandateTemplate) -> None:
    assert sante.organ_decision == "optional"
    assert ORGAN_DECISION_KEY not in sante.create_mandate_kwargs()["metadata"]
    metadata = sante.create_mandate_kwargs(organ_decision=_decision())["metadata"]
    assert metadata[ORGAN_DECISION_KEY] == _decision().to_metadata_value()
    assert metadata["template_id"] == AGENT_SANTE_RGPD_ID


def test_health_template_predefined_actions_are_a_closed_list(sante: MandateTemplate) -> None:
    assert sante.perimeter.allowed_actions
    assert all("*" not in action for action in sante.perimeter.allowed_actions)
    assert sante.perimeter.check_action("patient_record.read.all", {}) is not None
    assert sante.perimeter.check_action("appointment.cancel", {}) is not None


def test_organ_decision_key_is_reserved_in_principal_metadata(sante: MandateTemplate) -> None:
    with pytest.raises(ValueError, match="reserved"):
        sante.create_mandate_kwargs(metadata={ORGAN_DECISION_KEY: _decision().to_metadata_value()})


def _template(**changes: object) -> MandateTemplate:
    base = {
        "template_id": "demo",
        "version": "1.0.0",
        "title": "Demo",
        "sector": "demo",
        "summary": "Demo template",
        "perimeter": Perimeter(allowed_actions=("doc.read",)),
        "actions": {"doc.read": "Read a document."},
        "default_duration_hours": 24,
    }
    return MandateTemplate(**{**base, **changes})  # type: ignore[arg-type]


def test_template_without_organ_decision_refuses_one() -> None:
    template = _template()
    assert template.organ_decision == "none"
    with pytest.raises(ValueError, match="does not record an organ decision"):
        template.create_mandate_kwargs(organ_decision=_decision())


def test_template_requiring_a_decision_refuses_to_go_without() -> None:
    template = _template(organ_decision="required")
    with pytest.raises(ValueError, match="requires an organ decision"):
        template.create_mandate_kwargs()
    assert (
        ORGAN_DECISION_KEY in template.create_mandate_kwargs(organ_decision=_decision())["metadata"]
    )


@pytest.mark.parametrize("pattern", ["doc.*", "*"])
def test_template_with_organ_decision_needs_a_closed_list(pattern: str) -> None:
    perimeter = Perimeter(allowed_actions=(pattern,))
    actions = {pattern: "Anything under doc."}
    assert _template(perimeter=perimeter, actions=actions).organ_decision == "none"
    for mode in ("optional", "required"):
        with pytest.raises(ValidationError, match="closed list"):
            _template(perimeter=perimeter, actions=actions, organ_decision=mode)


def test_template_organ_decision_mode_is_restricted() -> None:
    with pytest.raises(ValidationError):
        _template(organ_decision="sometimes")


def test_template_digest_covers_the_organ_decision_mode() -> None:
    assert _template().digest() != _template(organ_decision="optional").digest()


# --- create_mandate, verify_mandate, get_proof ----------------------------------------


async def test_mandate_records_and_returns_the_decision(temp_db: Path) -> None:
    decision = _decision()
    result = await _create(metadata={ORGAN_DECISION_KEY: decision.to_metadata_value()})
    assert result["status"] == "created", result
    assert result["organ_decision"] == decision.canonical()

    verdict = json.loads(await verify_mandate(AGENT, "book a slot"))
    assert verdict["authorized"] is True
    assert verdict["organ_decision"] == decision.canonical()

    proof = json.loads(await get_proof(result["mandate_id"]))
    assert proof["mandate"]["organ_decision"] == decision.canonical()
    assert proof["mandate"]["metadata"][ORGAN_DECISION_KEY] == decision.to_metadata_value()


async def test_decision_is_sealed_into_the_chain_hash(temp_db: Path) -> None:
    decision = _decision()
    result = await _create(metadata={ORGAN_DECISION_KEY: decision.to_metadata_value()})
    row = _row(temp_db, result["mandate_id"])
    data = _hash_data(row)
    assert result["chain_hash"] != compute_hash(data, "")
    data["organ_decision"] = decision.canonical()
    assert result["chain_hash"] == compute_hash(data, "") == row["chain_hash"]


async def test_mandate_without_decision_keeps_its_exact_hash(temp_db: Path) -> None:
    result = await _create(metadata={"client_ref": "CAB-001"})
    assert result["organ_decision"] is None
    row = _row(temp_db, result["mandate_id"])
    assert result["chain_hash"] == compute_hash(_hash_data(row), "")
    verdict = json.loads(await verify_mandate(AGENT, "book a slot"))
    assert verdict["organ_decision"] is None
    proof = json.loads(await get_proof(result["mandate_id"]))
    assert proof["mandate"]["organ_decision"] is None


async def test_template_mandate_with_decision_end_to_end(
    sante: MandateTemplate, temp_db: Path
) -> None:
    kwargs = sante.create_mandate_kwargs(organ_decision=_decision())
    result = await _create(duration_hours=sante.default_duration_hours, **kwargs)
    assert result["status"] == "created", result
    assert result["organ_decision"]["authorized_personnel"] == list(
        DECISION["authorized_personnel"]
    )
    row = _row(temp_db, result["mandate_id"])
    data = _hash_data(row)
    data["duration_hours"] = sante.default_duration_hours
    data["organ_decision"] = _decision().canonical()
    assert row["chain_hash"] == compute_hash(data, "")


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ("junk", "organ_decision_invalid"),
        (json.dumps({**DECISION, "authorized_personnel": []}), "organ_decision_invalid"),
        (json.dumps(_decision().canonical(), indent=1), "organ_decision_not_canonical"),
    ],
)
async def test_malformed_decision_is_refused_and_nothing_is_written(
    temp_db: Path, value: str, code: str
) -> None:
    await init_db(temp_db)
    result = await _create(metadata={ORGAN_DECISION_KEY: value})
    assert result["code"] == code, result
    assert _count(temp_db) == 0


async def test_decision_dated_after_today_utc_is_refused(temp_db: Path) -> None:
    await init_db(temp_db)
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).date().isoformat()
    result = await _create(
        metadata={ORGAN_DECISION_KEY: _decision(decided_on=tomorrow).to_metadata_value()}
    )
    assert result["code"] == "organ_decision_invalid"
    assert "future" in result["error"]
    assert _count(temp_db) == 0


async def test_decision_dated_in_the_past_is_accepted(temp_db: Path) -> None:
    yesterday = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
    result = await _create(
        metadata={ORGAN_DECISION_KEY: _decision(decided_on=yesterday).to_metadata_value()}
    )
    assert result["status"] == "created", result


async def test_legacy_free_key_is_not_reported_as_a_decision(temp_db: Path) -> None:
    result = await _create()
    conn = sqlite3.connect(str(temp_db))
    try:
        # A mandate written before the key was reserved could carry any value there.
        conn.execute(
            "INSERT INTO mandates (id, principal_id, agent_id, scope, legal_basis_json, status, "
            "created_at, expires_at, metadata_json, chain_hash) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "00000000-0000-4000-8000-000000000001",
                PRINCIPAL,
                "agent:legacy",
                "legacy",
                '{"regulation":"x","article":"y","jurisdiction":"EU"}',
                "active",
                datetime.now(UTC).isoformat(),
                (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                json.dumps({ORGAN_DECISION_KEY: "committee of 2025"}),
                "0" * 64,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    assert result["status"] == "created"
    verdict = json.loads(await verify_mandate("agent:legacy", "anything"))
    assert verdict["authorized"] is True
    assert verdict["organ_decision"] is None
    proof = json.loads(await get_proof("00000000-0000-4000-8000-000000000001"))
    assert proof["mandate"]["organ_decision"] is None


# --- Principal signature covers the decision --------------------------------------------


def _pub(key: ed25519.Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return b64url_encode(raw)


async def _register(key: ed25519.Ed25519PrivateKey) -> None:
    proof = b64url_encode(key.sign(key_registration_payload(PRINCIPAL, _pub(key))))
    registered = json.loads(await register_principal_key(PRINCIPAL, _pub(key), proof))
    assert "key_id" in registered, registered


async def _signed(key: ed25519.Ed25519PrivateKey, metadata: dict[str, str]) -> dict:
    args = {**BASE, "metadata": metadata}
    prepared = json.loads(await prepare_mandate_signature(**args))  # type: ignore[arg-type]
    signature = b64url_encode(key.sign(prepared["payload"].encode("utf-8")))
    return {**args, "principal_signature": signature, "signed_at": prepared["signed_at"]}


async def test_signed_mandate_with_decision_is_valid_in_the_proof(temp_db: Path) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    await _register(key)
    signed = await _signed(key, {ORGAN_DECISION_KEY: _decision().to_metadata_value()})
    result = json.loads(await create_mandate(**signed))  # type: ignore[arg-type]
    assert result["status"] == "created", result
    proof = json.loads(await get_proof(result["mandate_id"]))
    assert proof["chain_integrity"]["principal_signature_valid"] is True
    assert proof["mandate"]["organ_decision"] == _decision().canonical()


@pytest.mark.parametrize("tampered", ["added", "changed"])
async def test_signature_covers_the_decision_so_adding_or_changing_it_fails(
    temp_db: Path, tampered: str
) -> None:
    key = ed25519.Ed25519PrivateKey.generate()
    await _register(key)
    signed_metadata = (
        {} if tampered == "added" else {ORGAN_DECISION_KEY: _decision().to_metadata_value()}
    )
    signed = await _signed(key, signed_metadata)
    forged = _decision(authorized_personnel=("Anyone",)).to_metadata_value()
    signed["metadata"] = {ORGAN_DECISION_KEY: forged}
    result = json.loads(await create_mandate(**signed))  # type: ignore[arg-type]
    assert result["code"] == "principal_signature_invalid"
    assert _count(temp_db) == 0


async def test_decision_on_a_sub_mandate_is_refused(temp_db: Path) -> None:
    parent = await _create(allowed_actions=["appointment.book"], delegation_allowed=True)
    assert parent["status"] == "created", parent
    result = await _create(
        principal_id=AGENT,
        agent_id="agent:sub",
        parent_mandate_id=parent["mandate_id"],
        allowed_actions=["appointment.book"],
        duration_hours=1.0,
        metadata={ORGAN_DECISION_KEY: _decision().to_metadata_value()},
    )
    assert result["code"] == "organ_decision_on_sub_mandate", result
    assert _count(temp_db) == 1


@pytest.mark.parametrize(
    "perimeter",
    [
        {"allowed_actions": None},
        {"allowed_actions": ["*"]},
        {"allowed_actions": ["appointment.*"]},
        {"allowed_actions": ["appointment.book", "letter.*"]},
    ],
)
async def test_decision_needs_a_closed_list_of_actions(temp_db: Path, perimeter: dict) -> None:
    await init_db(temp_db)
    result = await _create(
        metadata={ORGAN_DECISION_KEY: _decision().to_metadata_value()}, **perimeter
    )
    assert result["code"] == "organ_decision_needs_closed_list", result
    assert _count(temp_db) == 0
