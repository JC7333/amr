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

See `docs/token-issuance-spec.md` for the full specification.

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
| `parent_mandate_id` | str \| null | UUID of parent mandate for delegation chains |
| `metadata` | dict | Optional string key-value pairs for annotations |

**Returns:**
```json
{
  "status": "created",
  "mandate_id": "550e8400-e29b-41d4-a716-446655440000",
  "principal_id": "user:audric",
  "agent_id": "agent:korvex-advisor-v1",
  "scope": "Compare and recommend financial products to retail clients",
  "expires_at": "2026-05-13T20:00:00+00:00",
  "chain_hash": "a3f5c2d1e8b9..."
}
```

---

### `verify_mandate`

Check whether an AI agent has a currently active, non-expired mandate.

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
    "total_actions": 5,
    "total_events": 0
  },
  "compliance_notes": {
    "ai_act_art26": "This Proof Pack documents the mandate chain for AI Act Art.26 compliance.",
    "retention": "Logs must be retained for minimum 6 months per AI Act Art.26(6)."
  }
}
```

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

# Run the full test suite (20 tests)
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
└── tools/
    ├── create_mandate.py
    ├── verify_mandate.py
    ├── log_action.py
    └── get_proof.py
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

---

## License

Apache License 2.0 — See [LICENSE](LICENSE) for full terms.

Free to use in commercial products. Compatible with EU AI Act open-source provisions.

---

> ⚠️ **Disclaimer:** AMR is a technical infrastructure tool. It does not constitute legal advice. Compliance with EU AI Act, eIDAS 2.0, or any other regulation remains the responsibility of the operator. Consult qualified legal counsel for your specific regulatory obligations.
