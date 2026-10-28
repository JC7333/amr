# Agent Mandate Registry (AMR)

> **The legal mandate layer for AI agents.**

AMR is an open-source [MCP](https://modelcontextprotocol.io/) server that registers, verifies, and audits legal mandates authorizing AI agents to act on behalf of principals. It provides a cryptographically chained audit trail designed for compliance with **EU AI Act Art.26** (effective August 2026) and **eIDAS 2.0**.

---

## Quickstart for agents

This section is written so that an AI agent (Claude Code, Cursor, any MCP client) can
install AMR and reach a first verified mandate on its own: no account, no email, no
person to ask. Everything runs on your machine; AMR makes no network call (the one
exception, `report_issue`, is off until the operator sets `AMR_ISSUE_TOKEN`).

**1. Run the server** (needs [uv](https://docs.astral.sh/uv/)). The `--with "mcp<2"`
part is required today: AMR is written for version 1 of the MCP Python SDK and a fresh
install without it picks version 2, which fails at start with
`No module named 'mcp.server.fastmcp'`.

```bash
uvx --from git+https://github.com/JC7333/amr --with "mcp<2" amr
```

AMR is not published on PyPI: `uvx amr` would install a different project. Use the
command above, or clone the repository and run `uv sync && uv run amr`.

**2. Declare it in your MCP client.**

Claude Code:

```bash
claude mcp add amr -- uvx --from git+https://github.com/JC7333/amr --with "mcp<2" amr
```

Cursor (`.cursor/mcp.json`) and other clients that read an `mcpServers` object:

```json
{
  "mcpServers": {
    "amr": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/JC7333/amr", "--with", "mcp<2", "amr"],
      "env": {
        "AMR_DB_PATH": "/absolute/path/amr_mandates.db",
        "AMR_SIGNING_KEY_PATH": "/absolute/path/amr_signing_key.pem",
        "AMR_PUBLIC_KEY_PATH": "/absolute/path/amr_signing_key.pub"
      }
    }
  }
}
```

Set the three paths: by default AMR writes its database and its signing key in the
current directory of the client. Keep the `.pem` private key out of version control.

**3. Reach a first verified mandate.** The tools, in the order an agent uses them:

1. `create_mandate`: register who authorizes what (`principal_id`, `agent_id`, `scope`,
   `legal_basis_regulation`, `legal_basis_article`, `duration_hours`; add
   `allowed_actions` / `forbidden_actions` for a perimeter; only `issue_action_token`
   enforces it).
2. `verify_mandate(agent_id, action)`: `authorized: true` while the agent has an active
   mandate. It does not check `action` against the perimeter; `issue_action_token` does.
3. `log_action(mandate_id, action)`: append an entry to the hash-chained journal.
4. `issue_mandate_attestation` + `get_registry_public_key`: a signed document a third
   party checks offline with `python -m amr.verify_attestation`.
5. `revoke_mandate(mandate_id, reason)`: the stop button; `verify_mandate` then answers
   `authorized: false`. Tokens and attestations already issued stay valid until they
   expire.
6. `get_proof(mandate_id)`: the full audit bundle (mandate, actions, integrity).
7. `report_issue(title, description, version, context)`: report a problem with AMR
   itself. Without `AMR_ISSUE_TOKEN` it makes no network call and returns a pre-filled
   link to open; with it, it files the issue on GitHub. See
   [`docs/report-issue-spec.md`](docs/report-issue-spec.md).

The same flow, runnable and checked by the test suite, is in
[`examples/quickstart_agent.py`](examples/quickstart_agent.py):

```bash
git clone https://github.com/JC7333/amr.git && cd amr && uv sync
uv run python examples/quickstart_agent.py   # prints every step, ends with "OK"
```

Machine-readable summaries for agents: [`AGENTS.md`](AGENTS.md) and [`llms.txt`](llms.txt).
To report a problem, call `report_issue` or open an issue at
https://github.com/JC7333/amr/issues (never paste real mandate contents or personal data
into it).

---

## Why AMR?

Modern AI agent infrastructure covers many concerns — but the legal mandate layer is missing:

| Concern | Existing tools | AMR |
|---|---|---|
| Infrastructure & orchestration | ✅ LangChain, AutoGen, CrewAI | — |
| Security & sandboxing | ✅ Docker, RBAC, network policies | — |
| Permission & access control | ✅ OAuth, IAM, API keys | — |
| Observability & tracing | ✅ OpenTelemetry, Langfuse | — |
| **Legal mandate & accountability** | ❌ **Not covered** | ✅ **AMR** |

**EU AI Act Art.26** (August 2026) requires operators of high-risk AI systems to maintain tamper-evident logs of agent mandates and actions. Non-compliance: fines up to **€30M or 6% global turnover**. AMR closes this gap.

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
  exact hash and tokens. Re-checking the registry at execution time for
  irreversible actions is not done yet.

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
for that `principal_id`. The registry does not check who registers a key (first
registration wins), so register each principal's key at onboarding, through the
principal's own channel. Mandates of principals without a key behave as before (same
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
the record, contact a patient itself, or create a sub-agent.

```python
from amr.templates import get_template

template = get_template("agent-sante-rgpd")
await create_mandate(..., **template.create_mandate_kwargs())
```

The mandate records `template_id`, `template_version` and `template_digest` in its
metadata. That metadata is a label, not sealed into the chain hash; the perimeter is
sealed and is what the token issuer enforces. Templates only fill in existing
`create_mandate` arguments: existing mandates and their hashes are unchanged. They are a
Python API for now (no MCP tool lists them yet). Like every perimeter, the template
holds only if the agent cannot call `create_mandate` itself (see the deployment rule
above). See `docs/templates/agent-sante-rgpd.md`.

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

---

## Vision: from registry to enforcement

AMR v0.1 is a **mandate registry** — it stores, verifies, and audits mandates. This is necessary but not sufficient.

The problem: if the mandate check is a voluntary call, agents skip it. The system degrades to advisory compliance within weeks of real-world deployment.

The roadmap leads to **structural enforcement**: AMR becomes the layer that issues execution authorizations. No valid mandate → no authorization → no action possible. The system refuses to work without the mandate — not because someone recommends checking, but because the architecture makes it impossible to bypass.

| Layer | What it does | Status |
|---|---|---|
| **Registry** (v0.1) | Store, verify, audit mandates. SHA-256 chain. MCP native. | ✅ Live |
| **Enforcement** (planned) | Mandate-gated execution authorization. No mandate = no action. | 🔜 In design |
| **Ecosystem** | AMR authorizes *before* the action. Certification proxies prove what happened *during*. | Compatible today |

The open-source registry stays free. The enforcement layer is the commercial product.

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

Restart Claude Desktop. AMR's four tools will be available immediately.

---

## Tools

### `create_mandate`

Register a new legal mandate authorizing an AI agent to act on behalf of a principal.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `principal_id` | str | Principal granting the mandate. E.g. `"user:audric"` |
| `agent_id` | str | Agent receiving authorization. E.g. `"agent:korvex-advisor-v1"` |
| `scope` | str | What the agent is authorized to do |
| `legal_basis_regulation` | str | Regulation or contract. E.g. `"EU AI Act Art.26"` |
| `legal_basis_article` | str | Specific article or clause. E.g. `"Art.26(1)(a)"` |
| `duration_hours` | float | Duration in hours (max 8760 = 1 year) |
| `legal_basis_jurisdiction` | str | Jurisdiction code (default `"EU"`) |
| `parent_mandate_id` | str \| null | UUID of parent mandate for delegation chains (parent must allow delegation) |
| `metadata` | dict | Optional string key-value pairs for annotations |
| `allowed_actions` | list[str] \| null | Action types the agent may request: `"invoice.pay"`, `"invoice.*"` or `"*"` |
| `forbidden_actions` | list[str] \| null | Action types never allowed (win over `allowed_actions`). E.g. `["agent.create"]` |
| `delegation_allowed` | bool | Whether the agent may grant sub-mandates (default `false`) |
| `max_amount` | str \| null | Ceiling per action, decimal string. E.g. `"500"` |
| `currency` | str | ISO 4217 code of `max_amount` (default `"EUR"`) |
| `amount_actions` | list[str] \| null | Actions that must carry an `amount` under the ceiling (empty: all) |
| `period_max_amount` | str \| null | Cumulative ceiling over `period_days`, for this mandate and all its sub-mandates, decimal string. E.g. `"2000"` |
| `period_days` | int \| null | Rolling window of `period_max_amount`, 1 to 366 days (required with it). E.g. `30` |
| `risk_classes` | list[dict] \| null | Classes `{name, actions, max_token_seconds}` bounding the token lifetime of the actions they reach, here and in every sub-mandate. E.g. `[{"name": "irreversible", "actions": ["invoice.pay"], "max_token_seconds": 30}]` |
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

Returns `{"status": "registered", "principal_id", "key_id", "registered_at", "chain_hash"}`.

---

### `prepare_mandate_signature`

Same arguments as `create_mandate` (plus optional `signed_at`, default now). Writes
nothing; returns `{"payload", "payload_b64url", "signed_at"}`: the exact bytes the
principal signs before calling `create_mandate`.

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
`log_action` refuses it; `get_proof` and `export_insurer_dossier` report it. Tokens already issued cannot be
called back and stay valid until their `exp`: the response gives their number and the
last expiry. Mandate attestations already issued also stay valid until their `exp`
(15 minutes by default) and are not counted in the response.

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
  "outstanding_tokens": {"still_valid": 1, "last_expires_at": "2026-10-23T20:34:12+00:00"}
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
  "actions": [ "...list of all logged actions..." ],
  "events": [],
  "chain_integrity": {
    "actions_chain_valid": true,
    "principal_signature_valid": null,
    "revocation_signature_valid": null,
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
│  Ready for regulatory audit, eIDAS submission, or archival          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Security

1. **Pydantic v2 validation** — All tool inputs are validated before any DB interaction. Unknown fields are rejected (`extra="forbid"`). Duration, string lengths, and UUID formats are enforced at the model layer.

2. **Parameterized SQL only** — Every database query uses `?` placeholders. No string interpolation or f-strings in SQL. Enforced by `ruff` S608 rule on every commit.

3. **Append-only tables** — The `mandates` and `action_logs` tables are never `UPDATE`d or `DELETE`d. The audit trail is immutable by design. Status changes use a separate `mandate_events` table.

4. **SHA-256 cryptographic chain** — Each mandate and each action log entry is linked to the previous one via a SHA-256 hash (git-style). Any tampering invalidates all subsequent hashes, making the trail tamper-evident.

5. **stdio transport only** — AMR runs as a local MCP server over stdio. No listening port, no inbound network exposure, no outbound HTTP from tools, with one opt-in exception: `report_issue` sends one HTTPS request to the GitHub API, and only when the operator has set `AMR_ISSUE_TOKEN`. The attack surface is minimal.

---

## Regulatory Context

| Regulation | Relevance to AMR |
|---|---|
| **EU AI Act Art.26** | High-risk AI system operators must maintain logs of agent mandates and actions. AMR provides the technical infrastructure for this obligation. Effective **August 2026**. |
| **EU AI Act Art.26(6)** | Logs must be retained for a minimum of 6 months. AMR's append-only SQLite database and Proof Pack export support this requirement. |
| **eIDAS 2.0** | Electronic mandates for AI agents acting on behalf of natural or legal persons. AMR's mandate chain maps to the eIDAS electronic delegation trust framework. |
| **Fines** | EU AI Act fines up to **€30M or 6% of global annual turnover** for non-compliance with high-risk AI obligations. AMR directly reduces this regulatory risk. |

---

## Roadmap

| Version | Features |
|---|---|
| **v0.1** *(current)* | 4 MCP tools · SQLite · SHA-256 chain · Pydantic validation · Proof Pack JSON · Claude Desktop integration |
| **v0.2** | PDF Proof Pack export · SSE transport for remote MCP clients · Mandate revocation workflow |
| **v0.3** | PostgreSQL backend · Multi-tenant support · REST API alongside MCP |
| **v0.4** | eIDAS 2.0 qualified electronic signature integration · Cross-border mandate recognition |
| **v0.5** | Managed Agents registry · Sub-delegation chains · Webhook notifications on mandate events |
| **v0.6** | **Enforcement layer** — mandate-gated execution authorization · No valid mandate = no action · Dashboard + alerting |

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
├── server.py          # FastMCP server entrypoint (stdio transport)
├── models/mandate.py  # Pydantic models: MandateCreate, Mandate, ActionLog
├── crypto/chain.py    # compute_hash() and verify_chain() — stdlib only
├── db/engine.py       # init_db(), get_db(), get_last_mandate_hash()
├── tools/
│   ├── create_mandate.py
│   ├── verify_mandate.py
│   ├── log_action.py
│   ├── get_proof.py
│   ├── issue_mandate_attestation.py   # attestation + registry public key
│   ├── revoke_mandate.py
│   ├── report_issue.py   # only network call, opt-in (AMR_ISSUE_TOKEN)
│   └── export_insurer_dossier.py
├── attestation.py     # offline attestation verifier (no DB, no network)
├── verify_attestation.py  # python -m amr.verify_attestation
├── proof/insurer_dossier.py  # Signed insurer dossier: canonical form, JWS, print view
└── templates/         # Sector mandate templates (agent-sante-rgpd)
tests/
├── conftest.py              # Isolated temp DB fixture (autouse)
├── test_create_mandate.py   # 5 tests
├── test_verify_mandate.py   # 3 tests
├── test_log_and_proof.py    # 5 tests
└── test_crypto.py           # 7 tests
```

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `AMR_DB_PATH` | `amr_mandates.db` | Path to the SQLite database file |
| `AMR_LOG_LEVEL` | `INFO` | Logging verbosity |
| `AMR_SERVER_NAME` | `Agent Mandate Registry` | MCP server display name |
| `AMR_REQUIRE_PRINCIPAL_SIGNATURE` | `false` | Refuse every mandate not signed by its principal |
| `AMR_PRINCIPAL_SIGNATURE_MAX_AGE_SECONDS` | `900` | Allowed gap between `signed_at` and the registry clock |
| `AMR_ISSUE_TOKEN` | unset | GitHub token that lets `report_issue` file issues itself (fine-grained, Issues: write, one repository). Read from the process environment only, never from `.env`. Unset: no network call |
| `AMR_ISSUE_REPOSITORY` | `JC7333/amr` | Repository `report_issue` files issues on (`owner/name`) |
| `AMR_ATTESTATION_LIFETIME_SECONDS` | `900` | Longest lifetime of a mandate attestation |

---

## License

Apache License 2.0 — See [LICENSE](LICENSE) for full terms.

Free to use in commercial products. Compatible with EU AI Act open-source provisions.

---

> ⚠️ **Disclaimer:** AMR is a technical infrastructure tool. It does not constitute legal advice. Compliance with EU AI Act, eIDAS 2.0, or any other regulation remains the responsibility of the operator. Consult qualified legal counsel for your specific regulatory obligations.
