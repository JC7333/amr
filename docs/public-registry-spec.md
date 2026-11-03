# Public registry: online verification without an account

Status: v1 (`format: "amr-public-registry.v1"`). No change to the database schema.

The question it answers: a receiver (a seller, a hospital, an insurer) holds only a
mandate identifier, or an attestation pasted from an email. Can it check, in a browser
or from a script, without an account, whether that mandate exists, what it allows, and
whether it is still standing?

AMR runs over stdio next to each operator; nobody else can query it. The public
registry is a separate, read-only verification point fed by a **signed snapshot** of
the operator's registry. It never touches the database.

```
operator's registry (SQLite)  --export (read-only, signed)-->  snapshot.jws
snapshot.jws + pinned public key  -->  read-only WSGI app  -->  JSON for machines, HTML for people
```

## 1. Export: `python -m amr.public_registry export`

```bash
python -m amr.public_registry export --out amr_public_registry.jws [--db amr_mandates.db]
```

Opens the database read-only (`mode=ro`; a missing file is an error, nothing is
created; a database not yet migrated to the current schema gives `schema_outdated`:
start the AMR server once) and signs with the existing registry key (a missing key
gives `signing_key_not_found`; the export never creates a key). It writes a compact JWS, written atomically (temporary file then rename):

* header: `alg` `EdDSA` (the only algorithm, hard-coded), `typ`
  `amr-public-registry+jwt`, `kid` = key id of the registry key (the one that signs
  tokens and attestations, see `get_registry_public_key`);
* claims: `iss`, `iat`, and `amr_public_registry` = `{format, issuer, key_id,
  generated_at, mandates[]}`.

Each mandate carries only these fields (anything else makes the snapshot invalid):

| Field | Content |
|---|---|
| `id` | mandate UUID |
| `agent_id` | agent identifier, as recorded |
| `principal_ref` | `sha256:` + SHA-256 of the principal identifier |
| `principal_signed`, `principal_key_id` | whether the principal signed the mandate, and with which key |
| `perimeter`, `perimeter_digest` | structured perimeter (action types, ceilings, delegation, risk classes) |
| `created_at`, `expires_at` | dates |
| `parent_mandate_id` | parent, for a sub-mandate |
| `recorded_status` | `mandates.status` |
| `revoked_at` | date of the `revoke_mandate` row, or null |
| `chain_hash` | the mandate's SHA-256 chain hash, unchanged |

**Never exported:** the principal identifier in clear, the scope text, the legal basis,
the metadata (it can name people, e.g. an organ decision), the revocation reason,
action logs, contests. `principal_ref` is a pseudonym, not an anonymisation: whoever
knows the identifier can recompute and compare it, and a short or guessable identifier
can be found by trying candidates. `agent_id` is published as recorded: do not use a
person's name as an agent identifier in a registry you publish.

Export again after every change you want visible (creation, revocation), or on a
schedule. The application shows the snapshot date on every answer.

## 2. Serve: `make_app` (WSGI)

```python
from amr.public_registry import app_from_settings
app = app_from_settings()  # AMR_PUBLIC_EXPORT_PATH, AMR_PUBLIC_KEY_PATH
```

Local test: `python -m amr.public_registry serve --export amr_public_registry.jws
--public-key registry.pub` (binds `127.0.0.1:8080` by default; standard library
server, access log disabled).

At start, the snapshot is verified with the **pinned** public key (a PEM, or the JSON
of `get_registry_public_key`): EdDSA only, type `amr-public-registry+jwt`, key id of
the pinned key, Ed25519 signature, content matching v1 exactly, no mandate twice.
Otherwise `PublicRegistryError` and nothing is served: a storage layer separate from
the process (a file store, a bucket) cannot alter the snapshot without the private
key, which never leaves the operator. **Whoever runs the process is trusted**: a host
that controls the running code can answer anything. A receiver who does not trust the
host downloads the raw snapshot (`/snapshot`) and verifies it itself with the key it
pinned (`load_snapshot`).

Rollback: any correctly signed snapshot verifies, including an older one taken before
a revocation. Set `AMR_PUBLIC_SNAPSHOT_MAX_AGE_SECONDS` (or `max_snapshot_age_seconds`)
and export at least that often: past that age, mandate and attestation checks answer
`503` with `snapshot_too_old` instead of a status. Without it, only
`snapshot_age_seconds` shows the age.

Routes, `GET` and `HEAD` only (anything else: 405, `Allow: GET, HEAD`):

| Route | Answer |
|---|---|
| `/` | HTML form for people (`Accept: text/html`), list of endpoints in JSON otherwise |
| `/mandates/<id>` | status of the mandate now, from the snapshot |
| `/attestation?attestation=<jws>[&audience=<you>]` | verification of an attestation (`docs/mandate-attestation-spec.md`) |
| `/key` | the registry public key |
| `/snapshot` | the signed snapshot itself (compact JWS, `application/jose`), for receivers who verify it themselves |

JSON by default; HTML with `?format=html` or a browser's `Accept`. Every JSON answer
and every result page (all but the home page and `/snapshot`) carries
`checked_at`, `registry` (`issuer`, `key_id`, `snapshot_generated_at`,
`snapshot_age_seconds`, a notice that later revocations are not shown) and
`verification_ms`, the time the verification took on the server, which the HTML page
displays.

### Mandate status

Evaluated at request time from the snapshot, the mandate first, then every mandate
above it:

| `status` | `reason` |
|---|---|
| `active` | null: recorded active, not revoked, not expired, and every parent too; `delegation_chain` lists the parents |
| `revoked` | `mandate_revoked`; `mandate.revoked_at` gives the date |
| `inactive` | `mandate_<recorded status>` |
| `expired` | `mandate_expired` (expiry passed, even if it was active when exported) |
| `cut_by_parent` | `parent_mandate_revoked`, `parent_mandate_<status>`, `parent_mandate_expired`, `parent_mandate_not_found` or `delegation_chain_too_deep`; `refused_by` names the parent |
| `unknown` | 404: the identifier is not in the snapshot; nothing else is said |
| `invalid_id` | 400: not a UUID |
| `snapshot_too_old` | 503: only with a maximum age set, see section 2 |

### Attestation

The pasted attestation is verified offline with the pinned key and the snapshot's
issuer (`verify_attestation`). If it is valid but the mandate, or a mandate above it,
is revoked in the snapshot, the answer is `valid: false`, `reason:
"revoked_in_registry"`, with `refused_by` and `revoked_at`: the online check closes,
up to the snapshot date, the window in which an offline receiver would still accept
it. `in_snapshot` says whether the mandate appears in the snapshot. An attestation
addressed to an audience is accepted only with `audience` set to it.

### What the application does not do

No write path, no database, no account, no cookie, no outbound call. It never reads
the client's address and writes no log; the local server's access log is disabled.
The hosting provider may keep its own logs: choose and configure it accordingly.
Headers: `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`,
`Referrer-Policy: no-referrer`, a restrictive `Content-Security-Policy` (no script);
JSON answers allow any origin (`Access-Control-Allow-Origin: *`). Query strings over
16 KB are refused (414), more than 8 fields too (400, `bad_query`). Every value shown in HTML is escaped.

## 3. Hosting (operator's step)

Deployment, domain and DNS are the operator's decision; nothing in this repository
deploys. The application is a plain WSGI callable, so a Python host that serves WSGI
can run it, with two files: the snapshot and the public key. Choose a host you trust
to run the code unchanged (section 2). Pin the key (do not fetch it from the same
place as the snapshot) and publish its `key_id` where receivers already trust you.

## Known limits

* The answers themselves are not signed; only `/snapshot` is. Trust in an answer is
  trust in whoever runs the application.
* A snapshot is a photograph. A mandate revoked after `generated_at` still shows as
  active until the next export; `snapshot_age_seconds` says how old the answer is. For
  an irreversible act, the receiver should also use `check_action_token` with the
  operator (see `docs/token-issuance-spec.md`).
* The registry trusts its own database, as everywhere in AMR: the export signs what
  the database says.
* Action tokens are not verified here (they are bound to an audience and to one
  action; see `check_action_token`).
* One registry key, no rotation (as for attestations).
* `principal_ref` is a pseudonym (see section 1). Who the principal really is, is not
  proven here: see `docs/principal-signature-spec.md`, Known limits.
