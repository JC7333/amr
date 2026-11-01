# Insurer dossier — specification (v1.0)

The insurer dossier is a signed export of one mandate over a period. It answers, in one
document, the questions an insurer or an auditor asks about an AI agent: who authorized
it, to do what, with which limits, whether it could delegate, whether it was stopped,
and what it did. It contains facts recorded by the registry and nothing else: no legal
assessment, no compliance statement.

Tool: `export_insurer_dossier(mandate_id, period_start=None, period_end=None, format="json")`.
Read-only: the export writes nothing to the registry. Existing mandates and their
chain hashes are unchanged.

## Content

| Field | Meaning |
|---|---|
| `dossier_version` | `"1.0"` |
| `generated_at` | When the registry produced the dossier (UTC) |
| `period` | `{start, end}`, both inclusive; defaults to the mandate's creation and `generated_at`. Only ISO 8601 date-times are accepted (a bare date or a number is refused); naive date-times read as UTC |
| `mandate` | The mandate as stored (same object as in the Proof Pack), including its perimeter and, if any, the principal's signature |
| `status` | `stored_status`, `in_force` at `generated_at`, `not_in_force_reason` |
| `integrity` | `actions_chain_valid` and `total_actions` (whole mandate, not only the period), `principal_signature_valid` (`null` when the mandate is not signed by its principal), `principal_key_id`, `chain_head` (last action chain hash, or the mandate's chain hash when no action), `contested_actions` (number of actions of the mandate contested with `contest_action`) and `contests_intact` (as in the Proof Pack) |
| `sub_mandates` | The delegation tree below the mandate, breadth first: `id`, `parent_mandate_id`, `depth`, `principal_id`, `agent_id`, `scope`, dates, `perimeter`, `status`, `integrity`, `actions_in_period` |
| `sub_mandates_truncated` | `true` when the tree was cut at 500 sub-mandates or at the maximum delegation depth (16); the events and tokens of omitted sub-mandates are omitted too |
| `events` | Status events (`mandate_events`) of the period, for the mandate and its sub-mandates |
| `actions` | Actions logged under the exported mandate itself in the period (sub-mandates: count only, in `sub_mandates[].actions_in_period`) |
| `tokens` | Action tokens issued in the period for the mandate and its sub-mandates (`jti`, `mandate_id`, `agent_id`, `action_hash`, `audience`, `issued_at`, `expires_at`, `key_id`) |
| `limits` | Fixed list of what the dossier does not prove |

### In force

A mandate is in force when its stored status is `active`, it has not expired, and every
mandate above it is in force. `not_in_force_reason` is one of `mandate_<status>`,
`mandate_expired`, a delegation-chain refusal for the exported mandate
(`parent_mandate_<status>`, `parent_mandate_expired`, `parent_mandate_not_found`,
`delegation_chain_too_deep`), or `parent_mandate_not_in_force` for a sub-mandate whose
parent is cut. Its own status is checked first.

## Signature

- Canonical form: exactly Python's `json.dumps(dossier, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` encoded as UTF-8 (keys sorted by Unicode code point; this is not RFC 8785 JCS, which sorts by UTF-16 code units). A verifier does not need to rebuild it: the JWS payload is the signed bytes.
- JWS Compact Serialization (RFC 7515). Header: `{"alg": "EdDSA", "kid": <registry key id>, "typ": "amr-insurer-dossier+json"}`. Payload: the canonical dossier bytes.
- Key: the registry's Ed25519 signing key (`AMR_SIGNING_KEY_PATH`), the same key that signs action tokens. The export never creates it: without a key it returns an error. `kid` is the first 16 hex characters of the SHA-256 of the raw public key.
- `dossier_sha256`: SHA-256 of the canonical bytes, printed on the HTML page so a paper copy can be matched to the signed JSON.

### Verification (offline)

`amr.proof.insurer_dossier.verify_dossier(jws, public_key_pem)`:

1. the key must be an Ed25519 public key;
2. the signature must verify with EdDSA (the only accepted algorithm: `none`, HMAC and
   RSA are refused);
3. `typ` must be `amr-insurer-dossier+json`;
4. the payload must be a JSON object whose canonical form is exactly the signed bytes.

It returns the dossier, or raises `DossierVerificationError`. The verifier must obtain
the registry public key out of band (published by the registry operator, or exchanged
when the policy is written); the `public_key_pem` returned with the export is a
convenience for the operator, not a trust anchor.

## Print view

With `format="html"`, the result also carries a self-contained HTML page (inline CSS, no
script, no external resource, every value escaped) meant to be printed or saved as PDF
from the browser. It renders the signed dossier and shows its SHA-256 and the key id.
Unicode bidirectional control characters are replaced by U+FFFD on the page (not in the
JSON), so a printed value cannot be made to read in a misleading order.
Only the JSON signature is proof.

## Limits (also written in every dossier)

- The signature proves what the registry stated at generation time, not that its
  database was never altered before (the action log chain detects edits to logged
  actions; it does not cover a registry that rewrites its own history).
- Refused token requests are not recorded by this registry version.
- The dossier is read in several steps, not in one database transaction: a change
  recorded while it is generated may appear only in part.
- Actions are logged by the agent's operator: an action never logged does not appear.
- The principal is identified by the key it registered; the registry does not check who
  registered that key (see `docs/principal-signature-spec.md`).
- The legal basis is the one declared at creation; the registry does not assess it.
