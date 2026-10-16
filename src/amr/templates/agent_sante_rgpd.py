"""Template ``agent-sante-rgpd``: an AI agent working in a medical practice or facility.

What the agent may do: read the patient record, read and propose or book appointments in
the practice's own schedule, draft letters and patient messages for a human to validate,
and order supplies under a ceiling. What it may never do: prescribe, diagnose, write to or
export the patient record, send a letter or a message to a patient itself, or create a
sub-agent (delegation is off, and ``agent.create`` is forbidden).

The legal references are pointers for the principal, all marked ``to_verify``: they are
not legal advice and have not been reviewed by counsel.
"""

from amr.models.perimeter import Perimeter
from amr.templates.base import LegalReference, MandateTemplate

AGENT_SANTE_RGPD = MandateTemplate(
    template_id="agent-sante-rgpd",
    version="1.0.0",
    title="Healthcare practice assistant agent (GDPR health data)",
    sector="health",
    summary=(
        "Assist a medical practice or facility: read the patient record, handle the "
        "practice schedule, draft letters and patient messages for human validation, "
        "order supplies under a ceiling. Never prescribe, diagnose, change or export the "
        "record, contact a patient directly, or create a sub-agent."
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
            reference="Regulation (EU) 2016/679 (GDPR), Art. 9",
            topic="Processing of health data, a special category of personal data.",
        ),
        LegalReference(
            reference="Regulation (EU) 2024/1689 (AI Act), Art. 14 and Art. 26",
            topic="Human oversight, and the obligations of deployers of AI systems.",
        ),
        LegalReference(
            reference="Code de la santé publique (FR), Art. L1110-4",
            topic="Medical secrecy and sharing of health information.",
        ),
        LegalReference(
            reference="Code de la santé publique (FR), Art. L1111-8",
            topic="Hosting of health data (HDS).",
        ),
    ),
    notes=(
        "Legal references are pointers to check, not legal advice.",
        "The 100 EUR ceiling is a starting value: the principal may set a lower one.",
    ),
)
