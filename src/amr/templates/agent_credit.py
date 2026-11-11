"""Template ``agent-credit``: an AI agent assisting a credit analyst.

What the agent may do: read a credit application and the documents provided, draft a
creditworthiness analysis, propose a reasoned decision to a human analyst, and draft a
message to the applicant. What it may never do: grant or refuse a credit, set the final
rate or amount, send any message to the applicant itself, execute a payment, export the
credit file, or create a sub-agent (delegation is off, and ``agent.create`` is
forbidden).

Every decision on a credit (grant, refuse, final rate, amount or duration) stays with a human: the
agent proposes. No allowed action is irreversible, so the template sets no risk class; a
mandate may add one (``create_mandate_kwargs(risk_classes=...)``). Fraud detection is not
part of this template: the AI Act excludes it from the creditworthiness point of
Annex III.

This template is a provisional sector baseline (``stewardship``): published by the AMR
registry until a body of the credit sector takes it over, with no practitioner review
recorded yet.

The legal references are pointers for the principal, all marked ``to_verify``: they are
not legal advice and have not been reviewed by counsel.
"""

from amr.models.perimeter import Perimeter
from amr.templates.base import LegalReference, MandateTemplate, Stewardship

AGENT_CREDIT = MandateTemplate(
    template_id="agent-credit",
    version="1.0.0",
    title="Credit analysis assistant agent (human decides on every credit)",
    sector="credit",
    summary=(
        "Assist a credit analyst: read the credit application and the documents provided, "
        "draft a creditworthiness analysis, propose a reasoned decision to a human "
        "analyst, draft messages to the applicant for a human to send. Never grant or "
        "refuse a credit, set the final rate, amount or duration, send any message to the "
        "applicant, execute a payment, export the credit file, or create a sub-agent."
    ),
    perimeter=Perimeter(
        allowed_actions=(
            "credit_application.read",
            "creditworthiness_analysis.draft",
            "credit_decision.propose",
            "applicant_message.draft",
        ),
        forbidden_actions=(
            "credit.grant",
            "credit.refuse",
            "credit_terms.set",
            "applicant_message.send",
            "payment.execute",
            "credit_file.export",
            "agent.create",
        ),
        delegation_allowed=False,
    ),
    actions={
        "credit_application.read": "Read the credit application and the documents the "
        "applicant provided.",
        "creditworthiness_analysis.draft": "Draft a creditworthiness analysis for a human "
        "analyst.",
        "credit_decision.propose": "Propose a reasoned decision to a human analyst, who "
        "decides.",
        "applicant_message.draft": "Draft a message to the applicant, sent only by a "
        "human.",
        "credit.grant": "Forbidden: grant a credit; a human decides.",
        "credit.refuse": "Forbidden: refuse a credit or close an application; a human "
        "decides.",
        "credit_terms.set": "Forbidden: set the final rate, amount or duration of a "
        "credit.",
        "applicant_message.send": "Forbidden: send any message to the applicant without "
        "a human.",
        "payment.execute": "Forbidden: execute a payment or release funds.",
        "credit_file.export": "Forbidden: export or transfer the credit file.",
        "agent.create": "Forbidden: create a sub-agent (delegation is off as well).",
    },
    default_duration_hours=720,
    legal_references=(
        LegalReference(
            reference="Regulation (EU) 2024/1689 (AI Act), Annex III, point 5(b)",
            topic="AI systems to evaluate the creditworthiness of natural persons or "
            "establish their credit score, listed as high-risk, except systems used to "
            "detect financial fraud.",
        ),
        LegalReference(
            reference="Regulation (EU) 2024/1689 (AI Act), Art. 26",
            topic="Obligations of deployers of high-risk AI systems.",
        ),
        LegalReference(
            reference="Regulation (EU) 2024/1689 (AI Act), Art. 27",
            topic="Fundamental rights impact assessment, to be performed before use by "
            "deployers of the high-risk systems of Annex III, point 5(b).",
        ),
        LegalReference(
            reference="Regulation (EU) 2024/1689 (AI Act), Art. 86",
            topic="Right of a person affected by a decision taken on the basis of a "
            "high-risk AI system's output to obtain explanations from the deployer.",
        ),
        LegalReference(
            reference="Regulation (EU) 2016/679 (GDPR), Art. 22",
            topic="Decisions based solely on automated processing, including profiling.",
        ),
        LegalReference(
            reference="Directive (EU) 2023/2225 (consumer credit), Art. 18, including "
            "Art. 18(8)",
            topic="Creditworthiness assessment; where it involves automated processing, "
            "the consumer's right to human intervention, an explanation and a review. "
            "Applies from 20 November 2026 (Art. 48(1)), through national transposing "
            "measures.",
        ),
        LegalReference(
            reference="Code de la consommation (FR), Art. L312-16",
            topic="Creditworthiness assessment by the lender before a consumer credit "
            "contract; check the version in force on the date of use.",
        ),
    ),
    notes=(
        "Legal references are pointers to check, not legal advice.",
        "Every decision on a credit (grant, refuse, final rate, amount or duration) stays with a "
        "human: the agent proposes a decision, it does not decide.",
        "Fraud detection is not part of this template.",
        "The references point to consumer credit to natural persons; mortgage credit "
        "and credit to businesses have other texts, not listed here.",
        "A human review that only signs off the agent's proposal may not count as a "
        "human decision: the reviewer must be able to depart from it.",
        "The agent names the action type it asks a token for: the system that receives "
        "the token must map each real operation to the right type (a draft that is "
        "actually sent is applicant_message.send; an approval recorded in the credit "
        "system is credit.grant).",
        "No allowed action is irreversible, so the template sets no risk class; a "
        "mandate may add one.",
        "Delegation is off for mandates under this one. The agent must not have access to "
        "create_mandate itself, or it could register a new root mandate for a sub-agent.",
        "When a body authorized the agent, record its decision (organ_decision) with the "
        "persons or roles it designates. AMR records what the principal declares: it does "
        "not check that the decision exists or that the people named are who they say.",
    ),
    organ_decision="optional",
    stewardship=Stewardship(
        status="provisional",
        held_by="AMR registry (mandatia.eu)",
        handover=(
            "Provisional baseline published by the registry until a body of the credit "
            "sector takes it over; that body then holds the template and its versions."
        ),
        reviewers=(),
    ),
)
