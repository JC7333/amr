# AMR — Agent Mandate Registry

AMR is an open-source MCP server that registers and verifies legal mandates for AI agents.
It provides a cryptographically chained audit trail of agent authorizations and actions,
designed for compliance with EU AI Act Art.26 and eIDAS 2.0.

---

## Architecture Decisions

| Decision | Choice | Justification |
|---|---|---|
| MCP framework | FastMCP (mcp[cli]) | Official Python MCP SDK; generates tool schemas from type hints + docstrings |
| Database | SQLite + aiosqlite | Zero-dependency, file-based, ACID, WAL mode for concurrent reads |
| Validation | Pydantic v2 | Fast, strict, native type hints, `extra="forbid"` prevents unknown fields |
| SQL security | Parameterized `?` only | Prevents SQL injection (ruff S608 enforced) |
| Integrity | SHA-256 chain | Git-style tamper-evident chain; no blockchain overhead |
| Tables | Append-only | No UPDATE/DELETE on mandates/action_logs; immutable audit trail |
| License | Apache-2.0 | Permissive, compatible with commercial use and AI Act open-source provisions |
| Package manager | uv | Fast, reproducible, PEP 517 compliant, lockfile included |
| Linter | ruff | Blazing fast, replaces flake8 + isort + bandit (S rules for security) |

---

## Project Structure

```
src/amr/
├── __init__.py
├── config.py          # Settings via pydantic-settings (env prefix: AMR_)
├── server.py          # FastMCP server entrypoint (stdio transport)
├── models/
│   ├── __init__.py
│   └── mandate.py     # Pydantic models: MandateCreate, Mandate, ActionLog, VerifyResult
├── crypto/
│   ├── __init__.py
│   └── chain.py       # compute_hash() and verify_chain() — stdlib only
├── db/
│   ├── __init__.py
│   └── engine.py      # init_db(), get_db(), get_last_mandate_hash(), get_last_action_hash()
├── tools/
│   ├── __init__.py
│   ├── create_mandate.py   # Tool: register a new agent mandate
│   ├── verify_mandate.py   # Tool: check if an agent has an active mandate
│   ├── log_action.py       # Tool: log an agent action under a mandate
│   └── get_proof.py        # Tool: generate a Proof Pack (full audit bundle)
└── proof/
    └── __init__.py    # Reserved for future proof format extensions
tests/
├── __init__.py
└── conftest.py
```

---

## Security Rules (Non-Negotiable)

1. **Parameterized SQL only** — All queries use `?` placeholders. Never f-strings or `.format()` in SQL.
2. **Pydantic validation first** — All tool inputs are validated via Pydantic models before DB interaction.
3. **Append-only tables** — `mandates` and `action_logs` are never UPDATEd or DELETEd. Status changes use `mandate_events`.
4. **No secrets in code** — All config via env vars (prefix `AMR_`). Never hardcode credentials.
5. **No network calls** — AMR is a local MCP server. Zero outbound HTTP from tools.
6. **Chain hash linking** — Every mandate and action log entry is linked via SHA-256 to the previous entry.
7. **ruff S rules** — Security linting enforced. `ruff check src/` must pass before any commit.

---

## Commands

```powershell
# Start the MCP server (stdio transport for Claude Desktop / MCP clients)
uv run amr

# Run the test suite
uv run pytest -v

# Lint and security check
uv run ruff check src/

# Auto-fix safe issues
uv run ruff check --fix src/

# Validate imports work
uv run python -c "from amr.config import settings; print(settings.server_name)"
```

---

## Regulatory Context

| Regulation | Relevance |
|---|---|
| **EU AI Act Art.26** | High-risk AI system operators must maintain logs of agent actions and mandates. AMR provides the technical infrastructure for this obligation. |
| **EU AI Act Art.26(6)** | Logs must be retained for minimum 6 months. AMR's append-only SQLite + Proof Pack export supports this requirement. |
| **eIDAS 2.0** | Electronic mandates for AI agents acting on behalf of natural/legal persons. AMR's mandate chain maps to the eIDAS trust framework. |
| **Fines** | EU AI Act fines up to €30M or 6% global turnover for non-compliance with Art.26. AMR reduces this risk. |

---

## MCP Tool Reference

| Tool | Description |
|---|---|
| `create_mandate` | Register a new legal mandate for an AI agent (principal → agent) |
| `verify_mandate` | Check if an agent has an active, non-expired mandate |
| `log_action` | Log an agent action under an active mandate (append-only, chained) |
| `get_proof` | Generate a full Proof Pack JSON for a mandate (mandate + actions + integrity) |
