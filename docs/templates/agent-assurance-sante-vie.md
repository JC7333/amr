# Template `agent-assurance-sante-vie`: life and health underwriting assistant

A ready-made, machine-readable perimeter for an AI agent that assists a life or health
insurance underwriter. It fills in the perimeter arguments of `create_mandate`; the token
issuer then enforces it like any other structured perimeter.

| The agent may | The agent may never |
|---|---|
| read the underwriting file and the documents provided (`underwriting_file.read`) | accept or refuse an application (`application.accept`, `application.refuse`) |
| draft a risk assessment (`risk_assessment.draft`) | set the final premium (`premium.set`) |
| propose a reasoned premium to a human underwriter (`premium.propose`) | send any message to the insured person itself (`insured_message.send`) |
| draft the contract documents (`contract_documents.draft`) | use the result of a genetic test (`genetic_test_result.use`) |
| draft messages to the insured person (`insured_message.draft`) | export health data (`health_data.export`); create a sub-agent (`agent.create`; delegation is off) |

The actions on the right are refused (`forbidden:<type>`), and so is anything not listed
on the left (`not_allowed:<type>`). Every decision on an application stays with a human:
the agent proposes a premium, an underwriter decides. The mandate records the template it
was built from in its metadata (`template_id`, `template_version`, `template_digest`,
`template_status`), shown in the Proof Pack. That metadata is a label, not sealed into the
chain hash. What is sealed, and enforced, is the perimeter itself.

Claims handling is not part of this template: it covers risk assessment and pricing for
natural persons in life and health insurance (AI Act, Annex III, point 5(c)).

The rules differ between insurers (Code des assurances), mutual insurers (Code de la
mutualité) and provident institutions (Code de la sécurité sociale): the principal checks
the ones that apply to it. A human review that only signs off the agent's proposal may
not count as a human decision: the underwriter must be able to depart from it.

## Provisional baseline

This template is a **provisional** sector baseline (`stewardship` in the JSON below):

- status: `provisional`, held by the AMR registry (mandatia.eu) until a body of the
  insurance sector takes it over;
- practitioner reviewers: none recorded. The list stays empty until a real review is
  recorded; no name is filled in for one.

No allowed action is irreversible, so the template sets no risk class. A mandate may add
one with `create_mandate_kwargs(risk_classes=[...])`.

When a body (board, underwriting committee) authorized the agent, the mandate can record
its decision (`organ_decision`), as described for the health template in
[`agent-sante-rgpd.md`](agent-sante-rgpd.md#decision-of-a-body-organ-decision).

## Limits

- The agent names the action type it asks a token for. The system that receives the
  token must map each real operation to the right type (a draft that is actually sent is
  `insured_message.send`; a premium recorded in the policy system is `premium.set`).
- AMR checks action types, not content: it does not read a risk assessment or a proposed
  premium to see whether its reasons are lawful, and it does not check which data the
  agent used. Forbidding `genetic_test_result.use` refuses a token for that action type;
  it does not stop an agent from reading a genetic result hidden in a file it may read.
- Delegation is off for mandates under this one. The agent must not have access to
  `create_mandate` itself, or it could register a new root mandate for a sub-agent
  (README, deployment rule).
- Templates are a Python API for now: no MCP tool lists them yet.

> **Legal references are pointers, marked `to_verify`.** They have not been reviewed
> by counsel and are not legal advice. Using this template does not make an
> underwriting process compliant with any of them.

## Use

```python
from amr.templates import get_template
from amr.tools.create_mandate import create_mandate

template = get_template("agent-assurance-sante-vie")
await create_mandate(
    principal_id="org:insurer",
    agent_id="agent:underwriting-assistant",
    scope=template.summary,
    legal_basis_regulation="Mandat de gestion",
    legal_basis_article="Art. 1984 Code civil",
    duration_hours=template.default_duration_hours,
    **template.create_mandate_kwargs(metadata={"client_ref": "UW-001"}),
)
```

End to end, with that mandate:

```text
issue_action_token(..., action_type="underwriting_file.read")  -> token
issue_action_token(..., action_type="premium.propose")  -> token
issue_action_token(..., action_type="application.refuse")
  -> {"denied": true, "reason": "action_out_of_scope", "detail": "forbidden:application.refuse"}
issue_action_token(..., action_type="genetic_test_result.use")
  -> {"denied": true, "reason": "action_out_of_scope", "detail": "forbidden:genetic_test_result.use"}
create_mandate(principal_id="agent:underwriting-assistant", parent_mandate_id=<mandate>, ...)
  -> {"code": "delegation_not_allowed", ...}
```

These calls are the end-to-end tests in `tests/test_template_assurance_sante_vie.py`.

## Machine-readable template

The JSON below is `template.to_json(indent=2)`; a test checks that it matches the code.
`template.digest()` is the SHA-256 of its compact form.

```json
{
  "actions": {
    "agent.create": "Forbidden: create a sub-agent (delegation is off as well).",
    "application.accept": "Forbidden: accept an application; a human decides.",
    "application.refuse": "Forbidden: refuse an application or add an exclusion; a human decides.",
    "contract_documents.draft": "Draft the contract documents for a human to review.",
    "genetic_test_result.use": "Forbidden: ask for, read or use the result of a genetic test.",
    "health_data.export": "Forbidden: export or transfer health data.",
    "insured_message.draft": "Draft a message to the insured person, sent only by a human.",
    "insured_message.send": "Forbidden: send any message to the insured person without a human.",
    "premium.propose": "Propose a reasoned premium to a human underwriter, who decides.",
    "premium.set": "Forbidden: set the final premium.",
    "risk_assessment.draft": "Draft a risk assessment for a human underwriter.",
    "underwriting_file.read": "Read the underwriting file and the documents the applicant provided."
  },
  "default_duration_hours": 720.0,
  "legal_references": [
    {
      "reference": "Regulation (EU) 2024/1689 (AI Act), Annex III, point 5(c)",
      "status": "to_verify",
      "topic": "AI systems for risk assessment and pricing in relation to natural persons in the case of life and health insurance, listed as high-risk."
    },
    {
      "reference": "Regulation (EU) 2024/1689 (AI Act), Art. 26",
      "status": "to_verify",
      "topic": "Obligations of deployers of high-risk AI systems."
    },
    {
      "reference": "Regulation (EU) 2024/1689 (AI Act), Art. 27",
      "status": "to_verify",
      "topic": "Fundamental rights impact assessment, to be performed before use by deployers of the high-risk systems of Annex III, point 5(c)."
    },
    {
      "reference": "Regulation (EU) 2024/1689 (AI Act), Art. 86",
      "status": "to_verify",
      "topic": "Right of a person affected by a decision taken on the basis of a high-risk AI system's output to obtain explanations from the deployer."
    },
    {
      "reference": "Regulation (EU) 2016/679 (GDPR), Art. 9",
      "status": "to_verify",
      "topic": "Processing of special categories of personal data, including health and genetic data: prohibited unless an exception of Art. 9(2) applies."
    },
    {
      "reference": "Regulation (EU) 2016/679 (GDPR), Art. 22",
      "status": "to_verify",
      "topic": "Decisions based solely on automated processing, including profiling."
    },
    {
      "reference": "Code de la santé publique (FR), Art. L1141-1",
      "status": "to_verify",
      "topic": "Insurers covering invalidity or death may not take the results of a genetic test into account, ask about such tests or require one."
    },
    {
      "reference": "Code de la santé publique (FR), Art. L1141-5",
      "status": "to_verify",
      "topic": "Right to be forgotten: delay after the end of treatment for cancer or hepatitis C beyond which no medical information on it may be collected."
    },
    {
      "reference": "Code des assurances (FR), Art. L113-2-1",
      "status": "to_verify",
      "topic": "Borrower insurance: no health questionnaire or medical examination within the insured amount and age limits set by the article."
    },
    {
      "reference": "Code de la mutualité (FR), Art. L112-1",
      "status": "to_verify",
      "topic": "Mutual insurers: for optional health cost cover, no collection of medical information and no contribution based on health status; check the version in force on the date of use."
    }
  ],
  "notes": [
    "Legal references are pointers to check, not legal advice.",
    "Every decision on an application (accept, refuse, final premium) stays with a human: the agent proposes a premium, it does not decide.",
    "Claims handling is not part of this template.",
    "The rules differ between insurers (Code des assurances), mutual insurers (Code de la mutualité) and provident institutions (Code de la sécurité sociale): the principal checks the ones that apply to it.",
    "A human review that only signs off the agent's proposal may not count as a human decision: the reviewer must be able to depart from it.",
    "The agent names the action type it asks a token for: the system that receives the token must map each real operation to the right type (a draft that is actually sent is insured_message.send; a premium recorded in the policy system is premium.set).",
    "No allowed action is irreversible, so the template sets no risk class; a mandate may add one.",
    "Delegation is off for mandates under this one. The agent must not have access to create_mandate itself, or it could register a new root mandate for a sub-agent.",
    "When a body authorized the agent, record its decision (organ_decision) with the persons or roles it designates. AMR records what the principal declares: it does not check that the decision exists or that the people named are who they say."
  ],
  "organ_decision": "optional",
  "perimeter": {
    "allowed_actions": [
      "contract_documents.draft",
      "insured_message.draft",
      "premium.propose",
      "risk_assessment.draft",
      "underwriting_file.read"
    ],
    "amount_actions": [],
    "currency": "EUR",
    "delegation_allowed": false,
    "forbidden_actions": [
      "agent.create",
      "application.accept",
      "application.refuse",
      "genetic_test_result.use",
      "health_data.export",
      "insured_message.send",
      "premium.set"
    ],
    "max_amount": null
  },
  "sector": "insurance",
  "stewardship": {
    "handover": "Provisional baseline published by the registry until a body of the insurance sector takes it over; that body then holds the template and its versions.",
    "held_by": "AMR registry (mandatia.eu)",
    "reviewers": [],
    "status": "provisional"
  },
  "summary": "Assist a life or health insurance underwriter: read the underwriting file, draft a risk assessment, propose a reasoned premium to a human underwriter, draft the contract documents and messages to the insured person for a human to send. Never accept or refuse an application, set the final premium, send any message to the insured person, use the result of a genetic test, export health data, or create a sub-agent.",
  "template_id": "agent-assurance-sante-vie",
  "title": "Life and health underwriting assistant agent (human decides on every application)",
  "version": "1.0.0"
}
```
