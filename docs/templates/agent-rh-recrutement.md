# Template `agent-rh-recrutement`: recruitment assistant

A ready-made, machine-readable perimeter for an AI agent that assists a recruiter. It fills
in the perimeter arguments of `create_mandate`; the token issuer then enforces it like any
other structured perimeter.

| The agent may | The agent may never |
|---|---|
| read the applications received (`application.read`) | reject or select a candidate (`candidate.reject`, `candidate.select`) |
| draft a job posting (`job_posting.draft`) | send a job offer or a rejection (`offer.send`, `rejection.send`) |
| propose a reasoned shortlist to a human recruiter (`shortlist.propose`) | send any message to a candidate itself (`candidate_message.send`) |
| propose and book interview slots in the company calendar (`interview.propose`, `interview.book`) | recognize emotions, categorize people from biometric data, infer sensitive data |
| draft candidate messages (`candidate_message.draft`) | export candidate data; create a sub-agent (`agent.create`; delegation is off) |

Anything not listed on the left is refused (`not_allowed`). Every decision about a person
stays with a human: the agent proposes a shortlist, a recruiter decides. The mandate
records the template it was built from in its metadata (`template_id`,
`template_version`, `template_digest`, `template_status`), shown in the Proof Pack. That
metadata is a label, not sealed into the chain hash. What is sealed, and enforced, is the
perimeter itself.

## Provisional baseline

This template is a **provisional** sector baseline (`stewardship` in the JSON below):

- status: `provisional`, held by the AMR registry (mandatia.eu) until a body of the
  employment sector takes it over;
- practitioner reviewers: none recorded. The list stays empty until a real review is
  recorded; no name is filled in for one.

No allowed action is irreversible, so the template sets no risk class. A mandate may add
one with `create_mandate_kwargs(risk_classes=[...])`, for example a short token window
for `interview.book`.

When a body (board, committee) authorized the agent, the mandate can record its decision
(`organ_decision`), as described for the health template in
[`agent-sante-rgpd.md`](agent-sante-rgpd.md#decision-of-a-body-organ-decision).

## Limits

- `interview.book` must not notify the candidate: a confirmation sent to the candidate
  is a candidate message, which this template forbids.
- The agent names the action type it asks a token for. The system that receives the
  token must map each real operation to the right type (a draft that is actually sent is
  `candidate_message.send`, `offer.send` or `rejection.send`).
- AMR checks action types, not content: it does not read a shortlist to see whether its
  reasons are lawful, and it does not detect an emotion inference hidden inside an
  allowed action.
- Delegation is off for mandates under this one. The agent must not have access to
  `create_mandate` itself, or it could register a new root mandate for a sub-agent
  (README, deployment rule).
- Templates are a Python API for now: no MCP tool lists them yet.

> **Legal references are pointers, marked `to_verify`.** They have not been reviewed
> by counsel and are not legal advice. Using this template does not make a recruitment
> process compliant with any of them.

## Use

```python
from amr.templates import get_template
from amr.tools.create_mandate import create_mandate

template = get_template("agent-rh-recrutement")
await create_mandate(
    principal_id="org:employer",
    agent_id="agent:recruitment-assistant",
    scope=template.summary,
    legal_basis_regulation="Mandat de gestion",
    legal_basis_article="Art. 1984 Code civil",
    duration_hours=template.default_duration_hours,
    **template.create_mandate_kwargs(metadata={"client_ref": "RH-001"}),
)
```

End to end, with that mandate:

```text
issue_action_token(..., action_type="application.read")     -> token
issue_action_token(..., action_type="shortlist.propose")    -> token
issue_action_token(..., action_type="candidate.reject")
  -> {"denied": true, "reason": "action_out_of_scope", "detail": "forbidden:candidate.reject"}
issue_action_token(..., action_type="emotion_recognition")
  -> {"denied": true, "reason": "action_out_of_scope", "detail": "forbidden:emotion_recognition"}
create_mandate(principal_id="agent:recruitment-assistant", parent_mandate_id=<mandate>, ...)
  -> {"code": "delegation_not_allowed", ...}
```

These calls are the end-to-end tests in `tests/test_template_rh_recrutement.py`.

## Machine-readable template

The JSON below is `template.to_json(indent=2)`; a test checks that it matches the code.
`template.digest()` is the SHA-256 of its compact form.

```json
{
  "actions": {
    "agent.create": "Forbidden: create a sub-agent (delegation is off as well).",
    "application.read": "Read the applications received for the position at hand.",
    "biometric_categorisation": "Forbidden: categorize people from biometric data.",
    "candidate.reject": "Forbidden: reject a candidate or close an application.",
    "candidate.select": "Forbidden: select or retain a candidate; a human decides.",
    "candidate_data.export": "Forbidden: export or transfer candidate data.",
    "candidate_message.draft": "Draft a message to a candidate, sent only by a human.",
    "candidate_message.send": "Forbidden: send any message to a candidate without a human.",
    "emotion_recognition": "Forbidden: infer the emotions of a candidate or a worker.",
    "interview.book": "Book an interview slot in the company's own calendar.",
    "interview.propose": "Propose an interview slot, to be confirmed by a human.",
    "job_posting.draft": "Draft a job posting, published only by a human.",
    "offer.send": "Forbidden: send a job offer.",
    "rejection.send": "Forbidden: send a rejection.",
    "sensitive_data.infer": "Forbidden: infer sensitive data about a person (special categories of personal data).",
    "shortlist.propose": "Propose a reasoned shortlist to a human recruiter, who decides."
  },
  "default_duration_hours": 720.0,
  "legal_references": [
    {
      "reference": "Regulation (EU) 2024/1689 (AI Act), Annex III, point 4(a)",
      "status": "to_verify",
      "topic": "AI systems for the recruitment or selection of natural persons (targeted job ads, analysing and filtering applications, evaluating candidates), listed as high-risk."
    },
    {
      "reference": "Regulation (EU) 2024/1689 (AI Act), Art. 26, including Art. 26(7)",
      "status": "to_verify",
      "topic": "Obligations of deployers of high-risk AI systems; employers inform workers' representatives and the affected workers before use at the workplace."
    },
    {
      "reference": "Regulation (EU) 2024/1689 (AI Act), Art. 5(1)(f)",
      "status": "to_verify",
      "topic": "Prohibition of AI systems that infer emotions in the workplace, except for medical or safety reasons."
    },
    {
      "reference": "Regulation (EU) 2016/679 (GDPR), Art. 22",
      "status": "to_verify",
      "topic": "Decisions based solely on automated processing, including profiling."
    },
    {
      "reference": "Code du travail (FR), Art. L1132-1",
      "status": "to_verify",
      "topic": "Principle of non-discrimination, including in recruitment procedures."
    },
    {
      "reference": "Code du travail (FR), Art. L1221-8",
      "status": "to_verify",
      "topic": "Candidates informed beforehand of the recruitment methods and techniques used; methods relevant to the aim; results confidential."
    },
    {
      "reference": "Code du travail (FR), Art. L1221-9",
      "status": "to_verify",
      "topic": "No personal information on a candidate collected by a device not brought to the candidate's knowledge beforehand."
    }
  ],
  "notes": [
    "Legal references are pointers to check, not legal advice.",
    "Every decision about a candidate (reject, select, offer, rejection) stays with a human: the agent proposes a shortlist, it does not decide.",
    "interview.book must not notify the candidate: a confirmation sent to the candidate is a candidate message, which this template forbids.",
    "The agent names the action type it asks a token for: the system that receives the token must map each real operation to the right type (a draft that is actually sent is candidate_message.send, offer.send or rejection.send).",
    "No allowed action is irreversible, so the template sets no risk class; a mandate may add one.",
    "Delegation is off for mandates under this one. The agent must not have access to create_mandate itself, or it could register a new root mandate for a sub-agent.",
    "When a body authorized the agent, record its decision (organ_decision) with the persons or roles it designates. AMR records what the principal declares: it does not check that the decision exists or that the people named are who they say."
  ],
  "organ_decision": "optional",
  "perimeter": {
    "allowed_actions": [
      "application.read",
      "candidate_message.draft",
      "interview.book",
      "interview.propose",
      "job_posting.draft",
      "shortlist.propose"
    ],
    "amount_actions": [],
    "currency": "EUR",
    "delegation_allowed": false,
    "forbidden_actions": [
      "agent.create",
      "biometric_categorisation",
      "candidate.reject",
      "candidate.select",
      "candidate_data.export",
      "candidate_message.send",
      "emotion_recognition",
      "offer.send",
      "rejection.send",
      "sensitive_data.infer"
    ],
    "max_amount": null
  },
  "sector": "employment",
  "stewardship": {
    "handover": "Provisional baseline published by the registry until a body of the employment sector takes it over; that body then holds the template and its versions.",
    "held_by": "AMR registry (mandatia.eu)",
    "reviewers": [],
    "status": "provisional"
  },
  "summary": "Assist a recruiter: read the applications received, draft a job posting, propose a reasoned shortlist to a human recruiter, propose and book interview slots in the company calendar, draft candidate messages for a human to send. Never reject or select a candidate, send an offer, a rejection or any message to a candidate, recognize emotions, categorize people from biometric data, infer sensitive data, export candidate data, or create a sub-agent.",
  "template_id": "agent-rh-recrutement",
  "title": "Recruitment assistant agent (human decides on every candidate)",
  "version": "1.0.0"
}
```
