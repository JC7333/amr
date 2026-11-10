"""Tests for the template baseline: stewardship block and minimum thresholds per risk class.

A template published by the registry says it is provisional, who holds it and which
practitioners reviewed it (none recorded yet), and that block is covered by its digest.
Its risk classes are minimum thresholds: a mandate built from it may tighten them, never
loosen them.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from amr.crypto.signing import generate_signing_key
from amr.models.perimeter import Perimeter, RiskClass
from amr.templates import AGENT_SANTE_RGPD_ID, get_template, list_templates
from amr.templates.base import MandateTemplate, Stewardship
from amr.tools.create_mandate import create_mandate
from amr.tools.issue_action_token import issue_action_token

DOC = Path(__file__).resolve().parent.parent / "docs" / "templates" / "agent-sante-rgpd.md"
PRINCIPAL = "org:cabinet-medical"
AGENT = "agent:assistant-cabinet"
FLOOR = {
    "name": "irreversible",
    "actions": ["supplies.order"],
    "max_token_seconds": 30,
    "registry_check": True,
}


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


def _stewardship(**changes: object) -> Stewardship:
    fields: dict[str, object] = {
        "status": "provisional",
        "held_by": "AMR registry",
        "handover": "Until a body of the sector takes it over.",
    }
    fields.update(changes)
    return Stewardship(**fields)  # type: ignore[arg-type]


def _classes(sante: MandateTemplate, given: list[dict]) -> list[dict]:
    return sante.create_mandate_kwargs(risk_classes=given)["risk_classes"]


# --- Stewardship ------------------------------------------------------------------------


def test_every_registered_template_says_who_holds_it() -> None:
    for template_id in list_templates():
        assert get_template(template_id).stewardship is not None, template_id


def test_health_template_is_a_provisional_baseline_with_no_reviewer(
    sante: MandateTemplate,
) -> None:
    assert sante.version == "1.2.0"
    assert sante.stewardship is not None
    assert sante.stewardship.status == "provisional"
    assert sante.stewardship.reviewers == ()
    assert sante.stewardship.held_by.strip()
    assert "sector" in sante.stewardship.handover


def test_stewardship_is_in_the_canonical_form_and_the_digest(sante: MandateTemplate) -> None:
    assert sante.canonical()["stewardship"] == {
        "status": "provisional",
        "held_by": sante.stewardship.held_by,  # type: ignore[union-attr]
        "handover": sante.stewardship.handover,  # type: ignore[union-attr]
        "reviewers": [],
    }
    taken_over = sante.model_copy(
        update={"stewardship": sante.stewardship.model_copy(update={"status": "sector"})}  # type: ignore[union-attr]
    )
    assert taken_over.digest() != sante.digest()
    reviewed = sante.model_copy(
        update={"stewardship": sante.stewardship.model_copy(  # type: ignore[union-attr]
            update={"reviewers": ("Reviewer A",)}
        )}
    )
    assert reviewed.digest() != sante.digest()


def test_template_without_stewardship_keeps_its_canonical_form(sante: MandateTemplate) -> None:
    bare = sante.model_copy(update={"stewardship": None})
    assert "stewardship" not in bare.canonical()
    assert "template_status" not in bare.create_mandate_kwargs()["metadata"]


def test_status_is_copied_into_the_mandate_metadata(sante: MandateTemplate) -> None:
    assert sante.create_mandate_kwargs()["metadata"]["template_status"] == "provisional"
    with pytest.raises(ValueError, match="reserved"):
        sante.create_mandate_kwargs(metadata={"template_status": "sector"})


def test_stewardship_fields_are_checked() -> None:
    assert _stewardship(status="sector").status == "sector"
    for bad in (
        {"status": "final"},
        {"held_by": ""},
        {"held_by": "   "},
        {"handover": " "},
        {"reviewers": ("",)},
        {"reviewers": ("A", "A")},
        {"reviewers": ("x" * 201,)},
        {"unknown": "x"},
    ):
        with pytest.raises(ValidationError):
            _stewardship(**bad)


def test_stewardship_is_immutable(sante: MandateTemplate) -> None:
    with pytest.raises(ValidationError):
        sante.stewardship.status = "sector"  # type: ignore[union-attr,misc]


def test_template_page_says_provisional_and_names_no_reviewer(sante: MandateTemplate) -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "**provisional**" in text
    assert "practitioner reviewers: none recorded" in text
    assert '"reviewers": []' in text
    assert '"status": "provisional"' in text


# --- Minimum thresholds per risk class --------------------------------------------------


def test_health_template_sets_a_threshold_for_irreversible_orders(sante: MandateTemplate) -> None:
    assert [rc.canonical() for rc in sante.perimeter.risk_classes] == [FLOOR]
    assert sante.create_mandate_kwargs()["risk_classes"] == [FLOOR]


def test_mandate_may_shorten_the_window(sante: MandateTemplate) -> None:
    tighter = {**FLOOR, "max_token_seconds": 10}
    assert _classes(sante, [tighter]) == [tighter]
    assert _classes(sante, [FLOOR]) == [FLOOR]


def test_mandate_may_widen_the_class(sante: MandateTemplate) -> None:
    wider = {**FLOOR, "actions": ["supplies.order", "appointment.book"]}
    assert _classes(sante, [wider]) == [{**wider, "actions": sorted(wider["actions"])}]
    for pattern in ("supplies.*", "supplies", "*"):
        covering = {**FLOOR, "actions": [pattern]}
        assert _classes(sante, [covering]) == [covering]


def test_mandate_may_add_a_class_and_keeps_the_template_ones(sante: MandateTemplate) -> None:
    booking = {"name": "booking", "actions": ["appointment.book"], "max_token_seconds": 60}
    assert _classes(sante, [booking]) == [booking, FLOOR]
    assert _classes(sante, [RiskClass.model_validate(booking)]) == [booking, FLOOR]


def test_mandate_may_not_lengthen_the_window(sante: MandateTemplate) -> None:
    with pytest.raises(ValueError, match="never loosen") as excinfo:
        sante.create_mandate_kwargs(risk_classes=[{**FLOOR, "max_token_seconds": 31}])
    assert "31 s asked, template minimum threshold 30 s" in str(excinfo.value)


def test_mandate_may_not_drop_the_registry_check(sante: MandateTemplate) -> None:
    with pytest.raises(ValueError, match="registry_check cannot be dropped"):
        sante.create_mandate_kwargs(risk_classes=[{**FLOOR, "registry_check": False}])


@pytest.mark.parametrize(
    "actions", [["appointment.book"], ["supplies.order.small"], ["supplies.orders"], ["supplie.*"]]
)
def test_mandate_may_not_leave_an_action_out(sante: MandateTemplate, actions: list[str]) -> None:
    with pytest.raises(ValueError, match=r"actions left out: \['supplies.order'\]"):
        sante.create_mandate_kwargs(risk_classes=[{**FLOOR, "actions": actions}])


def test_bad_risk_class_input_is_refused(sante: MandateTemplate) -> None:
    with pytest.raises(ValueError, match="unique"):
        sante.create_mandate_kwargs(risk_classes=[FLOOR, FLOOR])
    with pytest.raises(ValueError, match="list of risk classes"):
        sante.create_mandate_kwargs(risk_classes=FLOOR)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        sante.create_mandate_kwargs(risk_classes=[{**FLOOR, "max_token_seconds": 0}])


def test_a_template_without_classes_accepts_new_ones() -> None:
    template = MandateTemplate(
        template_id="demo",
        version="1.0.0",
        title="Demo",
        sector="demo",
        summary="Demo template",
        perimeter=Perimeter(allowed_actions=("doc.read",)),
        actions={"doc.read": "Read a document."},
        default_duration_hours=1,
    )
    assert "risk_classes" not in template.create_mandate_kwargs()
    added = {"name": "slow", "actions": ["doc.read"], "max_token_seconds": 5}
    assert template.create_mandate_kwargs(risk_classes=[added])["risk_classes"] == [added]


# --- End to end -------------------------------------------------------------------------


async def _mandate(sante: MandateTemplate, **kwargs: object) -> dict:
    return json.loads(
        await create_mandate(
            principal_id=PRINCIPAL,
            agent_id=AGENT,
            scope=sante.summary,
            legal_basis_regulation="Mandat de gestion",
            legal_basis_article="Art. 1984 Code civil",
            duration_hours=sante.default_duration_hours,
            **sante.create_mandate_kwargs(**kwargs),  # type: ignore[arg-type]
        )
    )


async def _order_token(mandate_id: str) -> dict:
    return json.loads(
        await issue_action_token(
            mandate_id=mandate_id,
            agent_id=AGENT,
            action="order gloves",
            audience="runtime://cabinet",
            action_metadata_json=json.dumps({"amount": "20", "currency": "EUR"}),
            action_type="supplies.order",
        )
    )


def _claims(token: dict) -> dict:
    import base64

    payload = token["token"].split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


async def test_end_to_end_order_token_follows_the_threshold(sante: MandateTemplate) -> None:
    mandate = await _mandate(sante)
    assert mandate["status"] == "created", mandate
    claims = _claims(await _order_token(mandate["mandate_id"]))
    assert claims["exp"] - claims["iat"] <= 30
    assert claims["amr_registry_check"] is True


async def test_end_to_end_tightened_threshold_is_enforced(sante: MandateTemplate) -> None:
    mandate = await _mandate(sante, risk_classes=[{**FLOOR, "max_token_seconds": 5}])
    assert mandate["status"] == "created", mandate
    claims = _claims(await _order_token(mandate["mandate_id"]))
    assert claims["exp"] - claims["iat"] <= 5
