"""Tests for sector mandate templates, starting with ``agent-sante-rgpd``.

The end-to-end tests create a real mandate from the template and ask for tokens: allowed
actions get one, everything the template forbids is refused, at the token and at
delegation.
"""

import json
import re
from pathlib import Path

import aiosqlite
import pytest
from pydantic import ValidationError

from amr.crypto.signing import generate_signing_key
from amr.models.perimeter import Perimeter
from amr.templates import AGENT_SANTE_RGPD_ID, get_template, list_templates
from amr.templates.base import LegalReference, MandateTemplate
from amr.tools.create_mandate import create_mandate
from amr.tools.get_proof import get_proof
from amr.tools.issue_action_token import issue_action_token

DOC = Path(__file__).resolve().parent.parent / "docs" / "templates" / "agent-sante-rgpd.md"
PRINCIPAL = "org:cabinet-medical"
AGENT = "agent:assistant-cabinet"


@pytest.fixture(autouse=True)
def isolated_signing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    priv = tmp_path / "test_key.pem"
    pub = tmp_path / "test_key.pub"
    monkeypatch.setattr("amr.config.settings.signing_key_path", priv)
    monkeypatch.setattr("amr.config.settings.public_key_path", pub)
    generate_signing_key(priv, pub)


@pytest.fixture
def sante() -> MandateTemplate:
    return get_template(AGENT_SANTE_RGPD_ID)


async def _mandate_from(template: MandateTemplate, **kwargs: object) -> dict:
    args = template.create_mandate_kwargs(**kwargs)  # type: ignore[arg-type]
    return json.loads(
        await create_mandate(
            principal_id=PRINCIPAL,
            agent_id=AGENT,
            scope=template.summary,
            legal_basis_regulation="Mandat de gestion",
            legal_basis_article="Art. 1984 Code civil",
            duration_hours=template.default_duration_hours,
            **args,
        )
    )


async def _token(mandate_id: str, action_type: str, metadata: dict | None = None) -> dict:
    return json.loads(
        await issue_action_token(
            mandate_id=mandate_id,
            agent_id=AGENT,
            action=f"test {action_type}",
            audience="runtime://cabinet",
            action_metadata_json=json.dumps(metadata or {}),
            action_type=action_type,
        )
    )


# --- Registry --------------------------------------------------------------------------


def test_registry_lists_and_returns_the_health_template(sante: MandateTemplate) -> None:
    assert AGENT_SANTE_RGPD_ID in list_templates()
    assert sante.template_id == "agent-sante-rgpd"
    assert sante.sector == "health"


def test_unknown_template_is_refused() -> None:
    with pytest.raises(KeyError, match="unknown mandate template"):
        get_template("agent-inconnu")


# --- Content of the health template -------------------------------------------------


def test_health_template_forbids_what_the_card_says(sante: MandateTemplate) -> None:
    p = sante.perimeter
    for action in (
        "prescription.create",
        "prescription.renew",
        "prescription",
        "diagnosis.record",
        "patient_record.write",
        "patient_record.export",
        "patient_record.delete",
        "letter.send",
        "patient_message.send",
        "agent.create",
        "agent.create.batch",
    ):
        assert (p.check_action(action, {}) or "").startswith("forbidden:"), action
    assert p.delegation_allowed is False


def test_health_template_allows_the_practice_tasks(sante: MandateTemplate) -> None:
    p = sante.perimeter
    for action in (
        "patient_record.read",
        "appointment.read",
        "appointment.propose",
        "appointment.book",
        "letter.draft",
        "patient_message.draft",
    ):
        assert p.check_action(action, {}) is None, action


def test_health_template_does_not_allow_anything_else(sante: MandateTemplate) -> None:
    p = sante.perimeter
    assert "*" not in p.allowed_actions
    assert not any(a.endswith(".*") for a in p.allowed_actions)
    for action in ("invoice.pay", "patient_record", "appointment.cancel", "email.send"):
        assert (p.check_action(action, {}) or "").startswith("not_allowed:"), action


def test_health_template_ceiling_on_supplies(sante: MandateTemplate) -> None:
    p = sante.perimeter
    assert p.check_action("supplies.order", {"amount": "100", "currency": "EUR"}) is None
    assert p.check_action("supplies.order", {"amount": "100.01", "currency": "EUR"}) == (
        "amount_above_limit:100 EUR"
    )
    assert p.check_action("supplies.order", {}) == "amount_required"
    assert p.check_action("supplies.order", {"amount": "10", "currency": "USD"}) == (
        "currency_mismatch:EUR"
    )
    # The ceiling only applies to orders: reading the record needs no amount.
    assert p.check_action("patient_record.read", {}) is None


def test_every_action_has_a_meaning(sante: MandateTemplate) -> None:
    named = (
        set(sante.perimeter.allowed_actions)
        | set(sante.perimeter.forbidden_actions)
        | set(sante.perimeter.amount_actions)
    )
    assert set(sante.actions) == named
    for action in sante.perimeter.forbidden_actions:
        assert sante.actions[action].startswith("Forbidden:"), action


def test_legal_references_are_marked_to_verify(sante: MandateTemplate) -> None:
    assert sante.legal_references
    assert all(ref.status == "to_verify" for ref in sante.legal_references)


# --- Template model rules ----------------------------------------------------------


def _template(**overrides: object) -> MandateTemplate:
    params: dict = {
        "template_id": "agent-test",
        "version": "1.0.0",
        "title": "Test",
        "sector": "test",
        "summary": "Test template",
        "perimeter": Perimeter(allowed_actions=("a.read",), forbidden_actions=("a.write",)),
        "actions": {"a.read": "Read.", "a.write": "Forbidden: write."},
        "default_duration_hours": 24,
    }
    params.update(overrides)
    return MandateTemplate(**params)


def test_catalog_must_cover_every_action() -> None:
    with pytest.raises(ValidationError, match="no meaning for"):
        _template(actions={"a.read": "Read."})


def test_catalog_cannot_name_actions_outside_the_perimeter() -> None:
    with pytest.raises(ValidationError, match="outside the perimeter"):
        _template(actions={"a.read": "Read.", "a.write": "No.", "b.x": "Other."})


def test_catalog_entries_cannot_be_blank() -> None:
    with pytest.raises(ValidationError, match="needs a meaning"):
        _template(actions={"a.read": "  ", "a.write": "Forbidden: write."})


def test_an_allowed_action_cannot_be_forbidden_at_the_same_time() -> None:
    with pytest.raises(ValidationError, match="blocked by a forbidden pattern"):
        _template(
            perimeter=Perimeter(allowed_actions=("a.read",), forbidden_actions=("a",)),
            actions={"a.read": "Read.", "a": "Forbidden."},
        )
    with pytest.raises(ValidationError, match="blocked by a forbidden pattern"):
        _template(
            perimeter=Perimeter(allowed_actions=("a.*",), forbidden_actions=("a",)),
            actions={"a.*": "Anything.", "a": "Forbidden."},
        )
    # A narrower prohibition inside a wider allowance is legitimate.
    _template(
        perimeter=Perimeter(allowed_actions=("a.*",), forbidden_actions=("a.write",)),
        actions={"a.*": "Anything.", "a.write": "Forbidden."},
    )


def test_template_ids_and_versions_are_checked() -> None:
    with pytest.raises(ValidationError):
        _template(template_id="Agent Santé")
    with pytest.raises(ValidationError):
        _template(version="1.0")


def test_template_is_immutable(sante: MandateTemplate) -> None:
    with pytest.raises(ValidationError):
        sante.version = "9.9.9"  # type: ignore[misc]
    with pytest.raises(TypeError):
        sante.actions["patient_record.read"] = "changed"  # type: ignore[index]
    assert sante.actions["patient_record.read"].startswith("Read the patient record")


def test_health_template_digest_is_pinned(sante: MandateTemplate) -> None:
    # Any change to the template content must come with a new version and a new pin.
    assert sante.version == "1.1.0"
    assert sante.digest() == ("41117c040efcc7c96d8cf1dbda89fa025e4061a1cd252789163df57e1d5b16b3")


def test_legal_reference_status_is_restricted() -> None:
    with pytest.raises(ValidationError):
        LegalReference(reference="x", topic="y", status="approved")  # type: ignore[arg-type]


# --- Digest and arguments ------------------------------------------------------------


def test_digest_is_stable_and_sensitive_to_content(sante: MandateTemplate) -> None:
    assert sante.digest() == get_template(AGENT_SANTE_RGPD_ID).digest()
    assert re.fullmatch(r"[0-9a-f]{64}", sante.digest())
    changed = sante.model_copy(update={"version": "1.0.1"})
    assert changed.digest() != sante.digest()


def test_create_mandate_kwargs(sante: MandateTemplate) -> None:
    kwargs = sante.create_mandate_kwargs()
    assert kwargs["allowed_actions"] == list(sante.perimeter.allowed_actions)
    assert kwargs["forbidden_actions"] == list(sante.perimeter.forbidden_actions)
    assert kwargs["delegation_allowed"] is False
    assert kwargs["max_amount"] == "100"
    assert kwargs["currency"] == "EUR"
    assert kwargs["amount_actions"] == ["supplies.order"]
    assert kwargs["metadata"] == {
        "template_id": "agent-sante-rgpd",
        "template_version": "1.1.0",
        "template_digest": sante.digest(),
    }


def test_principal_may_lower_the_ceiling_but_not_raise_it(sante: MandateTemplate) -> None:
    assert sante.create_mandate_kwargs(max_amount="40")["max_amount"] == "40"
    assert sante.create_mandate_kwargs(max_amount="100")["max_amount"] == "100"
    for bad in ("100.01", "250", "0", "-5", "1e2", "abc"):
        with pytest.raises(ValueError):
            sante.create_mandate_kwargs(max_amount=bad)


def test_principal_metadata_is_merged_and_template_keys_are_reserved(
    sante: MandateTemplate,
) -> None:
    kwargs = sante.create_mandate_kwargs(metadata={"client_ref": "CAB-001"})
    assert kwargs["metadata"] == {
        "client_ref": "CAB-001",
        "template_id": "agent-sante-rgpd",
        "template_version": "1.1.0",
        "template_digest": sante.digest(),
    }
    for key in ("template_id", "template_digest", "template_other"):
        with pytest.raises(ValueError, match="reserved"):
            sante.create_mandate_kwargs(metadata={key: "x"})


def test_ceiling_override_needs_a_template_ceiling() -> None:
    with pytest.raises(ValueError, match="no amount ceiling"):
        _template().create_mandate_kwargs(max_amount="10")


# --- End to end: real mandate, real tokens --------------------------------------------


async def test_end_to_end_allowed_actions_get_tokens(sante: MandateTemplate) -> None:
    mandate = await _mandate_from(sante)
    assert mandate["status"] == "created", mandate
    for action in (
        "patient_record.read",
        "appointment.book",
        "letter.draft",
        "patient_message.draft",
    ):
        result = await _token(mandate["mandate_id"], action)
        assert "token" in result, (action, result)
    order = await _token(
        mandate["mandate_id"], "supplies.order", {"amount": "35.90", "currency": "EUR"}
    )
    assert "token" in order, order


@pytest.mark.parametrize(
    ("action", "detail"),
    [
        ("prescription.create", "forbidden:prescription"),
        ("diagnosis.record", "forbidden:diagnosis"),
        ("patient_record.export", "forbidden:patient_record.export"),
        ("patient_message.send", "forbidden:patient_message.send"),
        ("letter.send", "forbidden:letter.send"),
        ("agent.create", "forbidden:agent.create"),
        ("invoice.pay", "not_allowed:invoice.pay"),
    ],
)
async def test_end_to_end_forbidden_actions_get_no_token(
    sante: MandateTemplate, action: str, detail: str
) -> None:
    mandate = await _mandate_from(sante)
    result = await _token(mandate["mandate_id"], action)
    assert result.get("denied") is True, result
    assert result["reason"] == "action_out_of_scope"
    assert result["detail"] == detail


async def test_end_to_end_ceiling_is_enforced(sante: MandateTemplate) -> None:
    mandate = await _mandate_from(sante, max_amount="50")
    result = await _token(
        mandate["mandate_id"], "supplies.order", {"amount": "50.01", "currency": "EUR"}
    )
    assert result["detail"] == "amount_above_limit:50 EUR"


async def test_end_to_end_no_sub_agent(sante: MandateTemplate) -> None:
    mandate = await _mandate_from(sante)
    sub = json.loads(
        await create_mandate(
            principal_id=AGENT,
            agent_id="agent:sub",
            scope="read records",
            legal_basis_regulation="Mandat de gestion",
            legal_basis_article="Art. 1984 Code civil",
            duration_hours=1,
            parent_mandate_id=mandate["mandate_id"],
            allowed_actions=["patient_record.read"],
        )
    )
    assert sub["code"] == "delegation_not_allowed"


async def test_end_to_end_template_is_recorded_in_mandate_and_proof(
    sante: MandateTemplate, temp_db: Path
) -> None:
    mandate = await _mandate_from(sante)
    async with aiosqlite.connect(str(temp_db)) as db:
        cursor = await db.execute(
            "SELECT metadata_json, perimeter_json FROM mandates WHERE id = ?",
            (mandate["mandate_id"],),
        )
        metadata_json, perimeter_json = await cursor.fetchone()
    assert json.loads(metadata_json) == sante.create_mandate_kwargs()["metadata"]
    assert Perimeter.from_json(perimeter_json) == sante.perimeter
    proof = json.loads(await get_proof(mandate["mandate_id"]))
    assert proof["mandate"]["metadata"] == sante.create_mandate_kwargs()["metadata"]
    assert proof["mandate"]["perimeter"] == sante.perimeter.canonical()


async def test_end_to_end_with_principal_metadata(sante: MandateTemplate) -> None:
    mandate = await _mandate_from(sante, metadata={"client_ref": "CAB-001"})
    assert mandate["status"] == "created", mandate
    proof = json.loads(await get_proof(mandate["mandate_id"]))
    assert proof["mandate"]["metadata"]["client_ref"] == "CAB-001"
    assert proof["mandate"]["metadata"]["template_id"] == "agent-sante-rgpd"


# --- Documentation ---------------------------------------------------------------------


def test_documented_json_is_the_template(sante: MandateTemplate) -> None:
    text = DOC.read_text(encoding="utf-8")
    blocks = re.findall(r"```json\n(.*?)\n```", text.replace("\r\n", "\n"), re.DOTALL)
    assert blocks, "no json block in the template documentation"
    assert blocks[0] == sante.to_json(indent=2)
