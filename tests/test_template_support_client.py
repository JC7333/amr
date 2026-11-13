"""Tests for the ``agent-support-client`` template.

Every decision that goes against the customer stays with a human: the template forbids
refusing a refund or a complaint, terminating a contract, closing an account, changing
payment details, exporting the customer's data and creating a sub-agent. Granting a
commercial gesture is allowed only with an amount at or below the ceiling. The end-to-end
tests create a real mandate from the template and ask for tokens.
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
    AGENT_SUPPORT_CLIENT_ID,
    get_template,
    list_templates,
)
from amr.templates.base import MandateTemplate
from amr.tools.create_mandate import create_mandate
from amr.tools.get_proof import get_proof
from amr.tools.issue_action_token import issue_action_token

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "templates" / "agent-support-client.md"
README = ROOT / "README.md"
PRINCIPAL = "org:retailer"
AGENT = "agent:support-assistant"
GESTURE = "commercial_gesture.grant"

ALLOWED = (
    "customer_account.read",
    "ticket.answer",
    "ticket.route",
    "commercial_gesture.propose",
    GESTURE,
)
FORBIDDEN = (
    "refund.refuse",
    "complaint.refuse",
    "contract.terminate",
    "account.close",
    "payment_details.change",
    "customer_data.export",
    "agent.create",
)
REFERENCES = (
    "Regulation (EU) 2024/1689 (AI Act), Art. 50(1)",
    "Regulation (EU) 2016/679 (GDPR), Art. 22",
    "Code de la consommation (FR), Art. L612-1",
    "Code de la consommation (FR), Art. L616-1",
)


def _eur(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "EUR"}


@pytest.fixture(autouse=True)
def isolated_signing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    priv = tmp_path / "test_key.pem"
    pub = tmp_path / "test_key.pub"
    monkeypatch.setattr("amr.config.settings.signing_key_path", priv)
    monkeypatch.setattr("amr.config.settings.public_key_path", pub)
    generate_signing_key(priv, pub)


@pytest.fixture
def support() -> MandateTemplate:
    return get_template(AGENT_SUPPORT_CLIENT_ID)


async def _mandate_from(template: MandateTemplate, **kwargs: object) -> dict:
    args = template.create_mandate_kwargs(**kwargs)  # type: ignore[arg-type]
    return json.loads(
        await create_mandate(
            principal_id=PRINCIPAL,
            agent_id=AGENT,
            scope=template.summary,
            legal_basis_regulation="Delegation of authority",
            legal_basis_article="Section 2",
            duration_hours=template.default_duration_hours,
            **args,
        )
    )


async def _token(mandate_id: str, action_type: str, metadata: dict | None = None) -> dict:
    return json.loads(
        await issue_action_token(
            mandate_id=mandate_id,
            agent_id=AGENT,
            action=f"test {action_type} {metadata}",
            audience="runtime://support",
            action_metadata_json=json.dumps(metadata or {}),
            action_type=action_type,
        )
    )


# --- Registry ------------------------------------------------------------------------


def test_registry_lists_exactly_the_five_templates(support: MandateTemplate) -> None:
    assert list_templates() == [
        AGENT_ASSURANCE_SANTE_VIE_ID,
        AGENT_CREDIT_ID,
        AGENT_RH_RECRUTEMENT_ID,
        AGENT_SANTE_RGPD_ID,
        AGENT_SUPPORT_CLIENT_ID,
    ]
    assert support.template_id == "agent-support-client"
    assert support.sector == "customer-support"
    assert support.version == "1.0.0"


def test_other_templates_are_unchanged_by_the_new_one() -> None:
    pins = {
        AGENT_SANTE_RGPD_ID: "f150977f08f9f3c8f4e9a8e88ed86c42e53649c2157aa028896836a7f00a2391",
        AGENT_RH_RECRUTEMENT_ID: "de7e4fd23121d039957fbdb757ca230fa8355ba5024649a6f885868971a1b215",
        AGENT_CREDIT_ID: "3a6d5d5df9ac2a7016a16544c1dd72cf2d6a7bcb6626bb3b82b1a573fda335a4",
        AGENT_ASSURANCE_SANTE_VIE_ID: (
            "6d9bfbb782132caa5ce9eb757dfb552a9a0a30d2db3a36b1f8b800f5a7a57c95"
        ),
    }
    for template_id, digest in pins.items():
        assert get_template(template_id).digest() == digest, template_id


def test_digest_is_pinned(support: MandateTemplate) -> None:
    # Any change to the template content must come with a new version and a new pin.
    assert support.digest() == "3d2d83ff8131a7ec0606ec2a40ec10e31b889ad6a847fff80976c4ffd6ddfbd0"


# --- Perimeter -----------------------------------------------------------------------


def test_exact_lists(support: MandateTemplate) -> None:
    p = support.perimeter
    assert set(p.allowed_actions) == set(ALLOWED)
    assert set(p.forbidden_actions) == set(FORBIDDEN)
    assert p.delegation_allowed is False
    assert p.amount_actions == (GESTURE,)
    assert p.period_max_amount is None
    assert p.risk_classes == ()


def test_ceiling_is_50_eur_per_gesture(support: MandateTemplate) -> None:
    p = support.perimeter
    assert p.canonical()["max_amount"] == "50"
    assert p.currency == "EUR"
    assert p.check_action(GESTURE, _eur("50")) is None
    assert p.check_action(GESTURE, _eur("50.01")) == "amount_above_limit:50 EUR"
    assert p.check_action(GESTURE, {}) == "amount_required"
    assert p.check_action(GESTURE, {"amount": "10", "currency": "USD"}) == "currency_mismatch:EUR"
    assert p.check_action(GESTURE, {"amount": "10"}) == "currency_required"
    assert p.check_action(GESTURE, _eur("-30")) == "amount_invalid"
    assert p.check_action(f"{GESTURE}.bulk", _eur("10")) == f"not_allowed:{GESTURE}.bulk"


def test_a_proposal_that_states_a_larger_amount_is_refused(support: MandateTemplate) -> None:
    # Documented limit: every stated amount is checked against the ceiling.
    p = support.perimeter
    assert p.check_action("commercial_gesture.propose", {}) is None
    assert p.check_action("commercial_gesture.propose", _eur("80")) == "amount_above_limit:50 EUR"


def test_other_allowed_actions_need_no_amount(support: MandateTemplate) -> None:
    for action in ALLOWED:
        if action != GESTURE:
            assert support.perimeter.check_action(action, {}) is None, action


@pytest.mark.parametrize("action", FORBIDDEN)
def test_forbidden_actions_and_their_sub_types(support: MandateTemplate, action: str) -> None:
    p = support.perimeter
    assert p.check_action(action, {}) == f"forbidden:{action}"
    assert p.check_action(f"{action}.batch", {}) == f"forbidden:{action}"


def test_decisions_against_the_customer_are_never_allowed(support: MandateTemplate) -> None:
    p = support.perimeter
    assert "*" not in p.allowed_actions
    assert not any(a.endswith("*") for a in p.allowed_actions)
    for action in (
        "refund.grant",
        "refund",
        "complaint.close",
        "ticket.close",
        "account.suspend",
        "contract.change",
        "customer_data.delete",
        "email.send",
    ):
        assert (p.check_action(action, {}) or "").startswith("not_allowed:"), action


def test_catalog_says_forbidden_for_every_forbidden_action(support: MandateTemplate) -> None:
    for action in FORBIDDEN:
        assert support.actions[action].startswith("Forbidden:"), action
    for action in ALLOWED:
        assert not support.actions[action].startswith("Forbidden:"), action
    assert "comes from an AI" in support.actions["ticket.answer"]


def test_stewardship_is_provisional_with_no_reviewer(support: MandateTemplate) -> None:
    assert support.stewardship is not None
    assert support.stewardship.status == "provisional"
    assert support.stewardship.reviewers == ()
    assert "customer support sector" in support.stewardship.handover


def test_legal_references_exact_and_to_verify(support: MandateTemplate) -> None:
    assert tuple(ref.reference for ref in support.legal_references) == REFERENCES
    assert all(ref.status == "to_verify" for ref in support.legal_references)
    topics = {ref.reference: ref.topic for ref in support.legal_references}
    assert topics[REFERENCES[0]].startswith("Providers design AI systems")
    assert "Applies from 2 August 2026." in topics[REFERENCES[0]]
    assert "free of charge" in topics[REFERENCES[2]]
    assert "contact details of the competent mediator" in topics[REFERENCES[3]]


def test_kwargs_metadata_and_ceiling(support: MandateTemplate) -> None:
    kwargs = support.create_mandate_kwargs()
    assert kwargs["delegation_allowed"] is False
    assert kwargs["max_amount"] == "50"
    assert kwargs["currency"] == "EUR"
    assert kwargs["amount_actions"] == [GESTURE]
    assert "risk_classes" not in kwargs
    assert kwargs["metadata"] == {
        "template_id": "agent-support-client",
        "template_version": "1.0.0",
        "template_digest": support.digest(),
        "template_status": "provisional",
    }
    assert support.create_mandate_kwargs(max_amount="20")["max_amount"] == "20"
    with pytest.raises(ValueError, match="above the template ceiling"):
        support.create_mandate_kwargs(max_amount="50.01")


# --- End to end ----------------------------------------------------------------------


async def test_end_to_end_allowed_actions_get_tokens(support: MandateTemplate) -> None:
    mandate = await _mandate_from(support)
    assert mandate["status"] == "created", mandate
    for action in ALLOWED:
        meta = _eur("30") if action == GESTURE else None
        result = await _token(mandate["mandate_id"], action, meta)
        assert "token" in result, (action, result)


async def test_end_to_end_gesture_above_ceiling_or_without_amount_is_refused(
    support: MandateTemplate,
) -> None:
    mandate = await _mandate_from(support)
    above = await _token(mandate["mandate_id"], GESTURE, _eur("80"))
    assert above.get("denied") is True, above
    assert above["reason"] == "action_out_of_scope"
    assert above["detail"] == "amount_above_limit:50 EUR"
    missing = await _token(mandate["mandate_id"], GESTURE)
    assert missing.get("denied") is True, missing
    assert missing["detail"] == "amount_required"


async def test_end_to_end_cumulative_cap_added_by_the_principal(
    support: MandateTemplate,
) -> None:
    kwargs = support.create_mandate_kwargs()
    kwargs.update(period_max_amount="60", period_days=30)
    mandate = json.loads(
        await create_mandate(
            principal_id=PRINCIPAL,
            agent_id=AGENT,
            scope=support.summary,
            legal_basis_regulation="Delegation of authority",
            legal_basis_article="Section 2",
            duration_hours=support.default_duration_hours,
            **kwargs,
        )
    )
    assert mandate["status"] == "created", mandate
    first = await _token(mandate["mandate_id"], GESTURE, {**_eur("40"), "ref": "a"})
    assert "token" in first, first
    second = await _token(mandate["mandate_id"], GESTURE, {**_eur("40"), "ref": "b"})
    assert second.get("denied") is True, second
    assert second["detail"].startswith("period_amount_above_limit:60 EUR/30d"), second


async def test_end_to_end_lowered_ceiling_holds(support: MandateTemplate) -> None:
    mandate = await _mandate_from(support, max_amount="20")
    assert "token" in await _token(mandate["mandate_id"], GESTURE, _eur("20"))
    refused = await _token(mandate["mandate_id"], GESTURE, _eur("30"))
    assert refused["detail"] == "amount_above_limit:20 EUR"


@pytest.mark.parametrize("action", FORBIDDEN)
async def test_end_to_end_forbidden_actions_get_no_token(
    support: MandateTemplate, action: str
) -> None:
    mandate = await _mandate_from(support)
    result = await _token(mandate["mandate_id"], action)
    assert result.get("denied") is True, result
    assert result["reason"] == "action_out_of_scope"
    assert result["detail"] == f"forbidden:{action}"


async def test_end_to_end_no_sub_agent(support: MandateTemplate) -> None:
    mandate = await _mandate_from(support)
    sub = json.loads(
        await create_mandate(
            principal_id=AGENT,
            agent_id="agent:sub",
            scope="answer tickets",
            legal_basis_regulation="Delegation of authority",
            legal_basis_article="Section 2",
            duration_hours=1,
            parent_mandate_id=mandate["mandate_id"],
            allowed_actions=["ticket.answer"],
        )
    )
    assert sub["code"] == "delegation_not_allowed"


async def test_end_to_end_template_recorded_in_mandate_and_proof(
    support: MandateTemplate, temp_db: Path
) -> None:
    mandate = await _mandate_from(support, metadata={"client_ref": "SC-001"})
    async with aiosqlite.connect(str(temp_db)) as db:
        cursor = await db.execute(
            "SELECT perimeter_json FROM mandates WHERE id = ?", (mandate["mandate_id"],)
        )
        (perimeter_json,) = await cursor.fetchone()
    assert Perimeter.from_json(perimeter_json) == support.perimeter
    proof = json.loads(await get_proof(mandate["mandate_id"]))
    assert proof["mandate"]["metadata"]["template_id"] == "agent-support-client"
    assert proof["mandate"]["metadata"]["template_status"] == "provisional"
    assert proof["mandate"]["metadata"]["client_ref"] == "SC-001"


# --- Documentation -------------------------------------------------------------------


def _doc() -> str:
    return DOC.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_documented_json_is_the_template(support: MandateTemplate) -> None:
    blocks = re.findall(r"```json\n(.*?)\n```", _doc(), re.DOTALL)
    assert blocks, "no json block in the template documentation"
    assert blocks[0] == support.to_json(indent=2)


def test_doc_table_names_every_action(support: MandateTemplate) -> None:
    table = _doc().split("## Ceiling of a commercial gesture")[0]
    for action in (*ALLOWED, *FORBIDDEN):
        assert f"`{action}`" in table, action


def test_doc_says_references_are_to_verify_and_not_compliance() -> None:
    text = " ".join(_doc().replace("\n> ", "\n").split())
    assert "marked `to_verify`" in text
    assert "does not make a customer support process compliant" in text
    assert "`forbidden:<type>`" in text
    assert "50 EUR per gesture by default" in text
    assert "(`amount_above_limit:50 EUR` above it)" in text
    assert "`currency_required` without a currency" in text
    assert "several gestures to the same customer can add up" in text
    assert "kwargs.update(period_max_amount=" in text
    assert "is refused if its token states the amount" in text
    assert "keep refusals and promises out of `ticket.answer`" in text
    assert "There is no cumulative ceiling per period in this template:" in text
    assert "the template does not say that an answer meets it" in text
    assert "does not check which data the agent used" in text


def test_readme_lists_the_template() -> None:
    text = " ".join(README.read_text(encoding="utf-8").split())
    assert "`agent-support-client`, covers an agent answering customers" in text
    assert "Every decision that goes against the customer stays with a human." in text
    assert "AMR does not read the answers: they must not carry a refusal" in text
    assert (
        "sector templates (health, recruitment, credit, life and health insurance, "
        "customer support)" in text
    )
    assert "`docs/templates/agent-support-client.md`" in text
