"""Template ``agent-assurance-sante-vie``: an AI agent assisting a life or health underwriter.

What the agent may do: read an underwriting file, draft a risk assessment, propose a
reasoned premium to a human underwriter, draft the contract documents, and draft a
message to the insured person. What it may never do: accept or refuse an application,
set the final premium, send any message to the insured person itself, use the result of
a genetic test, export health data, or create a sub-agent (delegation is off, and
``agent.create`` is forbidden).

Every decision on an application (accept, refuse, final premium) stays with a human: the
agent proposes. No allowed action is irreversible, so the template sets no risk class; a
mandate may add one (``create_mandate_kwargs(risk_classes=...)``). Claims handling is not
part of this template.

This template is a provisional sector baseline (``stewardship``): published by the AMR
registry until a body of the insurance sector takes it over, with no practitioner review
recorded yet.

The legal references are pointers for the principal, all marked ``to_verify``: they are
not legal advice and have not been reviewed by counsel.
"""

from amr.models.perimeter import Perimeter
from amr.templates.base import LegalReference, MandateTemplate, Stewardship

AGENT_ASSURANCE_SANTE_VIE = MandateTemplate(
    template_id="agent-assurance-sante-vie",
    version="1.0.0",
    title="Life and health underwriting assistant agent (human decides on every application)",
    sector="insurance",
    summary=(
        "Assist a life or health insurance underwriter: read the underwriting file, draft "
        "a risk assessment, propose a reasoned premium to a human underwriter, draft the "
        "contract documents and messages to the insured person for a human to send. Never "
        "accept or refuse an application, set the final premium, send any message to the "
        "insured person, use the result of a genetic test, export health data, or create "
        "a sub-agent."
    ),
    perimeter=Perimeter(
        allowed_actions=(
            "underwriting_file.read",
            "risk_assessment.draft",
            "premium.propose",
            "contract_documents.draft",
            "insured_message.draft",
        ),
        forbidden_actions=(
            "application.accept",
            "application.refuse",
            "premium.set",
            "insured_message.send",
            "genetic_test_result.use",
            "health_data.export",
            "agent.create",
        ),
        delegation_allowed=False,
    ),
    actions={
        "underwriting_file.read": "Read the underwriting file and the documents the "
        "applicant provided.",
        "risk_assessment.draft": "Draft a risk assessment for a human underwriter.",
        "premium.propose": "Propose a reasoned premium to a human underwriter, who "
        "decides.",
        "contract_documents.draft": "Draft the contract documents for a human to review.",
        "insured_message.draft": "Draft a message to the insured person, sent only by a "
        "human.",
        "application.accept": "Forbidden: accept an application; a human decides.",
        "application.refuse": "Forbidden: refuse or postpone an application, or add an "
        "exclusion; a human decides.",
        "premium.set": "Forbidden: set the final premium, including a surcharge.",
        "insured_message.send": "Forbidden: send any message to the insured person "
        "without a human.",
        "genetic_test_result.use": "Forbidden: ask for, read or use the result of a "
        "genetic test.",
        "health_data.export": "Forbidden: export or transfer health data.",
        "agent.create": "Forbidden: create a sub-agent (delegation is off as well).",
    },
    default_duration_hours=720,
    legal_references=(
        LegalReference(
            reference="Regulation (EU) 2024/1689 (AI Act), Annex III, point 5(c)",
            topic="AI systems for risk assessment and pricing in relation to natural "
            "persons in the case of life and health insurance, listed as high-risk.",
        ),
        LegalReference(
            reference="Regulation (EU) 2024/1689 (AI Act), Art. 26",
            topic="Obligations of deployers of high-risk AI systems.",
        ),
        LegalReference(
            reference="Regulation (EU) 2024/1689 (AI Act), Art. 27",
            topic="Fundamental rights impact assessment, to be performed before use by "
            "deployers of the high-risk systems of Annex III, point 5(c).",
        ),
        LegalReference(
            reference="Regulation (EU) 2024/1689 (AI Act), Art. 86",
            topic="Right of a person affected by a decision taken on the basis of a "
            "high-risk AI system's output to obtain explanations from the deployer.",
        ),
        LegalReference(
            reference="Regulation (EU) 2016/679 (GDPR), Art. 9",
            topic="Processing of special categories of personal data, including health "
            "and genetic data: prohibited unless an exception of Art. 9(2) applies.",
        ),
        LegalReference(
            reference="Regulation (EU) 2016/679 (GDPR), Art. 22",
            topic="Decisions based solely on automated processing, including profiling.",
        ),
        LegalReference(
            reference="Code de la santé publique (FR), Art. L1141-1",
            topic="Insurers covering invalidity or death may not take the results of a "
            "genetic test into account, ask about such tests or require one.",
        ),
        LegalReference(
            reference="Code de la santé publique (FR), Art. L1141-5",
            topic="Insurance covering a loan under the AERAS convention (Art. L1141-2): delay "
            "after the end of treatment for cancer or hepatitis C beyond which no medical "
            "information on it may be collected.",
        ),
        LegalReference(
            reference="Code des assurances (FR), Art. L113-2-1",
            topic="Borrower insurance for home loans: no health information or medical "
            "examination may be asked within the insured amount and age limits set by the "
            "article.",
        ),
        LegalReference(
            reference="Code de la mutualité (FR), Art. L112-1",
            topic="Mutual insurers: for optional health cost cover, no collection of "
            "medical information and no contribution based on health status; check the "
            "version in force on the date of use.",
        ),
    ),
    notes=(
        "Legal references are pointers to check, not legal advice.",
        "Every decision on an application (accept, refuse, final premium) stays with a "
        "human: the agent proposes a premium, it does not decide.",
        "Claims handling is not part of this template.",
        "The rules differ between insurers (Code des assurances), mutual insurers (Code "
        "de la mutualité) and provident institutions (Code de la sécurité sociale): the "
        "principal checks the ones that apply to it.",
        "A human review that only signs off the agent's proposal may not count as a "
        "human decision: the reviewer must be able to depart from it.",
        "The agent names the action type it asks a token for: the system that receives "
        "the token must map each real operation to the right type (a draft that is "
        "actually sent is insured_message.send; a premium or a surcharge recorded in the "
        "policy system is premium.set; an exclusion or a postponement is "
        "application.refuse).",
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
            "Provisional baseline published by the registry until a body of the "
            "insurance sector takes it over; that body then holds the template and its "
            "versions."
        ),
        reviewers=(),
    ),
)
