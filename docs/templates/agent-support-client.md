# Template `agent-support-client`: customer support agent

A ready-made, machine-readable perimeter for an AI agent that answers customers for a
business. It fills in the perimeter arguments of `create_mandate`; the token issuer then
enforces it like any other structured perimeter.

| The agent may | The agent may never |
|---|---|
| read the customer's account and history (`customer_account.read`) | refuse a refund or a complaint (`refund.refuse`, `complaint.refuse`) |
| answer a ticket, saying the answer comes from an AI (`ticket.answer`) | terminate a contract (`contract.terminate`); close an account (`account.close`) |
| route a ticket (`ticket.route`) | change payment details (`payment_details.change`) |
| propose a commercial gesture (`commercial_gesture.propose`) | export the customer's data (`customer_data.export`) |
| grant a commercial gesture under the ceiling (`commercial_gesture.grant`) | create a sub-agent (`agent.create`; delegation is off) |

The actions on the right are refused (`forbidden:<type>`), and so is anything not listed
on the left (`not_allowed:<type>`). Every decision that goes against the customer is a
forbidden action type, for a human to take. AMR enforces this on the action types only:
see the limits below for what an answer or a routing could still say. The mandate records the template it was built from in its metadata
(`template_id`, `template_version`, `template_digest`, `template_status`), shown in the
Proof Pack. That metadata is a label, not sealed into the chain hash. What is sealed, and
enforced, is the perimeter itself.

## Ceiling of a commercial gesture

`commercial_gesture.grant` is the only allowed action type meant to commit money. A
token for it needs `amount` and `currency` in the action metadata (`amount_required`
without an amount, `currency_required` without a currency, `currency_mismatch:EUR` in
another currency), at or below the ceiling: 50 EUR per gesture by default
(`amount_above_limit:50 EUR` above it). A mandate may lower the ceiling with
`create_mandate_kwargs(max_amount="20")`, never raise it.

There is no cumulative ceiling per period in this template: tokens are refused only for
an identical request still active, so several gestures to the same customer can add up.
A principal who needs a total cap adds `period_max_amount` and `period_days` to the
arguments before calling `create_mandate`:

```python
kwargs = template.create_mandate_kwargs()
kwargs.update(period_max_amount="200", period_days=30)
```

Any action that states an amount is checked against the same ceiling. A proposal of a
larger gesture (`commercial_gesture.propose`) is refused if its token states the amount
(`amount_above_limit:50 EUR`); the agent asks for it without the amount and puts the
figure in the proposal itself.

## Provisional baseline

This template is a **provisional** sector baseline (`stewardship` in the JSON below):

- status: `provisional`, held by the AMR registry (mandatia.eu) until a body of the
  customer support sector takes it over;
- practitioner reviewers: none recorded. The list stays empty until a real review is
  recorded; no name is filled in for one.

The template sets no risk class. A mandate may add one with
`create_mandate_kwargs(risk_classes=[...])`, for example to shorten the tokens of
`commercial_gesture.grant`.

When a body (board, management committee) authorized the agent, the mandate can record
its decision (`organ_decision`), as described for the health template in
[`agent-sante-rgpd.md`](agent-sante-rgpd.md#decision-of-a-body-organ-decision).

## Limits

- The agent names the action type it asks a token for. The system that receives the
  token must map each real operation to the right type (a refund refused in the
  ticketing system is `refund.refuse`; a gesture actually credited is
  `commercial_gesture.grant`).
- AMR checks action types, not content: it does not read an answer to see whether it
  says that it comes from an AI, and it does not check which data the agent used. An
  answer could still tell the customer that a refund is refused or promise money, and a
  routing could send a ticket to a closed queue: the system that receives the token must
  keep refusals and promises out of `ticket.answer` and closures out of `ticket.route`.
  Article 50(1) of the AI Act is addressed to the provider of the AI system; the
  template does not say that an answer meets it.
- Delegation is off for mandates under this one. The agent must not have access to
  `create_mandate` itself, or it could register a new root mandate for a sub-agent
  (README, deployment rule).
- Templates are a Python API for now: no MCP tool lists them yet.

> **Legal references are pointers, marked `to_verify`.** They have not been reviewed
> by counsel and are not legal advice. Using this template does not make a customer
> support process compliant with any of them.

## Use

```python
from amr.templates import get_template
from amr.tools.create_mandate import create_mandate

template = get_template("agent-support-client")
await create_mandate(
    principal_id="org:retailer",
    agent_id="agent:support-assistant",
    scope=template.summary,
    legal_basis_regulation="Delegation of authority",
    legal_basis_article="Section 2",
    duration_hours=template.default_duration_hours,
    **template.create_mandate_kwargs(max_amount="20", metadata={"client_ref": "SC-001"}),
)
```

End to end, with a mandate at the default ceiling:

```text
issue_action_token(..., action_type="ticket.answer")  -> token
issue_action_token(..., action_type="commercial_gesture.grant",
                   action_metadata_json='{"amount": "30", "currency": "EUR"}')  -> token
issue_action_token(..., action_type="commercial_gesture.grant",
                   action_metadata_json='{"amount": "80", "currency": "EUR"}')
  -> {"denied": true, "reason": "action_out_of_scope", "detail": "amount_above_limit:50 EUR"}
issue_action_token(..., action_type="refund.refuse")
  -> {"denied": true, "reason": "action_out_of_scope", "detail": "forbidden:refund.refuse"}
create_mandate(principal_id="agent:support-assistant", parent_mandate_id=<mandate>, ...)
  -> {"code": "delegation_not_allowed", ...}
```

These calls are the end-to-end tests in `tests/test_template_support_client.py`.

## Machine-readable template

The JSON below is `template.to_json(indent=2)`; a test checks that it matches the code.
`template.digest()` is the SHA-256 of its compact form.

```json
{
  "actions": {
    "account.close": "Forbidden: close the customer's account.",
    "agent.create": "Forbidden: create a sub-agent (delegation is off as well).",
    "commercial_gesture.grant": "Grant a commercial gesture, with an amount at or below the mandate's ceiling.",
    "commercial_gesture.propose": "Propose a commercial gesture to a human, who decides.",
    "complaint.refuse": "Forbidden: reject a complaint; a human decides.",
    "contract.terminate": "Forbidden: terminate the customer's contract.",
    "customer_account.read": "Read the customer's account and the history of their tickets.",
    "customer_data.export": "Forbidden: export or transfer the customer's data.",
    "payment_details.change": "Forbidden: change the customer's payment details.",
    "refund.refuse": "Forbidden: refuse a refund; a human decides.",
    "ticket.answer": "Answer a ticket, saying that the answer comes from an AI.",
    "ticket.route": "Route a ticket to a human team or another queue."
  },
  "default_duration_hours": 720.0,
  "legal_references": [
    {
      "reference": "Regulation (EU) 2024/1689 (AI Act), Art. 50(1)",
      "status": "to_verify",
      "topic": "Providers design AI systems that interact directly with natural persons so that those persons are informed they are interacting with an AI system, unless obvious. Applies from 2 August 2026."
    },
    {
      "reference": "Regulation (EU) 2016/679 (GDPR), Art. 22",
      "status": "to_verify",
      "topic": "Decisions based solely on automated processing, including profiling."
    },
    {
      "reference": "Code de la consommation (FR), Art. L612-1",
      "status": "to_verify",
      "topic": "Consumer's right to use a consumer mediator free of charge; the trader guarantees access to a mediation scheme."
    },
    {
      "reference": "Code de la consommation (FR), Art. L616-1",
      "status": "to_verify",
      "topic": "The trader gives the consumer the contact details of the competent mediator, including when a complaint made to its services has not settled the dispute."
    }
  ],
  "notes": [
    "Legal references are pointers to check, not legal advice.",
    "Every decision that goes against the customer (refusing a refund or a complaint, terminating a contract, closing an account) stays with a human.",
    "AMR does not read answers or routings: an answer must not carry a refusal or a promise of money, and routing must not close a ticket; the system that receives the token checks that.",
    "The template does not say that the business must answer with an AI or that an AI answer meets the information duty of Art. 50(1): saying it is an AI is part of the action type ticket.answer, and AMR does not read the answer.",
    "The ceiling of a commercial gesture is 50 EUR per gesture by default; a mandate may lower it (create_mandate_kwargs(max_amount=...)), never raise it. There is no cumulative ceiling per period in this template: several gestures can add up, so a principal who needs a total cap adds period_max_amount and period_days to the create_mandate arguments.",
    "Any action that states an amount is checked against the ceiling: a proposal of a larger gesture is refused if its token states the amount, and is made without it.",
    "The agent names the action type it asks a token for: the system that receives the token must map each real operation to the right type (a refund refused in the ticketing system is refund.refuse; a gesture actually credited is commercial_gesture.grant).",
    "The template sets no risk class; a mandate may add one, for example to shorten the tokens of commercial_gesture.grant.",
    "Delegation is off for mandates under this one. The agent must not have access to create_mandate itself, or it could register a new root mandate for a sub-agent.",
    "When a body authorized the agent, record its decision (organ_decision) with the persons or roles it designates. AMR records what the principal declares: it does not check that the decision exists or that the people named are who they say."
  ],
  "organ_decision": "optional",
  "perimeter": {
    "allowed_actions": [
      "commercial_gesture.grant",
      "commercial_gesture.propose",
      "customer_account.read",
      "ticket.answer",
      "ticket.route"
    ],
    "amount_actions": [
      "commercial_gesture.grant"
    ],
    "currency": "EUR",
    "delegation_allowed": false,
    "forbidden_actions": [
      "account.close",
      "agent.create",
      "complaint.refuse",
      "contract.terminate",
      "customer_data.export",
      "payment_details.change",
      "refund.refuse"
    ],
    "max_amount": "50"
  },
  "sector": "customer-support",
  "stewardship": {
    "handover": "Provisional baseline published by the registry until a body of the customer support sector takes it over; that body then holds the template and its versions.",
    "held_by": "AMR registry (mandatia.eu)",
    "reviewers": [],
    "status": "provisional"
  },
  "summary": "Answer customers for a business: read the customer's account and history, answer a ticket while saying the answer comes from an AI, route a ticket, propose a commercial gesture, grant a commercial gesture under a ceiling. Never refuse a refund or a complaint, terminate a contract, close an account, change payment details, export the customer's data, or create a sub-agent.",
  "template_id": "agent-support-client",
  "title": "Customer support agent (human decides against the customer)",
  "version": "1.0.0"
}
```
