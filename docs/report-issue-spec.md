# report_issue: an agent reports a problem with AMR

## Why

An agent that installs and runs AMR on its own (see the README, "Quickstart for agents")
also needs a way to report what goes wrong, without a person in between. `report_issue`
turns what the agent observed into a GitHub issue on the AMR repository.

## Two modes

| Operator setting | What the tool does | Network |
|---|---|---|
| `AMR_ISSUE_TOKEN` unset (default) | Returns `status: "not_sent"` with `new_issue_url`, a pre-filled `https://github.com/<repo>/issues/new?title=...&body=...` link, and `issues_url` | None |
| `AMR_ISSUE_TOKEN` set | Sends one `POST https://api.github.com/repos/<repo>/issues` and returns `status: "created"`, `issue_number`, `issue_url` | One HTTPS request, 10 s timeout |

`<repo>` is `AMR_ISSUE_REPOSITORY` (default `JC7333/amr`, format `owner/name`, checked at
start). This is the only tool of AMR allowed to reach the network (CLAUDE.md, rule 5), and
only in the second mode. A test fails if any other module under `src/amr` imports a
network library.

The token is the operator's: a fine-grained GitHub token limited to Issues: write on that
one repository. It is read from the environment as a secret value, never written to the
database, never returned in a result and never logged.

## Input

| Argument | Rule |
|---|---|
| `title` | 5 to 120 characters |
| `description` | 10 to 4000 characters |
| `version` | 1 to 40 characters (the AMR version the agent runs) |
| `context` | optional, up to 1000 characters (MCP client, OS, Python version) |

Unknown arguments are refused (`extra="forbid"`). Text that contains a PEM block
(`-----BEGIN ...-----`) or something shaped like a compact JWS (`eyJ...`.`...`.`...`, the
form of AMR tokens and attestations) in any field is refused with
`issue_contains_secret`, before any network call.

## What is sent

Exactly this, nothing more:

```
title: <title>
body:  <description>

       ---
       AMR version: <version>
       Context: <context>            (only when given)
       Reported by an agent through the AMR report_issue tool.
```

The tool takes no mandate id and reads no database: no mandate, journal entry, key or
token from the registry can be attached by the tool itself. What the caller writes in
the text is the caller's responsibility; the secret check above is a safety net, not a
filter for personal data.

The pre-filled link keeps the body while the whole link stays under 8000 characters;
beyond that it carries the title only, and the agent or its user pastes the description.

## Errors

| Code | When | Extra field |
|---|---|---|
| `issue_report_invalid` | An argument breaks a rule above | |
| `issue_contains_secret` | A field looks like a private key or a signed token | |
| `issue_not_created` | GitHub answered an HTTP error, could not be reached, timed out, or answered without an issue number and link | `new_issue_url` (pre-filled link to file it by hand) |

## Limits

- The tool does not deduplicate: two calls file two issues.
- No rate limit inside AMR: GitHub's own limits apply to the token.
- The secret check recognises PEM blocks and JWS-shaped tokens only. It does not detect
  names, addresses, health data or other personal data: do not write them.
