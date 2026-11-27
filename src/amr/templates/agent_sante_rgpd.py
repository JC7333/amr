"""Template ``agent-sante-rgpd``: an AI agent working in a medical practice or facility.

What the agent may do: read the patient record, read and propose or book appointments in
the practice's own schedule, draft letters and patient messages for a human to validate,
and order supplies under a ceiling. What it may never do: prescribe, diagnose, write to or
export the patient record, rank patients or their requests by medical urgency (``triage``),
send a letter or a message to a patient itself, or create a sub-agent (delegation is off,
and ``agent.create`` is forbidden).

In a facility, the use of an agent is often decided by a body (an AI or digital strategy
committee) for predefined actions and designated staff. The mandate can record that
decision (``organ_decision``: body, title, date, reference, authorized personnel); the
predefined actions are the closed list of allowed actions below. A practice without such
a body simply leaves it out.

This template is a provisional sector baseline (``stewardship``): published by the AMR
registry until a body of the health sector takes it over, with no practitioner review
recorded yet. Its minimum threshold per risk class: an order of supplies is an
irreversible action, so its token lives at most 30 seconds and the receiver re-checks the
registry before acting (``registry_check``). A mandate may tighten this, never loosen it.

The legal references are pointers for the principal, all marked ``to_verify``: they are
not legal advice and have not been reviewed by counsel. Their wording was checked against
the texts in force on 26 November 2026 (EUR-Lex, Legifrance): Regulation (EU) 2024/1689 as
amended by Regulation (EU) 2026/1744. Within this template the agent is likely not a
high-risk AI system: the template gives it none of the medical purposes of MDR Art. 2(1)
and forbids triage, though the classification depends on the intended purpose its provider
sets. For the practice as deployer, the main AI Act duty that applies now is Art. 4; the
Art. 5 prohibitions also apply, and Art. 50 duties fall mainly on the provider. Art. 14
and Art. 26 apply only if the agent is high-risk.
"""

from amr.models.perimeter import Perimeter, RiskClass
from amr.templates.base import LegalReference, MandateTemplate, Stewardship

AGENT_SANTE_RGPD = MandateTemplate(
    template_id="agent-sante-rgpd",
    version="1.3.1",
    title="Healthcare practice assistant agent (GDPR health data)",
    sector="health",
    summary=(
        "Assist a medical practice or facility: read the patient record, handle the "
        "practice schedule, draft letters and patient messages for human validation, "
        "order supplies under a ceiling. Never prescribe, diagnose, triage by urgency, change "
        "or export the record, contact a patient directly, or create a sub-agent."
    ),
    perimeter=Perimeter(
        allowed_actions=(
            "patient_record.read",
            "appointment.read",
            "appointment.propose",
            "appointment.book",
            "letter.draft",
            "patient_message.draft",
            "supplies.order",
        ),
        forbidden_actions=(
            "prescription",
            "diagnosis",
            "triage",
            "patient_record.write",
            "patient_record.export",
            "patient_record.delete",
            "letter.send",
            "patient_message.send",
            "agent.create",
        ),
        delegation_allowed=False,
        max_amount="100",
        currency="EUR",
        amount_actions=("supplies.order",),
        risk_classes=(
            RiskClass(
                name="irreversible",
                actions=("supplies.order",),
                max_token_seconds=30,
                registry_check=True,
            ),
        ),
    ),
    actions={
        "patient_record.read": "Read the patient record needed for the task at hand.",
        "appointment.read": "Read the practice schedule.",
        "appointment.propose": "Propose an appointment slot, to be confirmed by a human.",
        "appointment.book": "Book a slot in the practice's own schedule.",
        "letter.draft": "Draft a letter (referral, report, administrative) for validation.",
        "patient_message.draft": "Draft a message to a patient, sent only by a human.",
        "supplies.order": "Order supplies, each order carrying amount and currency, "
        "at or below the ceiling.",
        "prescription": "Forbidden: create, renew or change any prescription.",
        "diagnosis": "Forbidden: state or record a diagnosis.",
        "triage": "Forbidden: sort or rank patients or their requests by medical urgency.",
        "patient_record.write": "Forbidden: write to or change the patient record.",
        "patient_record.export": "Forbidden: export or transfer the patient record.",
        "patient_record.delete": "Forbidden: delete anything from the patient record.",
        "letter.send": "Forbidden: send a letter; a human validates and sends it.",
        "patient_message.send": "Forbidden: send a message to a patient without a human.",
        "agent.create": "Forbidden: create a sub-agent (delegation is off as well).",
    },
    default_duration_hours=720,
    legal_references=(
        LegalReference(
            reference="Regulation (EU) 2016/679 (GDPR), Art. 9(1), 9(2)(h) and 9(3)",
            topic="Under 9(2)(h) and 9(3), health data may be processed for care and the "
            "management of health services by or under the responsibility of a professional "
            "bound by secrecy: here, the practitioner.",
        ),
        LegalReference(
            reference="Regulation (EU) 2016/679 (GDPR), Art. 28",
            topic="When the provider that runs the agent processes patient data only for the "
            "practice or facility, it is a processor: a written contract is required.",
        ),
        LegalReference(
            reference="Regulation (EU) 2016/679 (GDPR), Art. 35 and recital 91",
            topic="Recital 91: a practitioner working alone does not process health data on a "
            "large scale, so Art. 35(3)(b) does not apply. Whether an AI agent on health data "
            "still needs an impact assessment under Art. 35(1) and the CNIL list must be "
            "checked.",
        ),
        LegalReference(
            reference="Regulation (EU) 2024/1689 (AI Act), Art. 4, as replaced by "
            "Regulation (EU) 2026/1744",
            topic="AI literacy: every deployer takes measures to support the AI literacy of "
            "its staff; no specific level is required. Applies since 2 February 2025; current "
            "wording since 27 July 2026.",
        ),
        LegalReference(
            reference="Regulation (EU) 2024/1689 (AI Act), Art. 6, Annex I (point 11) and "
            "Annex III (point 5), as amended by Regulation (EU) 2026/1744; "
            "Regulation (EU) 2017/745, Art. 2(1)",
            topic="Check that the agent is not high-risk. The template gives it none of the "
            "medical purposes of MDR Art. 2(1) and forbids triage (Annex III, point 5(d)); the "
            "classification depends on the intended purpose its provider sets.",
        ),
        LegalReference(
            reference="Regulation (EU) 2024/1689 (AI Act), Art. 14 and Art. 26",
            topic="Only if the agent is high-risk: oversight built into the system by its "
            "provider (Art. 14) and the deployer's duties (Art. 26). From 2 December 2027 "
            "(Annex III) or 2 August 2028 (Annex I), Regulation (EU) 2026/1744.",
        ),
        LegalReference(
            reference="Code de la santé publique (FR), Art. L1110-4",
            topic="Medical secrecy binds everyone working with the practice; information is "
            "shared between professionals caring for the patient, only what is strictly "
            "necessary, and outside the care team only with the patient's consent. Version in "
            "force since 4 August 2021.",
        ),
        LegalReference(
            reference="Code de la santé publique (FR), Art. L1111-8",
            topic="Whoever stores health data on behalf of the practice must hold the HDS "
            "certificate (version in force since 1 July 2025). It may concern the platform "
            "that runs the agent; AMR needs no patient data.",
        ),
    ),
    notes=(
        "Legal references are pointers to check, not legal advice.",
        "The 100 EUR ceiling is a starting value: the principal may set a lower one.",
        "The ceiling applies to each order. There is no cumulative ceiling per period in "
        "this template: several orders can add up, so a principal who needs a total cap "
        "adds period_max_amount and period_days to the create_mandate arguments.",
        "appointment.book must not notify the patient: a confirmation sent to the "
        "patient is a patient message, which this template forbids.",
        "The agent names the action type it asks a token for: the system that receives "
        "the token must map each real operation to the right type (a draft that is "
        "actually sent is letter.send or patient_message.send).",
        "Delegation is off for mandates under this one. The agent must not have access to "
        "create_mandate itself, or it could register a new root mandate for a sub-agent.",
        "When a body authorized the agent, record its decision (organ_decision) with the "
        "persons or roles it designates. AMR records what the principal declares: it does "
        "not check that the decision exists or that the people named are who they say.",
        "triage is forbidden as an action type. AMR does not see the order in which the "
        "agent handles requests: the system that receives the tokens must not let the agent "
        "rank patients by urgency through another action (emergency triage is listed as "
        "high-risk in AI Act Annex III, point 5(d)).",
        "Whether a model that only processes a patient record for a moment, without keeping "
        "it, hosts health data under Code de la santé publique L1111-8 has not been checked "
        "(Art. R1111-8-8).",
        "Minimum threshold per risk class: an order of supplies cannot be undone, so its "
        "token lives at most 30 seconds and carries amr_registry_check. A mandate may "
        "shorten the window or widen the class, never lengthen it or drop the check.",
    ),
    organ_decision="optional",
    stewardship=Stewardship(
        status="provisional",
        held_by="AMR registry (mandatia.eu)",
        handover=(
            "Provisional baseline published by the registry until a body of the health "
            "sector takes it over; that body then holds the template and its versions."
        ),
        reviewers=(),
    ),
)
