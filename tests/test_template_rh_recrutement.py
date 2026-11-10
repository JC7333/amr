"""Tests for the ``agent-rh-recrutement`` template.

Every decision about a candidate stays with a human: the template forbids rejecting,
selecting, sending an offer, a rejection or any candidate message, emotion recognition,
biometric categorisation, inferring sensitive data, exporting candidate data and creating
a sub-agent. The end-to-end tests create a real mandate from the template and ask for
tokens.
"""

import json
import re
from pathlib import Path

import aiosqlite
import pytest

from amr.crypto.signing import generate_signing_key
from amr.models.perimeter import Perimeter
from amr.templates import (
    AGENT_RH_RECRUTEMENT_ID,
    AGENT_SANTE_RGPD_ID,
    get_template,
    list_templates,
)
from amr.templates.base import MandateTemplate
from amr.tools.create_mandate import create_mandate
from amr.tools.get_proof import get_proof
from amr.tools.issue_action_token import issue_action_token

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "templates" / "agent-rh-recrutement.md"
README = ROOT / "README.md"
PRINCIPAL = "org:employer"
AGENT = "agent:recruitment-assistant"

ALLOWED = (
    "application.read",
    "job_posting.draft",
    "shortlist.propose",
    "interview.propose",
    "interview.book",
    "candidate_message.draft",
)
FORBIDDEN = (
    "candidate.reject",
    "candidate.select",
    "offer.send",
    "rejection.send",
    "candidate_message.send",
    "emotion_recognition",
    "biometric_categorisation",
    "sensitive_data.infer",
    "candidate_data.export",
    "agent.create",
)
REFERENCES = (
    "Regulation (EU) 2024/1689 (AI Act), Annex III, point 4(a)",
    "Regulation (EU) 2024/1689 (AI Act), Art. 26, including Art. 26(7)",
    "Regulation (EU) 2024/1689 (AI Act), Art. 5(1)(f)",
    "Regulation (EU) 2016/679 (GDPR), Art. 22",
    "Code du travail (FR), Art. L1132-1",
    "Code du travail (FR), Art. L1221-8",
    "Code du travail (FR), Art. L1221-9",
)


@pytest.fixture(autouse=True)
def isolated_signing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    priv = tmp_path / "test_key.pem"
    pub = tmp_path / "test_key.pub"
    monkeypatch.setattr("amr.config.settings.signing_key_path", priv)
    monkeypatch.setattr("amr.config.settings.public_key_path", pub)
    generate_signing_key(priv, pub)


@pytest.fixture
def rh() -> MandateTemplate:
    return get_template(AGENT_RH_RECRUTEMENT_ID)


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


async def _token(mandate_id: str, action_type: str) -> dict:
    return json.loads(
        await issue_action_token(
            mandate_id=mandate_id,
            agent_id=AGENT,
            action=f"test {action_type}",
            audience="runtime://recruitment",
            action_metadata_json="{}",
            action_type=action_type,
        )
    )


# --- Registry ------------------------------------------------------------------------


def test_registry_lists_both_templates(rh: MandateTemplate) -> None:
    assert AGENT_RH_RECRUTEMENT_ID in list_templates()
    assert AGENT_SANTE_RGPD_ID in list_templates()
    assert list_templates() == sorted(list_templates())
    assert rh.template_id == "agent-rh-recrutement"
    assert rh.sector == "employment"
    assert rh.version == "1.0.0"


def test_health_template_is_unchanged_by_the_new_one() -> None:
    sante = get_template(AGENT_SANTE_RGPD_ID)
    assert sante.version == "1.2.0"
    assert sante.digest() == "f150977f08f9f3c8f4e9a8e88ed86c42e53649c2157aa028896836a7f00a2391"


def test_digest_is_pinned(rh: MandateTemplate) -> None:
    # Any change to the template content must come with a new version and a new pin.
    assert rh.digest() == "de7e4fd23121d039957fbdb757ca230fa8355ba5024649a6f885868971a1b215"


# --- Perimeter -----------------------------------------------------------------------


def test_exact_lists(rh: MandateTemplate) -> None:
    p = rh.perimeter
    assert set(p.allowed_actions) == set(ALLOWED)
    assert set(p.forbidden_actions) == set(FORBIDDEN)
    assert p.delegation_allowed is False
    assert p.max_amount is None
    assert p.amount_actions == ()
    assert p.risk_classes == ()


def test_allowed_actions_need_no_amount(rh: MandateTemplate) -> None:
    for action in ALLOWED:
        assert rh.perimeter.check_action(action, {}) is None, action


@pytest.mark.parametrize("action", FORBIDDEN)
def test_forbidden_actions_and_their_sub_types(rh: MandateTemplate, action: str) -> None:
    p = rh.perimeter
    assert p.check_action(action, {}) == f"forbidden:{action}"
    assert p.check_action(f"{action}.batch", {}) == f"forbidden:{action}"


def test_decisions_about_a_person_are_never_allowed(rh: MandateTemplate) -> None:
    p = rh.perimeter
    assert "*" not in p.allowed_actions
    assert not any(a.endswith("*") for a in p.allowed_actions)
    for action in (
        "candidate.hire",
        "candidate.score",
        "application.close",
        "application.export",
        "job_posting.publish",
        "candidate_message",
        "email.send",
    ):
        assert (p.check_action(action, {}) or "").startswith("not_allowed:"), action


def test_catalog_says_forbidden_for_every_forbidden_action(rh: MandateTemplate) -> None:
    for action in FORBIDDEN:
        assert rh.actions[action].startswith("Forbidden:"), action
    for action in ALLOWED:
        assert not rh.actions[action].startswith("Forbidden:"), action


def test_stewardship_is_provisional_with_no_reviewer(rh: MandateTemplate) -> None:
    assert rh.stewardship is not None
    assert rh.stewardship.status == "provisional"
    assert rh.stewardship.reviewers == ()
    assert "employment sector" in rh.stewardship.handover


def test_legal_references_exact_and_to_verify(rh: MandateTemplate) -> None:
    assert tuple(ref.reference for ref in rh.legal_references) == REFERENCES
    assert all(ref.status == "to_verify" for ref in rh.legal_references)


def test_kwargs_and_metadata(rh: MandateTemplate) -> None:
    kwargs = rh.create_mandate_kwargs()
    assert kwargs["delegation_allowed"] is False
    assert kwargs["max_amount"] is None
    assert "risk_classes" not in kwargs
    assert kwargs["metadata"] == {
        "template_id": "agent-rh-recrutement",
        "template_version": "1.0.0",
        "template_digest": rh.digest(),
        "template_status": "provisional",
    }
    with pytest.raises(ValueError, match="no amount ceiling"):
        rh.create_mandate_kwargs(max_amount="10")


def test_mandate_may_add_a_risk_class(rh: MandateTemplate) -> None:
    kwargs = rh.create_mandate_kwargs(
        risk_classes=[{"name": "booking", "actions": ["interview.book"], "max_token_seconds": 60}]
    )
    assert [rc["name"] for rc in kwargs["risk_classes"]] == ["booking"]


# --- End to end ----------------------------------------------------------------------


async def test_end_to_end_allowed_actions_get_tokens(rh: MandateTemplate) -> None:
    mandate = await _mandate_from(rh)
    assert mandate["status"] == "created", mandate
    for action in ALLOWED:
        result = await _token(mandate["mandate_id"], action)
        assert "token" in result, (action, result)


@pytest.mark.parametrize("action", FORBIDDEN)
async def test_end_to_end_forbidden_actions_get_no_token(
    rh: MandateTemplate, action: str
) -> None:
    mandate = await _mandate_from(rh)
    result = await _token(mandate["mandate_id"], action)
    assert result.get("denied") is True, result
    assert result["reason"] == "action_out_of_scope"
    assert result["detail"] == f"forbidden:{action}"


async def test_end_to_end_no_sub_agent(rh: MandateTemplate) -> None:
    mandate = await _mandate_from(rh)
    sub = json.loads(
        await create_mandate(
            principal_id=AGENT,
            agent_id="agent:sub",
            scope="read applications",
            legal_basis_regulation="Mandat de gestion",
            legal_basis_article="Art. 1984 Code civil",
            duration_hours=1,
            parent_mandate_id=mandate["mandate_id"],
            allowed_actions=["application.read"],
        )
    )
    assert sub["code"] == "delegation_not_allowed"


async def test_end_to_end_template_recorded_in_mandate_and_proof(
    rh: MandateTemplate, temp_db: Path
) -> None:
    mandate = await _mandate_from(rh, metadata={"client_ref": "RH-001"})
    async with aiosqlite.connect(str(temp_db)) as db:
        cursor = await db.execute(
            "SELECT perimeter_json FROM mandates WHERE id = ?", (mandate["mandate_id"],)
        )
        (perimeter_json,) = await cursor.fetchone()
    assert Perimeter.from_json(perimeter_json) == rh.perimeter
    proof = json.loads(await get_proof(mandate["mandate_id"]))
    assert proof["mandate"]["metadata"]["template_id"] == "agent-rh-recrutement"
    assert proof["mandate"]["metadata"]["template_status"] == "provisional"
    assert proof["mandate"]["metadata"]["client_ref"] == "RH-001"


# --- Documentation -------------------------------------------------------------------


def _doc() -> str:
    return DOC.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_documented_json_is_the_template(rh: MandateTemplate) -> None:
    blocks = re.findall(r"```json\n(.*?)\n```", _doc(), re.DOTALL)
    assert blocks, "no json block in the template documentation"
    assert blocks[0] == rh.to_json(indent=2)


def test_doc_table_names_every_action(rh: MandateTemplate) -> None:
    table = _doc().split("## Provisional baseline")[0]
    for action in (*ALLOWED, *FORBIDDEN):
        assert f"`{action}`" in table, action


def test_doc_says_references_are_to_verify_and_not_compliance() -> None:
    text = _doc()
    assert "marked `to_verify`" in text
    assert "does not make a recruitment" in text
    assert "`forbidden:<type>`" in text
    assert "does not check that a booked interview" in text


def test_readme_lists_the_template() -> None:
    text = " ".join(README.read_text(encoding="utf-8").split())
    assert "`agent-rh-recrutement`, covers an agent assisting a recruiter" in text
    assert "Every decision to reject, select or make an offer stays with a human." in text
    assert "sector templates (health, recruitment)" in text
    assert "`docs/templates/agent-rh-recrutement.md`" in text
