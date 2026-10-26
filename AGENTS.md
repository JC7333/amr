# AMR for agents

AMR (Agent Mandate Registry) is an MCP server that records which person or organization
(the principal) authorized which AI agent to do what, for how long, and keeps a
hash-chained, append-only journal of what the agent then did. Repository:
https://github.com/JC7333/amr (Apache-2.0). Human-readable guide: `README.md`.

## Install and run

```bash
uvx --from git+https://github.com/JC7333/amr --with "mcp<2" amr
```

- Transport: stdio. Needs uv and Python 3.12 or later.
- Keep `--with "mcp<2"`: without it a fresh install picks version 2 of the MCP Python
  SDK, which AMR does not support yet (error: `No module named 'mcp.server.fastmcp'`).
- AMR is not on PyPI: `uvx amr` installs a different project.
- Set `AMR_DB_PATH`, `AMR_SIGNING_KEY_PATH`, `AMR_PUBLIC_KEY_PATH` to absolute paths,
  or AMR writes them in the client's current directory. Never commit the `.pem` file.
- Runnable end-to-end example: `examples/quickstart_agent.py`.

## What it does

| Tool | Use it to |
|---|---|
| `create_mandate` | Register a mandate (principal, agent, scope, legal basis, duration, optional perimeter) |
| `verify_mandate` | Ask whether an agent has an active, unexpired mandate (does not check the action against the perimeter) |
| `log_action` | Append an action to the chained journal of a mandate |
| `get_proof` | Export the full audit bundle of a mandate |
| `issue_action_token` | Get a signed token only if the mandate and its perimeter allow the action (this is where the perimeter is enforced) |
| `register_principal_key` | Register the principal's Ed25519 public key |
| `prepare_mandate_signature` | Build the exact bytes a principal signs for a mandate |
| `issue_mandate_attestation` | Issue a signed document a third party verifies offline |
| `get_registry_public_key` | Get the registry's public key to verify attestations and tokens |
| `export_insurer_dossier` | Export a signed, printable dossier of a mandate |
| `revoke_mandate` | Cut a mandate and every sub-mandate below it, immediately |
| `prepare_revocation_signature` | Build the exact bytes a principal signs to revoke |

## What it does not do

- It does not give legal advice and does not make anyone compliant with any
  regulation; that stays with the operator.
- It does not check who a principal is, unless that principal registered a key and signs
  its mandates (`register_principal_key`).
- It does not host anything: there is no hosted service. The registry runs where you
  start it and trusts its own database file; protect that file.
- It makes no network call. Tokens and attestations already issued stay valid until
  their expiry after a revocation (the revocation response counts the tokens).
- Existing rows are never edited or deleted: status changes are new chained rows.

## Reporting a problem

Open an issue at https://github.com/JC7333/amr/issues with the version, the tool name,
the arguments you sent and the error returned. Do not include real mandate contents,
personal data, keys or tokens.
