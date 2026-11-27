# Template `agent-sante-rgpd`: healthcare practice assistant

A ready-made, machine-readable perimeter for an AI agent working in a medical practice
or a health facility. It fills in the perimeter arguments of `create_mandate`; the token
issuer then enforces it like any other structured perimeter.

| The agent may | The agent may never |
|---|---|
| read the patient record (`patient_record.read`) | prescribe (`prescription`, and every sub-type) |
| read, propose and book appointments in the practice schedule | diagnose (`diagnosis`) or rank patients by urgency (`triage`) |
| draft letters (`letter.draft`) | write to, export or delete the record |
| draft patient messages (`patient_message.draft`) | send a letter or a patient message itself |
| order supplies, 100 EUR per order at most (`supplies.order`) | create a sub-agent (`agent.create`; delegation is off) |

Anything not listed on the left is refused (`not_allowed`). The principal may set a
lower ceiling than 100 EUR, never a higher one. The mandate records the template it was
built from in its metadata (`template_id`, `template_version`, `template_digest`), shown
in the Proof Pack. That metadata is a label: like other mandate metadata (except
`organ_decision`, below) it is not sealed into the chain hash. What is sealed, and enforced, is the perimeter itself.

## Provisional baseline and minimum thresholds

This template is a **provisional** sector baseline. The code records who holds it and
whether the sector has taken it over (`stewardship` in the JSON below):

- status: `provisional`, held by the AMR registry (mandatia.eu) until a body of the
  health sector takes it over;
- practitioner reviewers: none recorded. The list stays empty until a real review is
  recorded; no name is filled in for one.

The stewardship block is part of the template's canonical form, so it is covered by
`template_digest`, and `create_mandate_kwargs()` copies the status into the mandate
metadata as `template_status`. Like the other `template_*` keys, it is a label, not
sealed into the chain hash.

The template sets a minimum threshold per risk class, with the risk-class mechanism the
code already has (`risk_classes` of the perimeter, sealed in the mandate):

| Class | Actions | Token lifetime at most | Registry re-check |
|---|---|---|---|
| `irreversible` | `supplies.order` | 30 seconds | yes (`amr_registry_check`, see `check_action_token`) |

A mandate built from the template may tighten a threshold, never loosen it:

```python
template.create_mandate_kwargs(risk_classes=[
    # same class, shorter window: accepted
    {"name": "irreversible", "actions": ["supplies.order"], "max_token_seconds": 10,
     "registry_check": True},
    # new class: added
    {"name": "booking", "actions": ["appointment.book"], "max_token_seconds": 60},
])
```

A class with the name of a template class that allows a longer lifetime, leaves out an
action the template class reaches, or drops `registry_check` is refused with a
`ValueError` that says which threshold would be loosened. Template classes that are not
named are kept as they are. This check is in `create_mandate_kwargs`: a principal who
calls `create_mandate` directly, without the template, is not bound by it, and the
`template_*` metadata is then only what the caller declares.

## Decision of a body (organ decision)

In a facility, an agent is often authorized by a body (an AI or digital strategy
committee) for predefined actions and designated staff. The mandate can record that
decision, so that whoever receives the agent sees who decided, when, and for whom:

```python
from amr.models.organ_decision import OrganDecision

decision = OrganDecision(
    body="Digital strategy committee",
    title="Use of the scheduling assistant in the outpatient department",
    decided_on="2026-10-01",
    reference="CSN-2026-14",  # optional
    authorized_personnel=("Head of outpatient department", "Care coordinator"),
)
template.create_mandate_kwargs(organ_decision=decision)
```

The decision goes in the mandate metadata under the reserved key `organ_decision`
(compact canonical JSON). `create_mandate` checks its form (date `YYYY-MM-DD`, not
after the registry's UTC date; at least one designated person or role) and seals it into
the chain hash; a principal signature covers it, since it signs the metadata.
`verify_mandate` and `get_proof` return it as `organ_decision`. The predefined actions
are the allowed actions: `create_mandate` accepts a decision only with a closed list (no
`*` pattern), and anything else is refused at token issuance. A decision is recorded on
a root mandate only (`organ_decision_on_sub_mandate` otherwise). A practice without such
a body leaves the decision out; the mandate and its hash are then unchanged.

## Limits

- An order token lives at most 30 seconds and carries `amr_registry_check`: the system
  that receives the order must call `check_action_token` before acting.
- The ceiling applies to each order. There is no cumulative ceiling per period in this
  template: several orders can add up. A principal who needs a total cap adds
  `period_max_amount` and `period_days` to the arguments before calling `create_mandate`
  (`kwargs.update(period_max_amount="300", period_days=30)`); the token issuer then sums
  the order tokens issued in the window and refuses one that would exceed it.
- `appointment.book` must not notify the patient: a confirmation sent to the patient is
  a patient message, which this template forbids.
- The agent names the action type it asks a token for. The system that receives the
  token must map each real operation to the right type (a draft that is actually sent
  is `letter.send` or `patient_message.send`).
- Delegation is off for mandates under this one. The agent must not have access to
  `create_mandate` itself, or it could register a new root mandate for a sub-agent
  (README, deployment rule).
- AMR records the organ decision as the principal declares it: it does not check that
  the decision exists, nor the identity of the persons it designates.
- `verify_mandate` and `get_proof` read the decision of the mandate asked about: for a
  sub-mandate under a mandate that records one, they return `null` (look at the parent).
- They do not recompute the mandate hash: a mandate written before this version with a
  free metadata key `organ_decision` in exactly the canonical form would be shown as a
  decision without being sealed.
- `prepare_mandate_signature` does not check the decision's form: a malformed one is
  refused by `create_mandate`, after the principal has signed.
- `triage` is forbidden as an action type. AMR does not see the order in which the agent
  handles requests: the system that receives the tokens must not let the agent rank
  patients by urgency through another action. Emergency triage is listed as high-risk in
  AI Act Annex III, point 5(d).
- Templates are a Python API for now: no MCP tool lists them yet.

> **Legal references are pointers, marked `to_verify`.** They have not been reviewed
> by counsel and are not legal advice.

## Legal references and their sources

Checked against the texts in force on 26 November 2026. Within this template the agent is
likely not a high-risk AI system: the template gives it none of the medical purposes of
MDR Art. 2(1) and forbids triage, though the classification depends on the intended
purpose its provider sets. For the practice as deployer, the main AI Act duty that applies
now is Art. 4; the Art. 5 prohibitions also apply, and Art. 50 duties fall mainly on the
provider. Art. 14 and Art. 26 apply only if the agent is high-risk.

| Reference | What it says, for this agent | Source |
|---|---|---|
| GDPR Art. 9(1), 9(2)(h), 9(3) | Health data may be processed for care and the management of health services by or under the responsibility of a professional bound by secrecy: here, the practitioner. | [EUR-Lex, CELEX 32016R0679](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R0679) |
| GDPR Art. 28 | When the provider that runs the agent processes patient data only for the practice or facility, it is a processor: a written contract is required. | [EUR-Lex, CELEX 32016R0679](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R0679) |
| GDPR Art. 35 and recital 91 | A practitioner working alone does not process health data on a large scale (recital 91), so Art. 35(3)(b) does not apply. Whether an AI agent on health data still needs an impact assessment under Art. 35(1) and the CNIL list must be checked. | [EUR-Lex, CELEX 32016R0679](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R0679) |
| AI Act Art. 4 | Measures to support the AI literacy of staff; no specific level is required. Applies since 2 February 2025 (Art. 113, point (a)); wording replaced by Regulation (EU) 2026/1744, in force since 27 July 2026. | [EUR-Lex, CELEX 32024R1689](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689), [CELEX 32026R1744](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32026R1744) |
| AI Act Art. 6, Annex I (point 11), Annex III (point 5), as amended; MDR Art. 2(1) | How to check the agent is not high-risk. Software is a medical device only with a medical purpose set by its provider; Art. 6(1a), added in 2026, says tools used only for service efficiency, automation or convenience are not safety components; Annex III, point 5(d) lists emergency triage. | [EUR-Lex, consolidated text of 27 July 2026](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:02024R1689-20260727), [CELEX 32017R0745](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32017R0745) |
| AI Act Art. 14 and Art. 26 | Only if high-risk: oversight designed in by the provider (Art. 14), deployer duties (Art. 26). From 2 December 2027 (Annex III) or 2 August 2028 (Annex I), Art. 113 as amended by Regulation (EU) 2026/1744. Neither article was amended. | [EUR-Lex, consolidated text of 27 July 2026](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:02024R1689-20260727) |
| Code de la santé publique, L1110-4 | Medical secrecy binds everyone working with the practice; sharing between professionals caring for the patient, only what is strictly necessary, and outside the care team only with the patient's consent. Version in force since 4 August 2021. | [Legifrance](https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000043895798) |
| Code de la santé publique, L1111-8 | Storing health data on behalf of the practice requires the HDS certificate (version in force since 1 July 2025, law n° 2024-449). It may concern the platform that runs the agent; AMR needs no patient data. | [Legifrance](https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000049577902) |

Open point: whether a model that only processes a patient record for a moment, without
keeping it, "hosts" health data under L1111-8 has not been checked (Art. R1111-8-8).

## Use

```python
from amr.templates import get_template
from amr.tools.create_mandate import create_mandate

template = get_template("agent-sante-rgpd")
await create_mandate(
    principal_id="org:cabinet-medical",
    agent_id="agent:assistant-cabinet",
    scope=template.summary,
    legal_basis_regulation="Delegation of authority",
    legal_basis_article="Section 2",
    duration_hours=template.default_duration_hours,
    **template.create_mandate_kwargs(
        max_amount="50",  # optional lower ceiling
        metadata={"client_ref": "CAB-001"},  # optional own annotations
    ),
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
    "supplies.order": "Order supplies, each order carrying amount and currency, at or below the ceiling.",
    "triage": "Forbidden: sort or rank patients or their requests by medical urgency."
  },
  "default_duration_hours": 720.0,
  "legal_references": [
    {
      "reference": "Regulation (EU) 2016/679 (GDPR), Art. 9(1), 9(2)(h) and 9(3)",
      "status": "to_verify",
      "topic": "Under 9(2)(h) and 9(3), health data may be processed for care and the management of health services by or under the responsibility of a professional bound by secrecy: here, the practitioner."
    },
    {
      "reference": "Regulation (EU) 2016/679 (GDPR), Art. 28",
      "status": "to_verify",
      "topic": "When the provider that runs the agent processes patient data only for the practice or facility, it is a processor: a written contract is required."
    },
    {
      "reference": "Regulation (EU) 2016/679 (GDPR), Art. 35 and recital 91",
      "status": "to_verify",
      "topic": "Recital 91: a practitioner working alone does not process health data on a large scale, so Art. 35(3)(b) does not apply. Whether an AI agent on health data still needs an impact assessment under Art. 35(1) and the CNIL list must be checked."
    },
    {
      "reference": "Regulation (EU) 2024/1689 (AI Act), Art. 4, as replaced by Regulation (EU) 2026/1744",
      "status": "to_verify",
      "topic": "AI literacy: every deployer takes measures to support the AI literacy of its staff; no specific level is required. Applies since 2 February 2025; current wording since 27 July 2026."
    },
    {
      "reference": "Regulation (EU) 2024/1689 (AI Act), Art. 6, Annex I (point 11) and Annex III (point 5), as amended by Regulation (EU) 2026/1744; Regulation (EU) 2017/745, Art. 2(1)",
      "status": "to_verify",
      "topic": "Check that the agent is not high-risk. The template gives it none of the medical purposes of MDR Art. 2(1) and forbids triage (Annex III, point 5(d)); the classification depends on the intended purpose its provider sets."
    },
    {
      "reference": "Regulation (EU) 2024/1689 (AI Act), Art. 14 and Art. 26",
      "status": "to_verify",
      "topic": "Only if the agent is high-risk: oversight built into the system by its provider (Art. 14) and the deployer's duties (Art. 26). From 2 December 2027 (Annex III) or 2 August 2028 (Annex I), Regulation (EU) 2026/1744."
    },
    {
      "reference": "Code de la santé publique (FR), Art. L1110-4",
      "status": "to_verify",
      "topic": "Medical secrecy binds everyone working with the practice; information is shared between professionals caring for the patient, only what is strictly necessary, and outside the care team only with the patient's consent. Version in force since 4 August 2021."
    },
    {
      "reference": "Code de la santé publique (FR), Art. L1111-8",
      "status": "to_verify",
      "topic": "Whoever stores health data on behalf of the practice must hold the HDS certificate (version in force since 1 July 2025). It may concern the platform that runs the agent; AMR needs no patient data."
    }
  ],
  "notes": [
    "Legal references are pointers to check, not legal advice.",
    "The 100 EUR ceiling is a starting value: the principal may set a lower one.",
    "The ceiling applies to each order. There is no cumulative ceiling per period in this template: several orders can add up, so a principal who needs a total cap adds period_max_amount and period_days to the create_mandate arguments.",
    "appointment.book must not notify the patient: a confirmation sent to the patient is a patient message, which this template forbids.",
    "The agent names the action type it asks a token for: the system that receives the token must map each real operation to the right type (a draft that is actually sent is letter.send or patient_message.send).",
    "Delegation is off for mandates under this one. The agent must not have access to create_mandate itself, or it could register a new root mandate for a sub-agent.",
    "When a body authorized the agent, record its decision (organ_decision) with the persons or roles it designates. AMR records what the principal declares: it does not check that the decision exists or that the people named are who they say.",
    "triage is forbidden as an action type. AMR does not see the order in which the agent handles requests: the system that receives the tokens must not let the agent rank patients by urgency through another action (emergency triage is listed as high-risk in AI Act Annex III, point 5(d)).",
    "Whether a model that only processes a patient record for a moment, without keeping it, hosts health data under Code de la santé publique L1111-8 has not been checked (Art. R1111-8-8).",
    "Minimum threshold per risk class: an order of supplies cannot be undone, so its token lives at most 30 seconds and carries amr_registry_check. A mandate may shorten the window or widen the class, never lengthen it or drop the check."
  ],
  "organ_decision": "optional",
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
      "prescription",
      "triage"
    ],
    "max_amount": "100",
    "risk_classes": [
      {
        "actions": [
          "supplies.order"
        ],
        "max_token_seconds": 30,
        "name": "irreversible",
        "registry_check": true
      }
    ]
  },
  "sector": "health",
  "stewardship": {
    "handover": "Provisional baseline published by the registry until a body of the health sector takes it over; that body then holds the template and its versions.",
    "held_by": "AMR registry (mandatia.eu)",
    "reviewers": [],
    "status": "provisional"
  },
  "summary": "Assist a medical practice or facility: read the patient record, handle the practice schedule, draft letters and patient messages for human validation, order supplies under a ceiling. Never prescribe, diagnose, triage by urgency, change or export the record, contact a patient directly, or create a sub-agent.",
  "template_id": "agent-sante-rgpd",
  "title": "Healthcare practice assistant agent (GDPR health data)",
  "version": "1.3.1"
}
```
