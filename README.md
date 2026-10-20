# Agent Mandate Registry (AMR)

> **The legal mandate layer for AI agents.**

AMR is an open-source [MCP](https://modelcontextprotocol.io/) server that registers, verifies, and audits legal mandates authorizing AI agents to act on behalf of principals. It provides a cryptographically chained audit trail designed for compliance with **EU AI Act Art.26** (effective August 2026) and **eIDAS 2.0**.

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
- every token issued under a sub-mandate re-checks the whole chain: revoke or let
  expire the parent, and every sub-mandate below it stops getting tokens.

Example: an assistant agent told never to create sub-agents.

```json
create_mandate(..., allowed_actions=["report.*"], forbidden_actions=["agent.create"])
issue_action_token(..., action_type="agent.create")
→ {"denied": true, "reason": "action_out_of_scope", "detail": "forbidden:agent.create"}
```

Root mandates without a perimeter keep working as before (free-text scope,
existence and validity checks only, same hashes). Two changes are deliberate and
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
git clone https://github.com/your-org/amr.git
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

5. **stdio transport only** — AMR runs as a local MCP server over stdio. No listening port, no inbound network exposure, no outbound HTTP from tools. The attack surface is minimal.

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
│   └── get_proof.py
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

---

## License

Apache License 2.0 — See [LICENSE](LICENSE) for full terms.

Free to use in commercial products. Compatible with EU AI Act open-source provisions.

---

> ⚠️ **Disclaimer:** AMR is a technical infrastructure tool. It does not constitute legal advice. Compliance with EU AI Act, eIDAS 2.0, or any other regulation remains the responsibility of the operator. Consult qualified legal counsel for your specific regulatory obligations.
