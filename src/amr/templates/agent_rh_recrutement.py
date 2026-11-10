"""Template ``agent-rh-recrutement``: an AI agent assisting a recruiter.

What the agent may do: read the applications received, draft a job posting, propose a
reasoned shortlist to a human recruiter, propose and book an interview slot in the
company's own calendar, and draft a message to a candidate. What it may never do: decide
on a candidate (reject or select), send a job offer or a rejection, send any message to a
candidate itself, recognize emotions, categorize people from biometric data, infer
sensitive data, export candidate data, or create a sub-agent (delegation is off, and
``agent.create`` is forbidden).

Every decision about a person stays with a human: the agent proposes, it does not decide.
No allowed action is irreversible, so the template sets no risk class; a mandate may add
one (``create_mandate_kwargs(risk_classes=...)``).

This template is a provisional sector baseline (``stewardship``): published by the AMR
registry until a body of the employment sector takes it over, with no practitioner review
recorded yet.

The legal references are pointers for the principal, all marked ``to_verify``: they are
not legal advice and have not been reviewed by counsel.
"""

from amr.models.perimeter import Perimeter
from amr.templates.base import LegalReference, MandateTemplate, Stewardship

AGENT_RH_RECRUTEMENT = MandateTemplate(
    template_id="agent-rh-recrutement",
    version="1.0.0",
    title="Recruitment assistant agent (human decides on every candidate)",
    sector="employment",
    summary=(
        "Assist a recruiter: read the applications received, draft a job posting, propose "
        "a reasoned shortlist to a human recruiter, propose and book interview slots in "
        "the company calendar, draft candidate messages for a human to send. Never reject "
        "or select a candidate, send an offer, a rejection or any message to a candidate, "
        "recognize emotions, categorize people from biometric data, infer sensitive data, "
        "export candidate data, or create a sub-agent."
    ),
    perimeter=Perimeter(
        allowed_actions=(
            "application.read",
            "job_posting.draft",
            "shortlist.propose",
            "interview.propose",
            "interview.book",
            "candidate_message.draft",
        ),
        forbidden_actions=(
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
        ),
        delegation_allowed=False,
    ),
    actions={
        "application.read": "Read the applications received for the position at hand.",
        "job_posting.draft": "Draft a job posting, published only by a human.",
        "shortlist.propose": "Propose a reasoned shortlist to a human recruiter, who "
        "decides.",
        "interview.propose": "Propose an interview slot, to be confirmed by a human.",
        "interview.book": "Book an interview slot in the company's own calendar.",
        "candidate_message.draft": "Draft a message to a candidate, sent only by a human.",
        "candidate.reject": "Forbidden: reject a candidate or close an application.",
        "candidate.select": "Forbidden: select or retain a candidate; a human decides.",
        "offer.send": "Forbidden: send a job offer.",
        "rejection.send": "Forbidden: send a rejection.",
        "candidate_message.send": "Forbidden: send any message to a candidate without a "
        "human.",
        "emotion_recognition": "Forbidden: infer the emotions of a candidate or a worker.",
        "biometric_categorisation": "Forbidden: categorize people from biometric data.",
        "sensitive_data.infer": "Forbidden: infer sensitive data about a person (special "
        "categories of personal data).",
        "candidate_data.export": "Forbidden: export or transfer candidate data.",
        "agent.create": "Forbidden: create a sub-agent (delegation is off as well).",
    },
    default_duration_hours=720,
    legal_references=(
        LegalReference(
            reference="Regulation (EU) 2024/1689 (AI Act), Annex III, point 4(a)",
            topic="AI systems for the recruitment or selection of natural persons "
            "(targeted job ads, analysing and filtering applications, evaluating "
            "candidates), listed as high-risk.",
        ),
        LegalReference(
            reference="Regulation (EU) 2024/1689 (AI Act), Art. 26, including Art. 26(7)",
            topic="Obligations of deployers of high-risk AI systems; employers inform "
            "workers' representatives and the affected workers before use at the "
            "workplace.",
        ),
        LegalReference(
            reference="Regulation (EU) 2024/1689 (AI Act), Art. 5(1)(f)",
            topic="Prohibition of AI systems that infer emotions in the workplace, except "
            "for medical or safety reasons.",
        ),
        LegalReference(
            reference="Regulation (EU) 2016/679 (GDPR), Art. 22",
            topic="Decisions based solely on automated processing, including profiling.",
        ),
        LegalReference(
            reference="Code du travail (FR), Art. L1132-1",
            topic="Principle of non-discrimination, including in recruitment procedures.",
        ),
        LegalReference(
            reference="Code du travail (FR), Art. L1221-8",
            topic="Candidates informed beforehand of the recruitment methods and "
            "techniques used; methods relevant to the aim; results confidential.",
        ),
        LegalReference(
            reference="Code du travail (FR), Art. L1221-9",
            topic="No personal information on a candidate collected by a device not "
            "brought to the candidate's knowledge beforehand.",
        ),
    ),
    notes=(
        "Legal references are pointers to check, not legal advice.",
        "Every decision about a candidate (reject, select, offer, rejection) stays with a "
        "human: the agent proposes a shortlist, it does not decide.",
        "interview.book must not notify the candidate: a confirmation sent to the "
        "candidate is a candidate message, which this template forbids.",
        "The agent names the action type it asks a token for: the system that receives "
        "the token must map each real operation to the right type (a draft that is "
        "actually sent is candidate_message.send, offer.send or rejection.send).",
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
            "employment sector takes it over; that body then holds the template and its "
            "versions."
        ),
        reviewers=(),
    ),
)
