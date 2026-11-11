# Template `agent-credit`: credit analysis assistant

A ready-made, machine-readable perimeter for an AI agent that assists a credit analyst.
It fills in the perimeter arguments of `create_mandate`; the token issuer then enforces
it like any other structured perimeter.

| The agent may | The agent may never |
|---|---|
| read the credit application and the documents provided (`credit_application.read`) | grant or refuse a credit (`credit.grant`, `credit.refuse`) |
| draft a creditworthiness analysis (`creditworthiness_analysis.draft`) | set the final rate, amount or duration (`credit_terms.set`) |
| propose a reasoned decision to a human analyst (`credit_decision.propose`) | send any message to the applicant itself (`applicant_message.send`) |
| draft messages to the applicant (`applicant_message.draft`) | execute a payment (`payment.execute`); export the credit file (`credit_file.export`); create a sub-agent (`agent.create`; delegation is off) |

The actions on the right are refused (`forbidden:<type>`), and so is anything not listed
on the left (`not_allowed:<type>`). Every decision on a credit stays with a human: the
agent proposes a decision, an analyst decides. The mandate records the template it was
built from in its metadata (`template_id`, `template_version`, `template_digest`,
`template_status`), shown in the Proof Pack. That metadata is a label, not sealed into the
chain hash. What is sealed, and enforced, is the perimeter itself.

Fraud detection is not part of this template: the AI Act excludes systems used to detect
financial fraud from its creditworthiness point (Annex III, point 5(b)).

The legal references point to consumer credit to natural persons. Mortgage credit and
credit to businesses have other texts, not listed here. A human review that only signs
off the agent's proposal may not count as a human decision: the analyst must be able to
depart from it.

## Provisional baseline

This template is a **provisional** sector baseline (`stewardship` in the JSON below):

- status: `provisional`, held by the AMR registry (mandatia.eu) until a body of the
  credit sector takes it over;
- practitioner reviewers: none recorded. The list stays empty until a real review is
  recorded; no name is filled in for one.

No allowed action is irreversible, so the template sets no risk class. A mandate may add
one with `create_mandate_kwargs(risk_classes=[...])`.

When a body (board, credit committee) authorized the agent, the mandate can record its
decision (`organ_decision`), as described for the health template in
[`agent-sante-rgpd.md`](agent-sante-rgpd.md#decision-of-a-body-organ-decision).

## Limits

- The agent names the action type it asks a token for. The system that receives the
  token must map each real operation to the right type (a draft that is actually sent is
  `applicant_message.send`; an approval recorded in the credit system is `credit.grant`).
- AMR checks action types, not content: it does not read an analysis or a proposed
  decision to see whether its reasons are lawful, and it does not check which data the
  agent used.
- Delegation is off for mandates under this one. The agent must not have access to
  `create_mandate` itself, or it could register a new root mandate for a sub-agent
  (README, deployment rule).
- Templates are a Python API for now: no MCP tool lists them yet.

> **Legal references are pointers, marked `to_verify`.** They have not been reviewed
> by counsel and are not legal advice. Using this template does not make a credit
> process compliant with any of them.

## Use

```python
from amr.templates import get_template
from amr.tools.create_mandate import create_mandate

template = get_template("agent-credit")
await create_mandate(
    principal_id="org:lender",
    agent_id="agent:credit-assistant",
    scope=template.summary,
    legal_basis_regulation="Mandat de gestion",
    legal_basis_article="Art. 1984 Code civil",
    duration_hours=template.default_duration_hours,
    **template.create_mandate_kwargs(metadata={"client_ref": "CR-001"}),
)
```

End to end, with that mandate:

```text
issue_action_token(..., action_type="credit_application.read")  -> token
issue_action_token(..., action_type="credit_decision.propose")  -> token
issue_action_token(..., action_type="credit.refuse")
  -> {"denied": true, "reason": "action_out_of_scope", "detail": "forbidden:credit.refuse"}
issue_action_token(..., action_type="payment.execute")
  -> {"denied": true, "reason": "action_out_of_scope", "detail": "forbidden:payment.execute"}
create_mandate(principal_id="agent:credit-assistant", parent_mandate_id=<mandate>, ...)
  -> {"code": "delegation_not_allowed", ...}
```

These calls are the end-to-end tests in `tests/test_template_credit.py`.

## Machine-readable template

The JSON below is `template.to_json(indent=2)`; a test checks that it matches the code.
`template.digest()` is the SHA-256 of its compact form.

```json
{
  "actions": {
    "agent.create": "Forbidden: create a sub-agent (delegation is off as well).",
    "applicant_message.draft": "Draft a message to the applicant, sent only by a human.",
    "applicant_message.send": "Forbidden: send any message to the applicant without a human.",
    "credit.grant": "Forbidden: grant a credit; a human decides.",
    "credit.refuse": "Forbidden: refuse a credit or close an application; a human decides.",
    "credit_application.read": "Read the credit application and the documents the applicant provided.",
    "credit_decision.propose": "Propose a reasoned decision to a human analyst, who decides.",
    "credit_file.export": "Forbidden: export or transfer the credit file.",
    "credit_terms.set": "Forbidden: set the final rate, amount or duration of a credit.",
    "creditworthiness_analysis.draft": "Draft a creditworthiness analysis for a human analyst.",
    "payment.execute": "Forbidden: execute a payment or release funds."
  },
  "default_duration_hours": 720.0,
  "legal_references": [
    {
      "reference": "Regulation (EU) 2024/1689 (AI Act), Annex III, point 5(b)",
      "status": "to_verify",
      "topic": "AI systems to evaluate the creditworthiness of natural persons or establish their credit score, listed as high-risk, except systems used to detect financial fraud."
    },
    {
      "reference": "Regulation (EU) 2024/1689 (AI Act), Art. 26",
      "status": "to_verify",
      "topic": "Obligations of deployers of high-risk AI systems."
    },
    {
      "reference": "Regulation (EU) 2024/1689 (AI Act), Art. 27",
      "status": "to_verify",
      "topic": "Fundamental rights impact assessment, to be performed before use by deployers of the high-risk systems of Annex III, point 5(b)."
    },
    {
      "reference": "Regulation (EU) 2024/1689 (AI Act), Art. 86",
      "status": "to_verify",
      "topic": "Right of a person affected by a decision taken on the basis of a high-risk AI system's output to obtain explanations from the deployer."
    },
    {
      "reference": "Regulation (EU) 2016/679 (GDPR), Art. 22",
      "status": "to_verify",
      "topic": "Decisions based solely on automated processing, including profiling."
    },
    {
      "reference": "Directive (EU) 2023/2225 (consumer credit), Art. 18, including Art. 18(8)",
      "status": "to_verify",
      "topic": "Creditworthiness assessment; where it involves automated processing, the consumer's right to human intervention, an explanation and a review. Applies from 20 November 2026 (Art. 48(1)), through national transposing measures."
    },
    {
      "reference": "Code de la consommation (FR), Art. L312-16",
      "status": "to_verify",
      "topic": "Creditworthiness assessment by the lender before a consumer credit contract; check the version in force on the date of use."
    }
  ],
  "notes": [
    "Legal references are pointers to check, not legal advice.",
    "Every decision on a credit (grant, refuse, final rate, amount or duration) stays with a human: the agent proposes a decision, it does not decide.",
    "Fraud detection is not part of this template.",
    "The references point to consumer credit to natural persons; mortgage credit and credit to businesses have other texts, not listed here.",
    "A human review that only signs off the agent's proposal may not count as a human decision: the reviewer must be able to depart from it.",
    "The agent names the action type it asks a token for: the system that receives the token must map each real operation to the right type (a draft that is actually sent is applicant_message.send; an approval recorded in the credit system is credit.grant).",
    "No allowed action is irreversible, so the template sets no risk class; a mandate may add one.",
    "Delegation is off for mandates under this one. The agent must not have access to create_mandate itself, or it could register a new root mandate for a sub-agent.",
    "When a body authorized the agent, record its decision (organ_decision) with the persons or roles it designates. AMR records what the principal declares: it does not check that the decision exists or that the people named are who they say."
  ],
  "organ_decision": "optional",
  "perimeter": {
    "allowed_actions": [
      "applicant_message.draft",
      "credit_application.read",
      "credit_decision.propose",
      "creditworthiness_analysis.draft"
    ],
    "amount_actions": [],
    "currency": "EUR",
    "delegation_allowed": false,
    "forbidden_actions": [
      "agent.create",
      "applicant_message.send",
      "credit.grant",
      "credit.refuse",
      "credit_file.export",
      "credit_terms.set",
      "payment.execute"
    ],
    "max_amount": null
  },
  "sector": "credit",
  "stewardship": {
    "handover": "Provisional baseline published by the registry until a body of the credit sector takes it over; that body then holds the template and its versions.",
    "held_by": "AMR registry (mandatia.eu)",
    "reviewers": [],
    "status": "provisional"
  },
  "summary": "Assist a credit analyst: read the credit application and the documents provided, draft a creditworthiness analysis, propose a reasoned decision to a human analyst, draft messages to the applicant for a human to send. Never grant or refuse a credit, set the final rate, amount or duration, send any message to the applicant, execute a payment, export the credit file, or create a sub-agent.",
  "template_id": "agent-credit",
  "title": "Credit analysis assistant agent (human decides on every credit)",
  "version": "1.0.0"
}
```
