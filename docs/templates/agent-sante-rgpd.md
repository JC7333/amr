# Template `agent-sante-rgpd`: healthcare practice assistant

A ready-made, machine-readable perimeter for an AI agent working in a medical practice
or a health facility. It fills in the perimeter arguments of `create_mandate`; the token
issuer then enforces it like any other structured perimeter.

| The agent may | The agent may never |
|---|---|
| read the patient record (`patient_record.read`) | prescribe (`prescription`, and every sub-type) |
| read, propose and book appointments in the practice schedule | diagnose (`diagnosis`) |
| draft letters (`letter.draft`) | write to, export or delete the record |
| draft patient messages (`patient_message.draft`) | send a letter or a patient message itself |
| order supplies, 100 EUR per order at most (`supplies.order`) | create a sub-agent (`agent.create`; delegation is off) |

Anything not listed on the left is refused (`not_allowed`). The principal may set a
lower ceiling than 100 EUR, never a higher one. The mandate records the template it was
built from in its metadata (`template_id`, `template_version`, `template_digest`), so the
Proof Pack shows which version of the template governed the agent.

> **Legal references are pointers, marked `to_verify`.** They have not been reviewed
> by counsel and are not legal advice.

## Use

```python
from amr.templates import get_template
from amr.tools.create_mandate import create_mandate

template = get_template("agent-sante-rgpd")
await create_mandate(
    principal_id="org:cabinet-medical",
    agent_id="agent:assistant-cabinet",
    scope=template.summary,
    legal_basis_regulation="Mandat de gestion",
    legal_basis_article="Art. 1984 Code civil",
    duration_hours=template.default_duration_hours,
    **template.create_mandate_kwargs(max_amount="50"),  # optional lower ceiling
)
```

End to end, with that mandate:

```text
issue_action_token(..., action_type="patient_record.read")       -> token
issue_action_token(..., action_type="supplies.order",
                   action_metadata_json='{"amount": "35.90", "currency": "EUR"}') -> token
issue_action_token(..., action_type="prescription.create")
  -> {"denied": true, "reason": "action_out_of_scope", "detail": "forbidden:prescription"}
issue_action_token(..., action_type="patient_message.send")
  -> {"denied": true, "reason": "action_out_of_scope", "detail": "forbidden:patient_message.send"}
create_mandate(principal_id="agent:assistant-cabinet", parent_mandate_id=<mandate>, ...)
  -> {"code": "delegation_not_allowed", ...}
```

These calls are the end-to-end tests in `tests/test_templates.py`.

## Machine-readable template

The JSON below is `template.to_json(indent=2)`; a test checks that it matches the code.
`template.digest()` is the SHA-256 of its compact form.

```json
{
  "actions": {
    "agent.create": "Forbidden: create a sub-agent (delegation is off as well).",
    "appointment.book": "Book a slot in the practice's own schedule.",
    "appointment.propose": "Propose an appointment slot, to be confirmed by a human.",
    "appointment.read": "Read the practice schedule.",
    "diagnosis": "Forbidden: state or record a diagnosis.",
    "letter.draft": "Draft a letter (referral, report, administrative) for validation.",
    "letter.send": "Forbidden: send a letter; a human validates and sends it.",
    "patient_message.draft": "Draft a message to a patient, sent only by a human.",
    "patient_message.send": "Forbidden: send a message to a patient without a human.",
    "patient_record.delete": "Forbidden: delete anything from the patient record.",
    "patient_record.export": "Forbidden: export or transfer the patient record.",
    "patient_record.read": "Read the patient record needed for the task at hand.",
    "patient_record.write": "Forbidden: write to or change the patient record.",
    "prescription": "Forbidden: create, renew or change any prescription.",
    "supplies.order": "Order supplies, each order carrying amount and currency, at or below the ceiling."
  },
  "default_duration_hours": 720.0,
  "legal_references": [
    {
      "reference": "Regulation (EU) 2016/679 (GDPR), Art. 9",
      "status": "to_verify",
      "topic": "Processing of health data, a special category of personal data."
    },
    {
      "reference": "Regulation (EU) 2024/1689 (AI Act), Art. 14 and Art. 26",
      "status": "to_verify",
      "topic": "Human oversight, and the obligations of deployers of AI systems."
    },
    {
      "reference": "Code de la santé publique (FR), Art. L1110-4",
      "status": "to_verify",
      "topic": "Medical secrecy and sharing of health information."
    },
    {
      "reference": "Code de la santé publique (FR), Art. L1111-8",
      "status": "to_verify",
      "topic": "Hosting of health data (HDS)."
    }
  ],
  "notes": [
    "Legal references are pointers to check, not legal advice.",
    "The 100 EUR ceiling is a starting value: the principal may set a lower one."
  ],
  "perimeter": {
    "allowed_actions": [
      "appointment.book",
      "appointment.propose",
      "appointment.read",
      "letter.draft",
      "patient_message.draft",
      "patient_record.read",
      "supplies.order"
    ],
    "amount_actions": [
      "supplies.order"
    ],
    "currency": "EUR",
    "delegation_allowed": false,
    "forbidden_actions": [
      "agent.create",
      "diagnosis",
      "letter.send",
      "patient_message.send",
      "patient_record.delete",
      "patient_record.export",
      "patient_record.write",
      "prescription"
    ],
    "max_amount": "100"
  },
  "sector": "health",
  "summary": "Assist a medical practice or facility: read the patient record, handle the practice schedule, draft letters and patient messages for human validation, order supplies under a ceiling. Never prescribe, diagnose, change or export the record, contact a patient directly, or create a sub-agent.",
  "template_id": "agent-sante-rgpd",
  "title": "Healthcare practice assistant agent (GDPR health data)",
  "version": "1.0.0"
}
```
