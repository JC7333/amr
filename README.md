# Agent Mandate Registry (AMR)

<!-- mcp-name: io.github.JC7333/mandatia -->

> **Records who authorized an AI agent to do what, until when.**

AMR is an open-source [MCP](https://modelcontextprotocol.io/) server that registers, verifies, and audits mandates authorizing AI agents to act on behalf of principals. Here a mandate is the written authorization a person or a body gives for its agent: it binds the one who gives it, not the agent, which is not a person. It provides a cryptographically chained audit trail of who authorized which agent to do what, until when: evidence that supports the human-oversight and record-keeping duties of deployers under **EU AI Act Article 26**, with **eIDAS 2.0** electronic mandates in mind. AMR is a technical tool: it does not by itself make a system compliant.

---

## Quickstart for agents

This section is written so that an AI agent (Claude Code, Cursor, any MCP client) can
install AMR and reach a first verified mandate on its own: no account, no email, no
person to ask. Everything runs on your machine; AMR makes no network call (two opt-in
exceptions, both off by default: `report_issue` once the operator sets `AMR_ISSUE_TOKEN`,
and the `did:web` key check once the operator sets `AMR_DID_WEB_RESOLVE=1`).

**1. Run the server** (needs [uv](https://docs.astral.sh/uv/)).

```bash
uvx mandatia
```

The PyPI package is named `mandatia`; the Python module and the `amr` command keep their
names. `uvx amr` installs a different, unrelated project: do not use it. To run the
latest code of the repository instead:

```bash
uvx --from git+https://github.com/JC7333/amr amr
```

AMR runs with version 1 and version 2 of the MCP Python SDK (`mcp>=1.2,<3`); no extra
version pin is needed.

Or clone the repository and run `uv sync && uv run amr`.

**2. Declare it in your MCP client.**

Claude Code:

```bash
claude mcp add amr -- uvx mandatia
```

Cursor (`.cursor/mcp.json`) and other clients that read an `mcpServers` object:

```json
{
  "mcpServers": {
    "amr": {
      "command": "uvx",
      "args": ["mandatia"],
      "env": {
        "AMR_DB_PATH": "/absolute/path/amr_mandates.db",
        "AMR_SIGNING_KEY_PATH": "/absolute/path/amr_signing_key.pem",
        "AMR_PUBLIC_KEY_PATH": "/absolute/path/amr_signing_key.pub"
      }
    }
  }
}
```

To run the repository code instead, the arguments are
`["--from", "git+https://github.com/JC7333/amr", "amr"]`.
Set the three paths: by default AMR writes its database and its signing key in the
current directory of the client. Keep the `.pem` private key out of version control.

**Give each side only its own tools.** An agent that can create, sign or revoke its own
mandate authorizes itself, and the mandate then proves nothing. Set `AMR_TOOL_PROFILE`
in the `env` block of each client, all pointing at the same `AMR_DB_PATH`:

| `AMR_TOOL_PROFILE` | Who runs it | Tools |
|---|---|---|
| `principal` | the person or body that grants mandates | create, sign, revoke, contest, prove (`create_mandate`, `register_principal_key`, `revoke_mandate`, `contest_action`, `get_proof`, `export_insurer_dossier`, ...) |
| `agent` | the agent that acts under a mandate | `verify_mandate`, `issue_action_token`, `log_action`, `issue_mandate_attestation`, `get_registry_public_key`; `create_mandate` for sub-mandates under its own mandate only |
| `receiver` | a third party the agent acts upon | `check_action_token`, `get_registry_public_key` |
| `full` (default) | tests and single-user setups | every tool |

With `agent`, `create_mandate` refuses a mandate without `parent_mandate_id`
(`root_mandate_needs_principal`).

**3. Reach a first verified mandate.** The tools, in the order an agent uses them:

1. `create_mandate`: register who authorizes what (`principal_id`, `agent_id`, `scope`,
   `legal_basis_regulation`, `legal_basis_article`, `duration_hours`; add
   `allowed_actions` / `forbidden_actions` for a perimeter; only `issue_action_token`
   enforces it).
2. `verify_mandate(agent_id, action)`: `authorized: true` while the agent has an active
   mandate. It does not check `action` against the perimeter; `issue_action_token` does.
3. `issue_action_token(mandate_id, agent_id, action, audience, action_type,
   action_metadata_json)`: before acting, the agent asks for a signed token. Under a
   perimeter, `action_type` is required (e.g. `"invoice.pay"`), and an amount goes in
   `action_metadata_json` as a decimal string: `'{"amount": "120", "currency": "EUR"}'`.
   Outside the perimeter or above a ceiling the answer is `denied: true` with
   `reason: "action_out_of_scope"` and a `detail` (`forbidden:agent.create`,
   `amount_above_limit:500 EUR`, ...). No token, no action. The receiver checks the token
   with `check_action_token` (profile `receiver`).
4. `log_action(mandate_id, action)`: append an entry to the hash-chained journal. Logging
   is a statement by the agent's operator, not a check: it is not tied to a token, so put
   the token's `jti` in `evidence` to link the two.
5. `issue_mandate_attestation` + `get_registry_public_key`: a signed document a third
   party checks offline with `python -m amr.verify_attestation`.
6. `revoke_mandate(mandate_id, reason)`: the stop button. That mandate then issues no
   token, and `verify_mandate` answers `authorized: false` unless the agent holds another
   active mandate. Tokens and attestations already issued stay valid until they expire,
   except for a receiver that re-checks the token with `check_action_token`.
7. `get_proof(mandate_id)`: the full audit bundle (mandate, actions, integrity).
   If the agent already did something it should not have, `contest_action(mandate_id,
   action_id, reason, response_days)` records that the act is disputed, and
   `list_action_contests` reminds the deadline the operator chose.
8. `report_issue(title, description, version, context)`: report a problem with AMR
   itself. Without `AMR_ISSUE_TOKEN` it makes no network call and returns a pre-filled
   link to open; with it, it files the issue on GitHub. See
   [`docs/report-issue-spec.md`](https://github.com/JC7333/amr/blob/main/docs/report-issue-spec.md).

The same flow, runnable and checked by the test suite, is in
[`examples/quickstart_agent.py`](https://github.com/JC7333/amr/blob/main/examples/quickstart_agent.py):

```bash
git clone https://github.com/JC7333/amr.git && cd amr && uv sync
uv run python examples/quickstart_agent.py   # prints every step, ends with "OK"
```

Machine-readable summaries for agents: [`AGENTS.md`](https://github.com/JC7333/amr/blob/main/AGENTS.md) and [`llms.txt`](https://github.com/JC7333/amr/blob/main/llms.txt).
To report a problem, call `report_issue` or open an issue at
https://github.com/JC7333/amr/issues (never paste real mandate contents or personal data
into it).

---

## Why AMR?

Modern AI agent infrastructure covers many concerns — but the record of who authorized an agent, for what and until when, is missing:

| Concern | Existing tools | AMR |
|---|---|---|
| Infrastructure & orchestration | ✅ LangChain, AutoGen, CrewAI | — |
| Security & sandboxing | ✅ Docker, RBAC, network policies | — |
| Permission & access control | ✅ OAuth, IAM, API keys | — |
| Observability & tracing | ✅ OpenTelemetry, Langfuse | — |
| **Authorization record & accountability** | ❌ **Not covered** | ✅ **AMR** |

**EU AI Act Article 26** ([Regulation (EU) 2024/1689](https://eur-lex.europa.eu/eli/reg/2024/1689/oj)) requires deployers of high-risk AI systems to assign human oversight and to keep the logs the system generates, to the extent they are under their control, for at least six months (Art. 26(6)). It applies from 2 December 2027 for Annex III systems and 2 August 2028 for Annex I systems ([Regulation (EU) 2026/1744](https://eur-lex.europa.eu/eli/reg/2026/1744/oj)). Non-compliance with Article 26 can be fined up to **€15 million or 3% of worldwide annual turnover**, whichever is higher (Art. 99(4); for SMEs and start-ups, whichever is lower, Art. 99(6)). AMR records who authorized an agent, for what and until when, and what it did, in a tamper-evident form that this oversight can rely on; it complements the system's own logs, it does not replace them.

---

### Structural hard-stop enforcement

AMR does not only record mandates — it enforces them. Agent runtimes must obtain
a signed action token from AMR before performing any action. The token is issued
if and only if a valid, non-expired, non-revoked mandate authorizes that specific
action for that specific agent. No mandate → no token → no action.

Tokens are JWS (RFC 7515) signed with Ed25519 (EdDSA), include replay prevention
via the `jti` claim and the `issued_tokens` audit table, and carry the exact
action hash and scope digest they authorize. Consumers verify offline with the
AMR public key and MUST check `aud`, `exp`, and `amr_action_hash`.

### Perimeter enforcement and delegation control

A mandate can carry a **structured perimeter**: the action types the agent may
request (`allowed_actions`), the ones it may never request (`forbidden_actions`,
which always win and also reach sub-types: forbidding `agent.create` forbids
`agent.create.batch`), whether it may delegate (`delegation_allowed`), and an
optional amount ceiling (`max_amount` with `currency`, applied to `amount_actions`). The token issuer then
checks the **requested action** against the perimeter, not only the existence of
the mandate:

- an action type outside `allowed_actions`, or matching `forbidden_actions`, gets
  no token (`reason: "action_out_of_scope"`, with a `detail` and the mandate that
  refused it in `refused_by`);
- a sub-mandate (`parent_mandate_id`) is created only if the parent is active,
  allows delegation, and was granted to the agent now delegating; the sub-mandate
  must stay inside the parent's allowed actions and limit, inherits the parent's
  prohibitions, and cannot outlive the parent;
- every token issued under a sub-mandate re-checks the whole chain: revoke
  (`revoke_mandate`) or let expire the parent, and every sub-mandate below it stops
  getting tokens;
- an optional **cumulative ceiling** (`period_max_amount` over a rolling window of
  `period_days` days, same `currency` and `amount_actions`) caps the total of the
  amounts of the tokens issued under the mandate **and every sub-mandate below it**
  in the window: for the actions that carry an amount (those reached by
  `amount_actions`, every action when it is empty, and any action that declares an
  `amount`), an agent cannot split a large purchase into small ones, nor spend the
  same budget again through a sub-agent (`detail:
  "period_amount_above_limit:<max> <CUR>/<days>d"`, with the mandate whose budget is
  spent in `refused_by`). A token counts as soon as it is issued, used or not; a
  refused token counts for nothing. A sub-mandate's own ceiling may not exceed the
  parent's. The parent's ceiling is not copied into the sub-mandate's perimeter (it
  binds the sub-mandate all the same, at issuance): read the whole chain, as
  `get_proof` and the attestation do, to see every ceiling that applies. A
  sub-mandate that sets a ceiling under a parent with a per-action limit binds the
  union of both `amount_actions` (an empty list on either side means every action);
- optional **risk classes** (`risk_classes`) bound how long a token stays usable,
  by what is at stake: each class names action types (reached with their sub-types,
  like `forbidden_actions`) and a `max_token_seconds` from 1 to 86400, for example
  `{"name": "irreversible", "actions": ["invoice.pay"], "max_token_seconds": 30}`.
  A token for an action reached by a class lives at most that long; the shortest
  class wins, in the mandate and in every mandate above it in the delegation chain,
  so a sub-mandate can shorten the window, never lengthen it: it inherits the
  parent's classes (shown in its own perimeter) and may reuse a class name only with
  a shorter or equal `max_token_seconds` (else `limit_exceeds_parent`). The matched class
  names are sealed in the token as `amr_risk_classes`. A class never lengthens a
  token beyond `AMR_TOKEN_LIFETIME_SECONDS`. Mandates without classes keep their
  exact hash and tokens. A class may also set `"registry_check": true`: its tokens
  then carry `amr_registry_check: true`, and the receiver re-checks them with
  `check_action_token` at the moment of acting, so a revocation in the meantime is
  seen. A sub-mandate inherits the flag and cannot drop it. Classes without it keep
  their exact form and hash.

Example: an assistant agent told never to create sub-agents.

```json
create_mandate(..., allowed_actions=["report.*"], forbidden_actions=["agent.create"])
issue_action_token(..., action_type="agent.create")
→ {"denied": true, "reason": "action_out_of_scope", "detail": "forbidden:agent.create"}
```

Root mandates without a perimeter keep working as before (free-text scope,
existence and validity checks only, same hashes). Perimeters without a cumulative
ceiling keep their exact canonical form, so their hashes, perimeter digests and
principal signatures are unchanged; schema v7 only adds the `token_amounts` table.
Limits of the cumulative ceiling: tokens issued before schema v7 carry no recorded
amount and are not counted (an older AMR cannot issue tokens on a capped branch: it
refuses the unknown perimeter fields); the ceiling binds one mandate and its branch,
not every mandate of the same principal. Two changes are deliberate and
breaking for sub-mandates: a new sub-mandate requires a parent that allows
delegation (so a free-text parent can no longer delegate), and tokens under any
sub-mandate, including ones created before v1.1, now require every parent to be
active and unexpired.

> **Deployment rule.** These controls hold only if agents cannot register their own
> mandates. `create_mandate` and `register_principal_key` are principal-side tools:
> expose them to the principal (or its back office), never to the agents it governs.
> An agent that can call `create_mandate` can mint itself a fresh root mandate for
> any principal without a key, and one that can call `register_principal_key` can
> claim a principal that has not registered a key yet. Principal signatures (below)
> close the first gap once each principal has registered its key; binding keys to a
> verified identity is on the roadmap.

### Principal signatures: the principal signs the mandate

A principal can register its own Ed25519 public key once (`register_principal_key`).
From then on, the registry accepts a mandate in its name only if the principal signed
it: `prepare_mandate_signature` returns the exact bytes to sign, and `create_mandate`
takes `principal_signature` and `signed_at`. The signature is sealed into the mandate's
`chain_hash`, cannot be used twice in the same registry, and is kept in the Proof Pack
with the public key and the signed bytes, so anyone can re-check it offline. Set
`AMR_REQUIRE_PRINCIPAL_SIGNATURE=true` to refuse every unsigned mandate.

What a valid signature proves: the mandate was signed with the key first registered
for that `principal_id`. For an ordinary `principal_id` the registry does not check who
registers a key (first registration wins), so register each principal's key at
onboarding, through the principal's own channel. An organisation can instead use a
`did:web:<its domain>` identifier: the key is then accepted only if the domain publishes
it in `https://<domain>/.well-known/did.json`, and the SHA-256 of that document is
sealed with the key (opt-in network access, `AMR_DID_WEB_RESOLVE=1`). This proves
control of the domain at registration time, not a qualified signature. Consumers that
rely on a `did:web` principal must check `did_web_unverified: false` in the Proof Pack,
the attestation or the insurer dossier.

The principal can also sign the mandate as a PDF with its own signature tool
(`prepare_mandate_pdf`, then `attach_signed_mandate_pdf`): the registry checks the
PAdES signature offline against the trust roots the operator chose and records the
signer named by the certificate. It does not read the EU trusted lists or check
revocation, and does not decide whether the signer may act for the principal.

**Behaviour change (did:web keys):** with the default configuration, registering a key
for a `did:web:` identifier is now refused (`did_web_resolution_disabled`) instead of
"first registration wins"; keys already registered stay valid and are reported as
`did_web_unverified`. A `scheme:method:` prefix written with non-ASCII look-alike
characters is refused (`principal_id_lookalike`). Mandates of principals without a key behave as before (same
hashes; the result gains `"principal_signature": null`); mandates created before a key
was registered stay valid. See `docs/principal-signature-spec.md`, including its
known limits.

See `docs/token-issuance-spec.md` for the full specification.

### Sector templates

A template is a ready-made, versioned perimeter for one kind of agent, with a catalog
that says in plain words what each action type means. The first one,
`agent-sante-rgpd`, covers an assistant agent in a medical practice: it may read the
record, handle the schedule, draft letters and patient messages for a human to send,
and order supplies under a ceiling; it may never prescribe, diagnose, change or export
the record, contact a patient itself, or create a sub-agent. The second one,
`agent-rh-recrutement`, covers an agent assisting a recruiter: it may read the
applications, draft a job posting, propose a shortlist to a human recruiter, propose
and book interview slots and draft candidate messages; it may never reject or select a candidate,
send an offer, a rejection or any candidate message, recognize emotions, categorize
people from biometric data, infer sensitive data, export candidate data, or create a
sub-agent. Every decision to reject, select or make an offer stays with a human. The
third one, `agent-credit`, covers an agent assisting a credit analyst: it may read the
credit application and the documents provided, draft a creditworthiness analysis,
propose a reasoned decision to a human analyst and draft messages to the applicant; it
may never grant or refuse a credit, set the final rate, amount or duration, send any message to
the applicant, execute a payment, export the credit file, or create a sub-agent. Every
decision on a credit stays with a human. Fraud detection is not part of it. The fourth
one, `agent-assurance-sante-vie`, covers an agent assisting a life or health insurance
underwriter: it may read the underwriting file, draft a risk assessment, propose a
reasoned premium to a human underwriter and draft the contract documents and messages
to the insured person; it may never accept or refuse an application, set the final
premium, send any message to the insured person, use the result of a genetic test,
export health data, or create a sub-agent. Every decision on an application stays with
a human. Claims handling is not part of it. The fifth one, `agent-support-client`, covers
an agent answering customers for a business: it may read the customer's account and
history, answer a ticket while saying the answer comes from an AI, route a ticket,
propose a commercial gesture and grant one under a ceiling (50 EUR per gesture by
default, which a mandate may lower, never raise); it may never refuse a refund or a
complaint, terminate a contract, close an account, change payment details, export the
customer's data, or create a sub-agent. Every decision that goes against the customer
stays with a human. AMR does not read the answers: they must not carry a refusal or a
promise of money.

```python
from amr.templates import get_template

template = get_template("agent-sante-rgpd")
await create_mandate(..., **template.create_mandate_kwargs())
```

The mandate records `template_id`, `template_version`, `template_digest` and, when the
template has a stewardship block, `template_status` in its metadata. That metadata is a label, not sealed into the chain hash; the perimeter is
sealed and is what the token issuer enforces. Templates only fill in existing
`create_mandate` arguments: existing mandates and their hashes are unchanged. They are a
Python API for now (no MCP tool lists them yet). Like every perimeter, the template
holds only if the agent cannot call `create_mandate` itself (see the deployment rule
above). See `docs/templates/agent-sante-rgpd.md`,
`docs/templates/agent-rh-recrutement.md`, `docs/templates/agent-credit.md`,
`docs/templates/agent-assurance-sante-vie.md` and `docs/templates/agent-support-client.md`.

Each template published here is a provisional sector baseline. Its `stewardship` block
says so (status `provisional` until a body of the sector takes it over, who holds it,
the practitioner reviewers recorded: none so far); the block is part of the template
digest and its status is copied into the mandate metadata as `template_status`. The
template's risk classes are minimum thresholds (for `agent-sante-rgpd`, version 1.2.0:
an order token lives at most 30 seconds and asks for a registry re-check;
`agent-rh-recrutement` 1.0.0, `agent-credit` 1.0.0 and `agent-assurance-sante-vie` 1.0.0 set
none, since none of their allowed actions is irreversible; `agent-support-client` 1.0.0 sets
none either, and a mandate may add one for `commercial_gesture.grant`):
`create_mandate_kwargs(risk_classes=[...])` may tighten them or add classes, and refuses
with a `ValueError` anything that would loosen them.

When a body (committee, board) authorized the agent, the mandate can record its decision
(`organ_decision`: body, title, date, optional reference, designated persons or roles);
the health template accepts it, `create_mandate` seals it into the chain hash (root
mandates with a closed list of allowed actions only), and `verify_mandate` and
`get_proof` return it. Mandates without it keep their exact hash.

### Third-party verification: the receiver checks the mandate alone

An agent can show whoever receives it (a seller, a hospital, an insurer) a signed
**mandate attestation** (`issue_mandate_attestation`). The receiver checks it alone,
offline, with the registry's public key fetched once (`get_registry_public_key`): no
account, no call to the registry. The attestation states that the mandate exists, who
granted it (and whether the principal signed it; with `include_principal_payload` the
receiver re-checks that signature itself), the agent, the scope and structured perimeter, the expiry, and that the
mandate and every mandate above it were active when the attestation was issued.

```bash
python -m amr.verify_attestation attestation.jws --public-key registry.pub --audience seller:acme
# registry.pub: the PEM (or the JSON) returned by get_registry_public_key
# {"valid": true, "reason": "ok", "attestation": {"principal_id": "...", "perimeter": {...}, ...}}
```

What it does not prove: that the mandate is still active *now*. An attestation lives
at most `AMR_ATTESTATION_LIFETIME_SECONDS` (default 15 minutes) and never outlives the
mandate or a parent; a revocation made after issuance reaches an offline receiver only
when the attestation expires. It is a bearer document: the receiver must make sure it
is dealing with the agent named in `agent_id`. Pass `audience` to address it to one
receiver. Mandate `metadata` is not disclosed unless `include_principal_payload` is
set (it is inside the signed bytes). The registry trusts its own database: protect the
file. Existing mandates and their hashes are unchanged; issuances are logged in a
new append-only table, `issued_attestations` (schema v5). See
`docs/mandate-attestation-spec.md`.

### Public registry: a verification point the operator hosts (no account for the receiver)

AMR runs over stdio next to each operator, so nobody else can query it. The public
registry is a separate, read-only verification point that each operator hosts on its own
domain (this repository deploys none, and mandatia.eu hosts none): the operator exports a **signed
snapshot** of the registry, and a small WSGI application (standard library only)
serves it. A receiver checks a mandate identifier or pastes an attestation, in a
browser (HTML) or from a script (JSON), with no account.

```bash
python -m amr.public_registry export --out amr_public_registry.jws   # read-only, signed EdDSA
python -m amr.public_registry serve --export amr_public_registry.jws --public-key registry.pub
curl http://127.0.0.1:8080/mandates/<mandate-id>
# {"status": "active" | "revoked" | "expired" | "cut_by_parent" | ..., "verification_ms": 0.2, ...}
```

The snapshot holds, per mandate, the agent, a SHA-256 reference of the principal (never
the identifier in clear), the perimeter, dates, recorded status, revocation date and
chain hash; never the scope text, legal basis, metadata or revocation reason. The
application verifies the snapshot with the pinned registry key before serving it
(and serves it raw at `/snapshot` for receivers who verify it themselves; trust in
the JSON answers is trust in whoever runs the app),
has no write path, keeps no log and never reads the client's address. Every result
gives the snapshot date and the time the verification took. Limit: a revocation made
after the snapshot shows only at the next export; set
`AMR_PUBLIC_SNAPSHOT_MAX_AGE_SECONDS` to refuse answers from an older snapshot. Deployment and domain are the
operator's step. Existing mandates and their hashes are unchanged; no schema change.
See `docs/public-registry-spec.md`.

---

## Vision: from registry to enforcement

AMR started as a **mandate registry** — it stores, verifies, and audits mandates. This is necessary but not sufficient.

The problem: if the mandate check is a voluntary call, agents skip it. The system degrades to advisory compliance within weeks of real-world deployment.

AMR now provides **structural enforcement**: it is the layer that issues execution authorizations (`issue_action_token`). No valid mandate → no authorization → no action possible. The system refuses to work without the mandate — not because someone recommends checking, but because the receiver accepts no action without a token the registry signed.

| Layer | What it does | Status |
|---|---|---|
| **Registry** | Store, verify, audit mandates. SHA-256 chain. MCP native. | ✅ Live |
| **Enforcement** | Mandate-gated execution authorization (`issue_action_token`, `check_action_token`). No mandate = no action. | ✅ Live |
| **Ecosystem** | AMR authorizes *before* the action. Certification proxies prove what happened *during*. | Compatible today |

---

## Quick Start

```bash
git clone https://github.com/JC7333/amr.git
cd amr
uv sync
uv run amr
```

### Claude Desktop Integration

Add AMR to your Claude Desktop config file:

**Location:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "amr": {
      "command": "uv",
      "args": ["--directory", "C:\\dev\\amr", "run", "amr"]
    }
  }
}
```

Restart Claude Desktop. All AMR tools will be available immediately.

---

## Tools

### `create_mandate`

Register a new mandate: the written authorization a principal (a person or a body) gives for an AI agent to act on its behalf.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `principal_id` | str | Principal granting the mandate. E.g. `"user:audric"` |
| `agent_id` | str | Agent receiving authorization. E.g. `"agent:korvex-advisor-v1"` |
| `scope` | str | What the agent is authorized to do |
| `legal_basis_regulation` | str | The act that gives the signer the power to authorize: delegation of authority, body decision, contract. E.g. `"Delegation of authority"` |
| `legal_basis_article` | str | Section, item or clause of that act. E.g. `"Section 2"` |
| `duration_hours` | float | Duration in hours (max 8760 = 1 year) |
| `legal_basis_jurisdiction` | str | Jurisdiction code (default `"EU"`) |
| `parent_mandate_id` | str \| null | UUID of parent mandate for delegation chains (parent must allow delegation) |
| `metadata` | dict | Optional string key-value pairs for annotations |
| `allowed_actions` | list[str] \| null | Action types the agent may request: `"invoice.pay"`, `"invoice.*"` or `"*"` |
| `forbidden_actions` | list[str] \| null | Action types never allowed (win over `allowed_actions`). E.g. `["agent.create"]` |
| `delegation_allowed` | bool | Whether the agent may grant sub-mandates (default `false`) |
| `max_delegation_depth` | int \| null | With `delegation_allowed`: how many levels of sub-mandates may exist below this mandate, 1 to 16 (`1` = the agent may delegate, its sub-agents may not). A deeper sub-mandate is refused with `delegation_depth_exceeded`; every ancestor's limit is checked. Absent: no limit from this mandate. Added to the sealed perimeter only when set, so existing mandates keep their hash. The limit is sealed with the mandate and checked each time a sub-mandate is created below it (a sub-mandate cannot declare more levels than its ancestors leave); it is not re-checked when a token is issued, and it binds only chains that declare their parent: the principal signature is what stops an agent from opening a separate root. Perimeters with this key cannot be read by older AMR versions. |
| `max_amount` | str \| null | Ceiling per action, decimal string. E.g. `"500"` |
| `currency` | str | ISO 4217 code of `max_amount` (default `"EUR"`) |
| `amount_actions` | list[str] \| null | Actions that must carry an `amount` under the ceiling (empty: all) |
| `period_max_amount` | str \| null | Cumulative ceiling over `period_days`, for this mandate and all its sub-mandates, decimal string. E.g. `"2000"` |
| `period_days` | int \| null | Rolling window of `period_max_amount`, 1 to 366 days (required with it). E.g. `30` |
| `risk_classes` | list[dict] \| null | Classes `{name, actions, max_token_seconds, registry_check?}` bounding the token lifetime of the actions they reach, here and in every sub-mandate; `registry_check: true` asks the receiver to re-check with `check_action_token`. E.g. `[{"name": "irreversible", "actions": ["invoice.pay"], "max_token_seconds": 30, "registry_check": true}]` |
| `principal_signature` | str \| null | Principal's base64url Ed25519 signature of the `prepare_mandate_signature` payload (required once the principal has a registered key) |
| `signed_at` | str \| null | ISO 8601 timestamp with timezone placed in the signed payload (within 15 minutes of the registry clock) |

**Returns:**
```json
{
  "status": "created",
  "mandate_id": "550e8400-e29b-41d4-a716-446655440000",
  "principal_id": "user:audric",
  "agent_id": "agent:korvex-advisor-v1",
  "scope": "Compare and recommend financial products to retail clients",
  "perimeter": null,
  "parent_mandate_id": null,
  "principal_signature": null,
  "expires_at": "2026-05-13T20:00:00+00:00",
  "chain_hash": "a3f5c2d1e8b9..."
}
```

`perimeter` holds the structured perimeter when one was given (it is sealed into
`chain_hash`). Perimeter and delegation errors return `{"error": "...", "code": "..."}`
with a stable code: `perimeter_invalid`, `parent_mandate_not_found`,
`parent_mandate_<status>`, `parent_mandate_expired`, `delegation_not_allowed`,
`delegator_mismatch`, `sub_mandate_requires_perimeter`, `perimeter_exceeds_parent`,
`limit_exceeds_parent`, `expires_after_parent`. A broken chain above the parent
returns `parent_mandate_<status>`, `parent_mandate_expired` or
`delegation_chain_too_deep` (more than 16 levels).

`principal_signature` is `{"key_id", "signed_at"}` for a signed mandate. Signature
errors: `principal_signature_required`, `principal_signature_incomplete`,
`principal_key_not_registered`, `signed_at_invalid`, `principal_signature_stale`,
`principal_signature_invalid`, `principal_signature_replayed`.

---

### `register_principal_key`

Register a principal's Ed25519 public key, once, with a proof of possession.

| Parameter | Type | Description |
|---|---|---|
| `principal_id` | str | The principal. E.g. `"user:audric"` |
| `public_key` | str | Raw 32-byte public key, base64url |
| `proof_signature` | str | Signature of `{"context":"amr.principal_key.v1","principal_id":...,"public_key":...}` (canonical JSON) |

Returns `{"status": "registered", "principal_id", "key_id", "registered_at", "chain_hash",
"domain_proof"}`. `domain_proof` is null, except for a `did:web:<domain>` principal: its key
is accepted only if `https://<domain>/.well-known/did.json` lists it (needs
`AMR_DID_WEB_RESOLVE=1`), and `domain_proof` holds `did_document_url`,
`did_document_sha256` and `verified_at`. See `docs/principal-signature-spec.md`,
section 1 bis.

---

### `prepare_mandate_signature`

Same arguments as `create_mandate` (plus optional `signed_at`, default now). Writes
nothing; returns `{"payload", "payload_b64url", "signed_at"}`: the exact bytes the
principal signs before calling `create_mandate`.

---

### `prepare_mandate_pdf`

Same arguments as `prepare_mandate_signature`. Writes nothing; returns the mandate as a
PDF for the principal to read and sign with its own signature tool (for example a PAdES
signature): `{"pdf_base64", "filename", "pdf_sha256", "attachment_name",
"payload_sha256", "payload", "payload_b64url", "signed_at"}`. The PDF carries the exact
payload of `prepare_mandate_signature` as the attached file `amr-mandate.json` and prints
its SHA-256 on every page. The same arguments and `signed_at` always give the same PDF.
The registry does not sign this PDF. The mandate is still accepted on the principal's
Ed25519 signature of the same payload, with `signed_at` within
`AMR_PRINCIPAL_SIGNATURE_MAX_AGE_SECONDS` (default 900 seconds) of the registry clock;
generate, sign and register within that window (see `docs/principal-signature-spec.md`,
section 2 bis). Once the principal has signed the PDF itself, record it with
`attach_signed_mandate_pdf`.

---

### `attach_signed_mandate_pdf`

`attach_signed_mandate_pdf(mandate_id, signed_pdf_base64)`, after `create_mandate`.
Checks, offline, the PDF of `prepare_mandate_pdf` once the principal signed it with its
own tool (PAdES, for example with a qualified certificate): the file starts with the
exact mandate PDF and its attached content is this mandate; what was appended only adds
signatures; every signature verifies, covers the document and its certificate chains to
a root of `AMR_PDF_TRUST_ROOTS_PATH` (a PEM file the operator chooses) at the time of the
check. The signed file, the signers (names, organisation identifier, qualified
certificate statements) and the SHA-256 of the roots used are recorded, chained, and
shown in `get_proof` (`pdf_signatures`, `chain_integrity.pdf_signatures_intact`).
Without `AMR_PDF_TRUST_ROOTS_PATH`, nothing is accepted (`pdf_trust_roots_missing`).

It does not read the EU trusted lists, does not check certificate revocation
(`revocation_checked: false`; no network call) and does not compare the signer with the
principal: `declared_level` (`qualified_on_qscd`, `qualified`, `not_qualified`) is what
the certificate declares under the operator's roots. See
`docs/mandate-pdf-signature-spec.md`.

---

### `verify_mandate`

Check whether an AI agent has a currently active, non-expired mandate (for a
sub-mandate, every mandate above it must be active and unexpired too). It does not
check the action against the perimeter: `issue_action_token` does.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `agent_id` | str | Agent to check. E.g. `"agent:korvex-advisor-v1"` |
| `action` | str | Action the agent wants to perform |
| `context` | str | Optional context for audit logging |

**Returns:**
```json
{
  "authorized": true,
  "mandate_id": "550e8400-e29b-41d4-a716-446655440000",
  "reason": "Active mandate found",
  "scope": "Compare and recommend financial products to retail clients",
  "perimeter": null,
  "parent_mandate_id": null,
  "expires_at": "2026-05-13T20:00:00+00:00"
}
```

---

### `issue_action_token`

The hard-stop. Before acting, the agent asks the registry for a signed token (JWS, EdDSA).
It is issued only if the mandate and every mandate above it are active and unexpired, and
the action fits the perimeter at every level: allowed, not forbidden, under the amount
ceiling per action and over the period. No token, no action: the receiver checks the token
offline with the registry's public key, or with `check_action_token` when it must know the
mandate still stands at the moment it acts.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `mandate_id` | str | UUID of the mandate the agent invokes |
| `agent_id` | str | Must be the mandate's `agent_id` |
| `action` | str | Description of the action. E.g. `"Pay invoice FAC-001"` |
| `audience` | str | Where the token will be presented. E.g. `"platform:payments"` |
| `action_type` | str \| null | Dotted type checked against the perimeter (required under one). E.g. `"invoice.pay"` |
| `action_metadata_json` | str | JSON object as a string. An amount is a decimal string: `'{"amount": "120", "currency": "EUR"}'` |
| `lifetime_override_seconds` | int \| null | Shorter lifetime (never longer than the default, the mandate or a risk class) |

**Returns** (issued):
```json
{"token": "eyJhbGciOiJFZERTQSIs...", "jti": "ab2331ad-...", "expires_at": "2026-11-09T20:17:02+00:00", "key_id": "f37c94e3eb51d1d4"}
```

**Returns** (refused):
```json
{"denied": true, "reason": "action_out_of_scope", "detail": "amount_above_limit:500 EUR", "mandate_id": "...", "refused_by": "..."}
```

Other reasons: `mandate_status_revoked`, `mandate_expired`, `agent_mismatch`,
`action_type_required`, `invalid_input`; perimeter details include `forbidden:<type>`,
`not_allowed:<type>`, `amount_required`, `currency_mismatch:<code>`. See
[`docs/token-issuance-spec.md`](https://github.com/JC7333/amr/blob/main/docs/token-issuance-spec.md).

---

### `log_action`

Log an agent action under an active mandate. Cryptographically chained to previous actions.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `mandate_id` | str | UUID of the mandate under which the action was performed |
| `action` | str | Description of the action performed |
| `evidence` | str | Optional reference or evidence. E.g. `"email:msg_abc123"` |
| `result` | str | Optional outcome. E.g. `"Delivered"` |

**Returns:**
```json
{
  "status": "logged",
  "action_id": "7f3e9b2a-...",
  "mandate_id": "550e8400-...",
  "action": "Generated investment recommendation for Product X",
  "chain_hash": "c8d7e6f5..."
}
```

The mandate must be active, not revoked and not expired. For a sub-mandate, so must
every mandate above it: revoke or let expire a parent and its whole branch stops
logging. The refusal then says why and which mandate broke the chain:
`{"error": "...", "reason": "parent_mandate_revoked", "refused_by": "<parent id>"}`
(also `parent_mandate_expired`, `parent_mandate_<status>`, `parent_mandate_not_found`,
`delegation_chain_too_deep`).

---

### `revoke_mandate`

The principal's stop button. Records a **final** revocation of a mandate, with the
reason the principal gives. Append-only: a chained row in `mandate_revocations` and a
`revoked` mandate event; the mandate row is not modified and its hash does not change.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `mandate_id` | str | UUID of the mandate to revoke |
| `reason` | str | Why, as it will be recorded (1 to 500 characters) |
| `principal_signature` | str \| null | Ed25519 signature of the revocation payload (required if the principal has a registered key) |
| `signed_at` | str \| null | The `signed_at` placed in the payload |

Only the mandate's own principal revokes it (for a sub-mandate, the agent that
delegated it). Same signature policy as `create_mandate`; build the exact bytes to sign
with `prepare_revocation_signature(mandate_id, reason, signed_at=None)`.

**Effect, as soon as it returns:** `issue_action_token` and `issue_mandate_attestation`
refuse the mandate (`mandate_status_revoked`) and every sub-mandate below it
(`parent_mandate_revoked`);
`verify_mandate` no longer returns it; no sub-mandate can be created under it;
`log_action` refuses it and every sub-mandate below it; `get_proof` and `export_insurer_dossier` report it. Tokens already issued cannot be
called back and stay valid until their `exp`: the response gives their number and the
last expiry, unless the receiver re-checks the token with `check_action_token` when it
acts (see below). Mandate attestations already issued also stay valid until their `exp`
(15 minutes by default) for a receiver that checks them offline: the response gives
their number and last expiry too, for the mandate and its sub-mandates.

**Returns:**
```json
{
  "status": "revoked",
  "mandate_id": "550e8400-e29b-41d4-a716-446655440000",
  "principal_id": "org:clinic",
  "reason": "agent exceeded its order limit",
  "revoked_at": "2026-10-23T20:30:01.123456+00:00",
  "principal_signature": null,
  "chain_hash": "a3f1...",
  "outstanding_tokens": {"still_valid": 1, "last_expires_at": "2026-10-23T20:34:12+00:00"},
  "outstanding_attestations": {"still_valid": 0, "last_expires_at": null}
}
```

A token lives at most `AMR_TOKEN_LIFETIME_SECONDS` (300 s by default) and never past the
expiry of its mandate or of any mandate above it in the delegation chain, nor beyond
the shortest risk class (`risk_classes`) that reaches its action type in that chain.
The caller's `lifetime_override_seconds` can only shorten it. Breaking change for callers that asked
for a token longer than the default: they now get the default. After a revocation, the
window in which an already issued token still works is therefore at most that lifetime,
whatever the depth of the chain. See `docs/revocation-spec.md`.

---

### `contest_action`

The agent has already acted, and the principal disputes the act. Revoking the mandate
stops what comes next; `contest_action` records that one past act, logged with
`log_action`, is contested, when, why, and by whom. Append-only: a chained row in
`action_contests` (one per action; it cannot be withdrawn or edited) and an
`action_contested` mandate event. The action log, the mandate and every hash already
recorded stay as they are.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `mandate_id` | str | UUID of the mandate the action was logged under |
| `action_id` | str | `action_id` returned by `log_action` |
| `reason` | str | Why the act is contested (1 to 500 characters) |
| `response_days` | int | Days until `respond_by` (1 to 365), chosen by the operator |
| `contested_by` | str \| null | The contesting principal; default: the mandate's principal |
| `principal_signature` | str \| null | Ed25519 signature of the contest payload (required if the contesting principal has a registered key) |
| `signed_at` | str \| null | The `signed_at` placed in the payload |

`contested_by` may be the mandate's principal or the principal of any mandate above it
in the delegation chain (an organization disputes what a sub-agent did), whatever the
status of those mandates. Same signature policy as `create_mandate` and
`revoke_mandate`; build the bytes with `prepare_contest_signature` (same arguments,
plus `signed_at=None`).

`respond_by = contested_at + response_days` is the operator's own deadline, for
example the delay its counsel gives before keeping or using what was ordered could be
read as accepting it. **AMR computes no legal deadline and asserts none.** A contest
does not undo the act and does not revoke the mandate: call `revoke_mandate` for that.

**Returns:**
```json
{
  "status": "contested",
  "mandate_id": "550e8400-e29b-41d4-a716-446655440000",
  "action_id": "0b6f7c1e-3d0a-4c55-9a43-5d1f1f0e2a10",
  "action_chain_hash": "9c2e...",
  "contested_by": "org:clinic",
  "reason": "order placed above the agreed quantity",
  "response_days": 14,
  "contested_at": "2026-11-01T21:30:00+00:00",
  "reminder": {"respond_by": "2026-11-15T21:30:00+00:00", "days_left": 14, "deadline_passed": false},
  "principal_signature": null,
  "chain_hash": "5be0..."
}
```
Errors (`code`): `invalid_input`, `mandate_not_found`, `action_not_found` (also when
the action belongs to another mandate), `contester_not_in_chain`,
`action_already_contested`, and the principal signature codes of `revoke_mandate`.

**Reminder:** `list_action_contests(mandate_id=None, contested_by=None,
due_within_days=None)` (read-only; give `mandate_id`, `contested_by` or both) returns
the contests, nearest `respond_by` first, each with `reminder.days_left` (negative once
passed) and `reminder.deadline_passed`. Call it on a schedule, for example each morning
with `due_within_days=3`. `get_proof` lists the contests of a mandate in
`action_contests` and re-checks them in `chain_integrity.contests_intact`. See
[`docs/action-contest-spec.md`](https://github.com/JC7333/amr/blob/main/docs/action-contest-spec.md).

---

### `check_action_token`

For the receiver of an agent's action: re-check a token with the registry at the moment
of acting, before an irreversible step. Required when the token carries
`amr_registry_check: true` (a risk class with `registry_check`); possible for any token.
Read only.

| Parameter | Type | Description |
|---|---|---|
| `token` | str | The JWS returned by `issue_action_token` |
| `audience` | str | Who you are; must equal the token's `aud` |
| `expected_action_hash` | str \| null | SHA-256 of the canonical action you are about to perform; must equal `amr_action_hash` |
| `max_token_age_seconds` | int \| null | Your own, stricter bound (1 to 86400): refuse a token issued longer ago. Never extends `exp` |

It verifies the signature (EdDSA only, this registry's key), `iss`, `aud`, `exp`, `nbf`,
that the token is one the registry issued, then that the mandate and every mandate
above it are still active, not revoked and not expired.

```json
{"valid": true, "reason": "ok", "jti": "...", "mandate_id": "...", "agent_id": "agent:billing",
 "action_type": "invoice.pay", "registry_check_required": true,
 "expires_at": "2026-10-29T21:30:30+00:00", "checked_at": "2026-10-29T21:30:12.400000+00:00"}
```
```json
{"valid": false, "reason": "mandate_status_revoked", "jti": "...", "mandate_id": "...",
 "checked_at": "2026-10-29T21:30:14.100000+00:00"}
```

The registry opens its database read-only and writes nothing for a check, and the
answer is not signed: it is not evidence that anyone checked. Call the registry over
your own channel; never accept a check result relayed by the agent whose token it is.
Once a mandate with `registry_check` exists, an older AMR version cannot read its
perimeter (it fails closed). See `docs/token-issuance-spec.md`, Registry Check at
Execution.

---

### `get_proof`

Generate a complete **Proof Pack** — a full audit bundle for a mandate including all actions and cryptographic chain verification.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `mandate_id` | str | UUID of the mandate to prove |
| `format` | str | Output format (currently `"json"`) |

**Returns:**
```json
{
  "proof_pack_version": "0.1.0",
  "generated_at": "2026-04-13T18:00:00+00:00",
  "mandate": { "...": "full mandate details" },
  "delegation_chain": {"broken": false, "reason": null, "refused_by": null},
  "actions": [ "...list of all logged actions..." ],
  "events": [],
  "action_contests": [],
  "chain_integrity": {
    "actions_chain_valid": true,
    "principal_signature_valid": null,
    "revocation_signature_valid": null,
    "contests_intact": true,
    "total_actions": 5,
    "total_events": 0
  },
  "compliance_notes": {
    "ai_act_art26": "This Proof Pack documents the mandate chain for AI Act Art.26 compliance.",
    "retention": "Logs must be retained for minimum 6 months per AI Act Art.26(6)."
  }
}
```

`mandate.principal_signature` holds the principal's signature, public key, the key's
proof of possession and the signed bytes (or `null`); `principal_signature_valid`
re-checks them against the stored mandate. It is `false` if the signature does not
match, or if it is missing although the principal had a key when the mandate was
created; `null` for a mandate whose principal had no key then.

Once `revoke_mandate` has run, `mandate.status` reads `"revoked"` (the stored value
stays in `mandate.stored_status`) and `mandate.revocation` holds `revoked_at`, `reason`, the principal's signature
of the revocation (or `null`) and its chain hash; `revocation_signature_valid` re-checks
that signature against the principal's key (`null` when there is nothing to check).

`delegation_chain` says whether the chain above a sub-mandate still holds:
`{"broken": true, "reason": "parent_mandate_revoked", "refused_by": "<parent id>"}`
when a mandate above it is revoked, expired, not active or missing (the sub-mandate's
own `mandate.status` does not change: the cut is above it);
`{"broken": false, "reason": null, "refused_by": null}` otherwise, and always for a root
mandate.

---

### `issue_mandate_attestation`

| Parameter | Type | Description |
|---|---|---|
| `mandate_id` | str | UUID of the mandate to attest |
| `agent_id` | str | Must match the mandate's agent |
| `audience` | str \| null | Optional receiver it is addressed to |
| `lifetime_seconds` | int \| null | Optional shorter lifetime (never longer than the configured maximum) |
| `include_principal_payload` | bool | Also carry the principal's signature and signed bytes (discloses `metadata`); default `false` |

Returns `{"attestation", "jti", "issued_at", "expires_at", "key_id", "issuer"}`, or
`{"denied": true, "reason", "mandate_id"}`, for example `mandate_not_found`,
`agent_mismatch`, `mandate_status_<status>`, `mandate_status_revoked`, `mandate_expired`,
`parent_mandate_<status>`, `parent_mandate_revoked`, `principal_signature_invalid`, with `refused_by` when a
parent is the cause (full list in `docs/mandate-attestation-spec.md`).

### `get_registry_public_key`

No parameters. Returns `{"issuer", "key_id", "algorithm": "EdDSA", "public_key_pem",
"public_key_jwk"}`: what a receiver needs to verify attestations offline.

### `export_insurer_dossier`

Export a **signed dossier** of one mandate over a period: the piece an insurer or an
auditor asks for about an AI agent. Read-only; facts from the registry only.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `mandate_id` | str | UUID of the mandate |
| `period_start` | str \| null | ISO 8601 date-time start (naive = UTC; a bare date is refused); defaults to the mandate's creation |
| `period_end` | str \| null | ISO 8601 date-time end (naive = UTC; a bare date is refused); defaults to now |
| `format` | str | `"json"` (default) or `"html"` to also get a printable page |

**The dossier holds:** the mandate (principal, agent, scope, declared legal basis,
dates); its perimeter (allowed and forbidden action types, right to delegate, amount
limit); whether it is in force at generation time, and why not (`mandate_revoked`,
`mandate_expired`, or a broken chain above it such as `parent_mandate_revoked`); its
sub-mandates, each with depth, perimeter, in-force status and the number of actions it
logged in the period (a cut mandate cuts its whole branch); the actions the mandate's
own agent logged in the period; the status events and action tokens of the period, for
the mandate and its sub-mandates; the integrity checks (action log chain, principal
signature, last chain hash); and a fixed list of the dossier's limits (for example:
refused token requests are not recorded, so the dossier lists issued tokens, not
blocked actions).

**Returns:**
```json
{
  "dossier": { "dossier_version": "1.0", "period": {}, "mandate": {}, "status": {},
               "integrity": {}, "sub_mandates": [], "events": [], "actions": [],
               "tokens": [], "limits": [] },
  "dossier_sha256": "hex SHA-256 of the canonical dossier",
  "signature": { "jws": "...", "algorithm": "EdDSA", "key_id": "...",
                 "public_key_pem": "..." },
  "html": "only when format is \"html\""
}
```

The signature is a JWS (RFC 7515, EdDSA / Ed25519, same registry key as action tokens)
whose payload is the canonical JSON of the dossier. Verify it offline:

```python
from amr.proof.insurer_dossier import verify_dossier

dossier = verify_dossier(jws, registry_public_key_pem)  # raises if anything is off
```

The export never creates a signing key: on a registry without one it returns an error.
Get the registry public key out of band: `public_key_pem` in the export is a
convenience, and a dossier that carries its own key proves nothing about who signed
it. The HTML page is a self-contained print view (no external resources; print to PDF
from the browser) that shows the dossier's SHA-256 and the key id; only the JSON
signature is proof. See `docs/insurer-dossier-spec.md`.

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PRINCIPAL                                   │
│              (user:audric, org:acme-corp)                           │
└──────────────────────────┬──────────────────────────────────────────┘
                           │  create_mandate()
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    MANDATE (SHA-256 chained)                        │
│  id · principal · agent · scope · legal_basis · expires_at         │
│  chain_hash = SHA256(mandate_data + prev_hash)                      │
└──────────────────────────┬──────────────────────────────────────────┘
                           │  verify_mandate() → authorized: true
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          AGENT                                      │
│              (agent:korvex-advisor-v1)                              │
└──────────────────────────┬──────────────────────────────────────────┘
                           │  log_action() × N
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                ACTION LOG (append-only, SHA-256 chained)            │
│  action_1 ──hash──▶ action_2 ──hash──▶ action_3 ──hash──▶ ...     │
│  Each action links to the previous via chain_hash                   │
└──────────────────────────┬──────────────────────────────────────────┘
                           │  get_proof()
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       PROOF PACK (JSON)                             │
│  mandate + actions + chain_integrity + compliance_notes             │
│  Ready for an audit, an insurer, or archival                        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Security

1. **Pydantic v2 validation** — All tool inputs are validated before any DB interaction. Unknown fields are rejected (`extra="forbid"`). Duration, string lengths, and UUID formats are enforced at the model layer.

2. **Parameterized SQL only** — Every database query uses `?` placeholders. No string interpolation or f-strings in SQL. Enforced by `ruff` S608 rule on every commit.

3. **Append-only tables** — The `mandates` and `action_logs` tables are never `UPDATE`d or `DELETE`d. The audit trail is immutable by design. Status changes use a separate `mandate_events` table.

4. **SHA-256 cryptographic chain** — Each mandate and each action log entry is linked to the previous one via a SHA-256 hash (git-style). Any tampering invalidates all subsequent hashes, making the trail tamper-evident.

5. **stdio transport only** — AMR runs as a local MCP server over stdio. No listening port, no inbound network exposure, no outbound HTTP from tools, with two opt-in exceptions: `report_issue` sends one HTTPS request to the GitHub API, only when the operator has set `AMR_ISSUE_TOKEN`; `register_principal_key` reads the DID document of a `did:web` principal, only when the operator has set `AMR_DID_WEB_RESOLVE=1`. The attack surface is minimal.

6. **One profile per side** — `AMR_TOOL_PROFILE` keeps the principal's tools (grant, sign, revoke) away from the agent's server, so an agent cannot authorize itself.

---

## Regulatory Context

| Regulation | Relevance to AMR |
|---|---|
| **EU AI Act Art.26** | Deployers of high-risk AI systems must use them as instructed, assign human oversight and keep the logs the system generates. AMR records the mandate behind each agent and its actions, as evidence for that oversight. Applies from **2 December 2027** (Annex III systems) and **2 August 2028** (Annex I systems), [Regulation (EU) 2026/1744](https://eur-lex.europa.eu/eli/reg/2026/1744/oj). |
| **EU AI Act Art.26(6)** | The logs a high-risk system generates must be kept for at least six months. AMR's append-only SQLite database and Proof Pack export support this requirement. |
| **eIDAS 2.0** | Electronic mandates for AI agents acting on behalf of natural or legal persons. AMR's mandate chain maps to the eIDAS electronic delegation trust framework. |
| **Fines** | Non-compliance with Article 26 can be fined up to **€15 million or 3% of worldwide annual turnover**, whichever is higher ([Art. 99(4)](https://eur-lex.europa.eu/eli/reg/2024/1689/oj); for SMEs and start-ups, whichever is lower, Art. 99(6)). |

---

## Roadmap

| Status | Features |
|---|---|
| **Shipped** | Mandate registry · SHA-256 chain · Proof Pack JSON · structured perimeters · sub-mandates and delegation chains · revocation · contested actions · signed action tokens (enforcement) and check at execution · offline mandate attestations · signed insurer dossier (JSON and printable HTML) · principal signatures and did:web keys · read-only public registry · sector templates (health, recruitment, credit, life and health insurance, customer support) · MCP SDK v1 and v2 · PyPI package `mandatia` |
| **Planned** | PDF Proof Pack export · remote transport for MCP clients · PostgreSQL backend · multi-tenant support · REST API alongside MCP · eIDAS 2.0 qualified electronic signatures · cross-border mandate recognition · webhook notifications · dashboard and alerting |

---

## Development

```bash
# Install all dependencies including dev extras
uv sync --all-extras

# Run the full test suite
uv run pytest -v

# Run with short traceback on failure
uv run pytest -v --tb=short

# Lint and security check (src + tests)
uv run ruff check src/ tests/

# Auto-fix safe issues
uv run ruff check --fix src/ tests/

# Start the MCP server (stdio — normal to wait for input)
uv run amr
```

### Project Structure

```
src/amr/
├── config.py          # Settings via pydantic-settings (env prefix: AMR_)
├── server.py          # MCP server entrypoint (stdio transport; mcp 1.x or 2.x)
├── models/mandate.py  # Pydantic models: MandateCreate, Mandate, ActionLog
├── crypto/chain.py    # compute_hash() and verify_chain() — stdlib only
├── db/engine.py       # init_db(), get_db(), get_last_mandate_hash()
├── tools/
│   ├── create_mandate.py
│   ├── prepare_mandate_pdf.py   # the mandate as a PDF the principal signs itself
│   ├── attach_signed_mandate_pdf.py   # records that PDF once signed (PAdES, offline)
│   ├── verify_mandate.py
│   ├── log_action.py
│   ├── get_proof.py
│   ├── check_action_token.py          # receiver re-checks a token when it acts
│   ├── issue_mandate_attestation.py   # attestation + registry public key
│   ├── revoke_mandate.py
│   ├── contest_action.py   # contested acts and their response deadline (reminder)
│   ├── report_issue.py   # network call, opt-in (AMR_ISSUE_TOKEN)
│   └── export_insurer_dossier.py
├── attestation.py     # offline attestation verifier (no DB, no network)
├── did_web.py         # did:web key check, network opt-in (AMR_DID_WEB_RESOLVE)
├── mandate_pdf.py     # deterministic mandate PDF, payload attached (stdlib only)
├── pades.py           # offline check of a PAdES signature on that PDF (pyHanko)
├── verify_attestation.py  # python -m amr.verify_attestation
├── proof/insurer_dossier.py  # Signed insurer dossier: canonical form, JWS, print view
└── templates/         # Sector mandate templates (agent-sante-rgpd, agent-rh-recrutement, agent-credit, agent-assurance-sante-vie, agent-support-client)
tests/
├── conftest.py              # Isolated temp DB fixture (autouse)
└── test_*.py                # One file per tool or feature (`uv run pytest -q`)
```

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `AMR_DB_PATH` | `amr_mandates.db` | Path to the SQLite database file |
| `AMR_LOG_LEVEL` | `INFO` | Logging verbosity |
| `AMR_SERVER_NAME` | `Agent Mandate Registry` | MCP server display name |
| `AMR_TOOL_PROFILE` | `full` | Tools this server exposes: `principal`, `agent`, `receiver` or `full` (see Quickstart) |
| `AMR_SIGNING_KEY_PATH` | `amr_signing_key.pem` | Registry Ed25519 private key, created on first use; keep it out of version control |
| `AMR_TOKEN_ISSUER` | `amr://localhost` | `iss` of tokens and attestations; set it to an identifier of your registry (e.g. `https://registry.example.org`) so receivers can tell registries apart |
| `AMR_REQUIRE_PRINCIPAL_SIGNATURE` | `false` | Refuse every mandate not signed by its principal |
| `AMR_PRINCIPAL_SIGNATURE_MAX_AGE_SECONDS` | `900` | Allowed gap between `signed_at` and the registry clock |
| `AMR_ISSUE_TOKEN` | unset | GitHub token that lets `report_issue` file issues itself (fine-grained, Issues: write, one repository). Read from the process environment only, never from `.env`. Unset: no network call |
| `AMR_DID_WEB_RESOLVE` | unset | `1` lets `register_principal_key` read the DID document of a `did:web` principal (one HTTPS GET to that domain). Read from the process environment only, never from `.env`. Unset: `did:web` keys are refused |
| `AMR_PDF_TRUST_ROOTS_PATH` | unset | PEM file of the certificate authorities whose PDF signatures `attach_signed_mandate_pdf` accepts. Unset: no signed PDF is accepted |
| `AMR_ISSUE_REPOSITORY` | `JC7333/amr` | Repository `report_issue` files issues on (`owner/name`) |
| `AMR_ATTESTATION_LIFETIME_SECONDS` | `900` | Longest lifetime of a mandate attestation |
| `AMR_PUBLIC_EXPORT_PATH` | `amr_public_registry.jws` | Signed snapshot written by `python -m amr.public_registry export` and served by its app |
| `AMR_PUBLIC_KEY_PATH` | `amr_signing_key.pub` | Registry public key; the public registry app pins it to verify the snapshot |
| `AMR_PUBLIC_SNAPSHOT_MAX_AGE_SECONDS` | unset | Public registry: answer `snapshot_too_old` instead of a status past this age |

---

## License

Apache License 2.0 — See [LICENSE](https://github.com/JC7333/amr/blob/main/LICENSE) for full terms.

Free to use, including in commercial products.

---

> ⚠️ **Disclaimer:** AMR is a technical infrastructure tool. It does not constitute legal advice. Compliance with EU AI Act, eIDAS 2.0, or any other regulation remains the responsibility of the operator. Consult qualified legal counsel for your specific regulatory obligations.
