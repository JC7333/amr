# report_issue: an agent reports a problem with AMR

## Why

An agent that installs and runs AMR on its own (see the README, "Quickstart for agents")
also needs a way to report what goes wrong, without a person in between. `report_issue`
turns what the agent observed into a GitHub issue on the AMR repository.

## Two modes

| Operator setting | What the tool does | Network |
|---|---|---|
| `AMR_ISSUE_TOKEN` unset (default) | Returns `status: "not_sent"` with `new_issue_url`, a pre-filled `https://github.com/<repo>/issues/new?title=...&body=...` link, and `issues_url` | None |
| `AMR_ISSUE_TOKEN` set | Sends one `POST https://api.github.com/repos/<repo>/issues` and returns `status: "created"`, `issue_number`, `issue_url` | One HTTPS request, 10 s timeout per socket operation, redirects refused, answer read up to 1 MB |

`<repo>` is `AMR_ISSUE_REPOSITORY` (default `JC7333/amr`, format `owner/name`, checked at
start; names made only of dots are refused). This is the only tool of AMR allowed to reach
the network (CLAUDE.md, rule 5), and only in the second mode. A test parses every module
under `src/amr` and fails if another one imports a network module (`urllib.request`,
`http`, `socket`, `ssl`, `requests`, `httpx`, `aiohttp`, `urllib3`, and a few others) or
calls `urlopen`, `open_connection` or `create_connection`.

The token is the operator's: a fine-grained GitHub token limited to Issues: write on that
one repository. It is read from the server's process environment only, never from a
`.env` file, so an agent that can write files in its working directory cannot switch the
network on. A token made only of spaces counts as unset. It is never written to the
database, never returned in a result (errors carry the HTTP status or the exception type
only) and never logged. Redirects are refused, because urllib would otherwise resend the
`Authorization` header to the new address.

## Input

| Argument | Rule |
|---|---|
| `title` | 5 to 120 characters |
| `description` | 10 to 4000 characters |
| `version` | 1 to 40 characters (the AMR version the agent runs) |
| `context` | optional, up to 1000 characters (MCP client, OS, Python version) |

Leading and trailing spaces are removed before the lengths are checked. Unknown arguments
are refused (`extra="forbid"`). Spaces, line breaks and invisible characters are removed,
then any field that contains one of these shapes is refused with `issue_contains_secret`,
before any network call: a PEM header (`-----BEGIN`); a compact JWS (`eyJ...`.`...`.`...`,
the form of AMR tokens and attestations, detached payload included); a GitHub token
(`ghp_`, `gho_`, `ghs_`, `ghu_`, `ghr_`, `github_pat_`); a bare PKCS#8 Ed25519 private key
(`MC4CAQAwBQYDK2Vw...`).

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

In the body, `#` and `@` are written as the HTML entities `&#35;` and `&#64;`: they show
the same on GitHub but cannot mention a user or link an issue, so an agent cannot make
the operator's token notify anyone. The title is sent as written.
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
- The secret check recognises the shapes listed above only. It does not detect other
  secrets, names, addresses, health data or other personal data: do not write them.
