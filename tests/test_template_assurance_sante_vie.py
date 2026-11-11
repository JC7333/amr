"""Tests for the ``agent-assurance-sante-vie`` template.

Every decision on an application stays with a human: the template forbids accepting or
refusing an application, setting the final premium, sending a message to the insured
person, using the result of a genetic test, exporting health data and creating a
sub-agent. The end-to-end tests create a real mandate from the template and ask for
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
    AGENT_ASSURANCE_SANTE_VIE_ID,
    AGENT_CREDIT_ID,
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
DOC = ROOT / "docs" / "templates" / "agent-assurance-sante-vie.md"
README = ROOT / "README.md"
PRINCIPAL = "org:insurer"
AGENT = "agent:underwriting-assistant"

ALLOWED = (
    "underwriting_file.read",
    "risk_assessment.draft",
    "premium.propose",
    "contract_documents.draft",
    "insured_message.draft",
)
FORBIDDEN = (
    "application.accept",
    "application.refuse",
    "premium.set",
    "insured_message.send",
    "genetic_test_result.use",
    "health_data.export",
    "agent.create",
)
REFERENCES = (
    "Regulation (EU) 2024/1689 (AI Act), Annex III, point 5(c)",
    "Regulation (EU) 2024/1689 (AI Act), Art. 26",
    "Regulation (EU) 2024/1689 (AI Act), Art. 27",
    "Regulation (EU) 2024/1689 (AI Act), Art. 86",
    "Regulation (EU) 2016/679 (GDPR), Art. 9",
    "Regulation (EU) 2016/679 (GDPR), Art. 22",
    "Code de la santé publique (FR), Art. L1141-1",
    "Code de la santé publique (FR), Art. L1141-5",
    "Code des assurances (FR), Art. L113-2-1",
    "Code de la mutualité (FR), Art. L112-1",
)


@pytest.fixture(autouse=True)
def isolated_signing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    priv = tmp_path / "test_key.pem"
    pub = tmp_path / "test_key.pub"
    monkeypatch.setattr("amr.config.settings.signing_key_path", priv)
    monkeypatch.setattr("amr.config.settings.public_key_path", pub)
    generate_signing_key(priv, pub)


@pytest.fixture
def insurance() -> MandateTemplate:
    return get_template(AGENT_ASSURANCE_SANTE_VIE_ID)


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
            audience="runtime://underwriting",
            action_metadata_json="{}",
            action_type=action_type,
        )
    )


# --- Registry ------------------------------------------------------------------------


def test_registry_lists_the_template(insurance: MandateTemplate) -> None:
    ids = list_templates()
    assert AGENT_ASSURANCE_SANTE_VIE_ID in ids
    assert {AGENT_CREDIT_ID, AGENT_RH_RECRUTEMENT_ID, AGENT_SANTE_RGPD_ID} <= set(ids)
    assert insurance.template_id == "agent-assurance-sante-vie"
    assert insurance.sector == "insurance"
    assert insurance.version == "1.0.0"


def test_other_templates_are_unchanged_by_the_new_one() -> None:
    sante = get_template(AGENT_SANTE_RGPD_ID)
    assert sante.version == "1.2.0"
    assert sante.digest() == "f150977f08f9f3c8f4e9a8e88ed86c42e53649c2157aa028896836a7f00a2391"
    rh = get_template(AGENT_RH_RECRUTEMENT_ID)
    assert rh.version == "1.0.0"
    assert rh.digest() == "de7e4fd23121d039957fbdb757ca230fa8355ba5024649a6f885868971a1b215"
    credit = get_template(AGENT_CREDIT_ID)
    assert credit.version == "1.0.0"
    assert credit.digest() == "3a6d5d5df9ac2a7016a16544c1dd72cf2d6a7bcb6626bb3b82b1a573fda335a4"


def test_digest_is_pinned(insurance: MandateTemplate) -> None:
    # Any change to the template content must come with a new version and a new pin.
    assert insurance.digest() == "fe29e7bee8403654726be71ddd5ddd472f26e5da9311fa5dac0cbb488f56b15a"


# --- Perimeter -----------------------------------------------------------------------


def test_exact_lists(insurance: MandateTemplate) -> None:
    p = insurance.perimeter
    assert set(p.allowed_actions) == set(ALLOWED)
    assert set(p.forbidden_actions) == set(FORBIDDEN)
    assert p.delegation_allowed is False
    assert p.max_amount is None
    assert p.amount_actions == ()
    assert p.risk_classes == ()


def test_allowed_actions_need_no_amount(insurance: MandateTemplate) -> None:
    for action in ALLOWED:
        assert insurance.perimeter.check_action(action, {}) is None, action


@pytest.mark.parametrize("action", FORBIDDEN)
def test_forbidden_actions_and_their_sub_types(insurance: MandateTemplate, action: str) -> None:
    p = insurance.perimeter
    assert p.check_action(action, {}) == f"forbidden:{action}"
    assert p.check_action(f"{action}.batch", {}) == f"forbidden:{action}"


def test_decisions_about_a_person_are_never_allowed(insurance: MandateTemplate) -> None:
    p = insurance.perimeter
    assert "*" not in p.allowed_actions
    assert not any(a.endswith("*") for a in p.allowed_actions)
    for action in (
        "application.approve",
        "application.close",
        "policy.issue",
        "premium",
        "exclusion.add",
        "claim.settle",
        "genetic_test.request",
        "health_data.share",
        "email.send",
    ):
        assert (p.check_action(action, {}) or "").startswith("not_allowed:"), action


def test_catalog_says_forbidden_for_every_forbidden_action(insurance: MandateTemplate) -> None:
    for action in FORBIDDEN:
        assert insurance.actions[action].startswith("Forbidden:"), action
    for action in ALLOWED:
        assert not insurance.actions[action].startswith("Forbidden:"), action


def test_stewardship_is_provisional_with_no_reviewer(insurance: MandateTemplate) -> None:
    assert insurance.stewardship is not None
    assert insurance.stewardship.status == "provisional"
    assert insurance.stewardship.reviewers == ()
    assert "insurance sector" in insurance.stewardship.handover


def test_legal_references_exact_and_to_verify(insurance: MandateTemplate) -> None:
    assert tuple(ref.reference for ref in insurance.legal_references) == REFERENCES
    assert all(ref.status == "to_verify" for ref in insurance.legal_references)


def test_reference_topics(insurance: MandateTemplate) -> None:
    topics = {ref.reference: ref.topic for ref in insurance.legal_references}
    assert "life and health insurance" in topics[REFERENCES[0]]
    assert "Annex III, point 5(c)" in topics[REFERENCES[2]]
    assert "genetic data" in topics[REFERENCES[4]]
    assert "genetic test" in topics[REFERENCES[6]]
    assert "cancer or hepatitis C" in topics[REFERENCES[7]]
    assert "Borrower insurance" in topics[REFERENCES[8]]
    assert "no contribution based on health status" in topics[REFERENCES[9]]


def test_kwargs_and_metadata(insurance: MandateTemplate) -> None:
    kwargs = insurance.create_mandate_kwargs()
    assert kwargs["delegation_allowed"] is False
    assert kwargs["max_amount"] is None
    assert "risk_classes" not in kwargs
    assert kwargs["metadata"] == {
        "template_id": "agent-assurance-sante-vie",
        "template_version": "1.0.0",
        "template_digest": insurance.digest(),
        "template_status": "provisional",
    }
    with pytest.raises(ValueError, match="no amount ceiling"):
        insurance.create_mandate_kwargs(max_amount="10")


def test_mandate_may_add_a_risk_class(insurance: MandateTemplate) -> None:
    kwargs = insurance.create_mandate_kwargs(
        risk_classes=[{"name": "proposal", "actions": ["premium.propose"], "max_token_seconds": 60}]
    )
    assert [rc["name"] for rc in kwargs["risk_classes"]] == ["proposal"]


# --- End to end ----------------------------------------------------------------------


async def test_end_to_end_allowed_actions_get_tokens(insurance: MandateTemplate) -> None:
    mandate = await _mandate_from(insurance)
    assert mandate["status"] == "created", mandate
    for action in ALLOWED:
        result = await _token(mandate["mandate_id"], action)
        assert "token" in result, (action, result)


@pytest.mark.parametrize("action", FORBIDDEN)
async def test_end_to_end_forbidden_actions_get_no_token(
    insurance: MandateTemplate, action: str
) -> None:
    mandate = await _mandate_from(insurance)
    result = await _token(mandate["mandate_id"], action)
    assert result.get("denied") is True, result
    assert result["reason"] == "action_out_of_scope"
    assert result["detail"] == f"forbidden:{action}"


async def test_end_to_end_no_sub_agent(insurance: MandateTemplate) -> None:
    mandate = await _mandate_from(insurance)
    sub = json.loads(
        await create_mandate(
            principal_id=AGENT,
            agent_id="agent:sub",
            scope="read underwriting files",
            legal_basis_regulation="Mandat de gestion",
            legal_basis_article="Art. 1984 Code civil",
            duration_hours=1,
            parent_mandate_id=mandate["mandate_id"],
            allowed_actions=["underwriting_file.read"],
        )
    )
    assert sub["code"] == "delegation_not_allowed"


async def test_end_to_end_template_recorded_in_mandate_and_proof(
    insurance: MandateTemplate, temp_db: Path
) -> None:
    mandate = await _mandate_from(insurance, metadata={"client_ref": "UW-001"})
    async with aiosqlite.connect(str(temp_db)) as db:
        cursor = await db.execute(
            "SELECT perimeter_json FROM mandates WHERE id = ?", (mandate["mandate_id"],)
        )
        (perimeter_json,) = await cursor.fetchone()
    assert Perimeter.from_json(perimeter_json) == insurance.perimeter
    proof = json.loads(await get_proof(mandate["mandate_id"]))
    assert proof["mandate"]["metadata"]["template_id"] == "agent-assurance-sante-vie"
    assert proof["mandate"]["metadata"]["template_status"] == "provisional"
    assert proof["mandate"]["metadata"]["client_ref"] == "UW-001"


# --- Documentation -------------------------------------------------------------------


def _doc() -> str:
    return DOC.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_documented_json_is_the_template(insurance: MandateTemplate) -> None:
    blocks = re.findall(r"```json\n(.*?)\n```", _doc(), re.DOTALL)
    assert blocks, "no json block in the template documentation"
    assert blocks[0] == insurance.to_json(indent=2)


def test_doc_table_names_every_action(insurance: MandateTemplate) -> None:
    table = _doc().split("## Provisional baseline")[0]
    for action in (*ALLOWED, *FORBIDDEN):
        assert f"`{action}`" in table, action


def test_doc_says_references_are_to_verify_and_not_compliance() -> None:
    text = " ".join(_doc().replace("\n> ", "\n").split())
    assert "marked `to_verify`" in text
    assert "does not make an underwriting process compliant" in text
    assert "`forbidden:<type>`" in text
    assert "Claims handling is not part of this template" in text
    assert "the principal checks the ones that apply to it" in text
    assert "does not check which data the agent used" in text
    assert "it does not stop an agent from reading a genetic result" in text


def test_readme_lists_the_template() -> None:
    text = " ".join(README.read_text(encoding="utf-8").split())
    assert "`agent-assurance-sante-vie`, covers an agent assisting a life or health" in text
    assert "Every decision on an application stays with a human." in text
    assert "sector templates (health, recruitment, credit, life and health insurance)" in text
    assert "`docs/templates/agent-assurance-sante-vie.md`" in text
