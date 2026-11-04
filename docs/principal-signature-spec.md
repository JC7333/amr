# Principal signatures on mandates

Status: v1 (schema v4; did:web keys: schema v9). First step towards answering "who really
granted this mandate?".

Without it, anyone who can call `create_mandate` can register a mandate in the name of
any principal, including an agent minting itself a root mandate. With it, a principal
registers its own Ed25519 public key once, and from then on the registry accepts a
mandate in its name only if it was signed with that key. A valid signature proves
possession of the key first registered for the `principal_id`, not the identity of
the person behind it (see Known limits). The signature is sealed into the
mandate's `chain_hash` and kept, with the exact signed bytes and the public key, in the
Proof Pack, so a third party can re-check it offline.

This is separate from the registry's own token key (`amr_signing_key.pem`, used for
action tokens): the registry never holds a principal's private key.

## Encodings

- Algorithm: Ed25519 (RFC 8032), nothing else is accepted.
- Public key: the 32 raw bytes, base64url without padding (padding is tolerated on input).
- Signature: the 64 raw bytes, base64url without padding (padding tolerated on input,
  stored without it).
- Signed payloads: canonical JSON, UTF-8, keys sorted, no whitespace
  (`json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`).
  Do not rebuild them by hand: `prepare_mandate_signature` returns the exact bytes.

## 1. Register the principal's key: `register_principal_key`

| Parameter | Description |
|---|---|
| `principal_id` | The principal, e.g. `"user:audric"` |
| `public_key` | Base64url Ed25519 public key |
| `proof_signature` | Signature of the registration payload (proof of possession) |

Registration payload:

```json
{"context":"amr.principal_key.v1","principal_id":"user:audric","public_key":"<base64url, no padding>"}
```

The key record is appended to the `principal_keys` table and chained (SHA-256, like
mandates). One key per principal: a second registration is refused
(`principal_key_already_registered`). Key rotation and revocation are not in v1.

**Limit: first registration wins.** For an ordinary `principal_id`, the registry does not
check who registers a key. Expose `register_principal_key` to principals (or their back
office) only, never to agents, and register each principal's key when the principal is
onboarded. A `did:web` principal closes this gap at the level of a domain name (section
1 bis). Binding the key to a qualified signature or a named signatory is a later step.

Errors: `principal_id_invalid`, `public_key_invalid`, `principal_signature_invalid`
(malformed proof), `principal_key_proof_invalid`, `principal_key_already_registered`,
and for `did:web` principals the codes of section 1 bis.

## 1 bis. Key published by the principal's domain: `did:web` principals

An organisation can use as `principal_id` a `did:web` identifier (W3C did:web method):
`did:web:<domain>` or `did:web:<domain>:<path>:<segments>`. It publishes its Ed25519
key in its DID document, at `https://<domain>/.well-known/did.json` (or
`https://<domain>/<path>/<segments>/did.json`), as a `verificationMethod` with
`publicKeyJwk` `{"kty": "OKP", "crv": "Ed25519", "x": "<base64url>"}` or
`publicKeyMultibase` `"z"` + base58btc(`0xed 0x01` + key). The document's `id` must be
the identifier itself.

`register_principal_key` then accepts the key only if that document lists it: whoever
calls the tool first can no longer take the name of an organisation whose domain they do
not control. Rules:

- **Opt-in network access.** Reading the document is the second exception to "no
  network calls" (the first is `report_issue`). It is off unless the operator sets
  `AMR_DID_WEB_RESOLVE=1` in the server's process environment (never read from `.env`).
  Off, a `did:web` key is refused (`did_web_resolution_disabled`); it never falls back
  to "first registration wins". A `did:web` identifier is recognised whatever its case
  or surrounding spaces, so `DID:Web:...` cannot skip the check; and any identifier
  that reads as `scheme:method:...` must write that prefix in plain ASCII (Cyrillic
  letters, full-width colons or zero-width characters are refused with
  `principal_id_lookalike`, for every principal).
- **One request, constrained.** One HTTPS GET per registration, after the proof of
  possession is checked and only if the principal has no key yet. Certificate checked
  against the host name; no redirect followed; 5 s timeout per socket operation and
  10 s for the whole request; at most 64 KiB read; every address of the domain must be
  public (no private, loopback, link-local, reserved or multicast address, and no
  NAT64, IPv4-compatible, 6to4 or Teredo address that embeds another one); the
  connection is made to an address that was checked (each in turn if one fails). No
  database connection is held while the domain answers.
- **Canonical identifier.** Characters that IDNA 2003 and IDNA 2008 encode differently
  (`ß`, final sigma, zero-width joiners) are refused: write the punycode form.
  The domain is lowercase and in its ASCII form (punycode for
  a domain with accents: `did:web:xn--hpital-ixa.example`); ports and IP addresses are
  refused. A non-canonical identifier is refused with `canonical_principal_id`, the form
  to use.
- **Sealed proof.** The document URL, the SHA-256 of the exact bytes read and the
  verification time are added to the key record sealed in its `chain_hash` (as
  `domain_proof`); the document itself is kept in the append-only table
  `principal_key_domain_proofs`. The result of `register_principal_key` gains
  `domain_proof` (`null` for an ordinary principal).

Errors: `did_web_resolution_disabled`, `did_web_invalid` (malformed identifier, port, IP
address, path segment), `did_web_not_canonical`, `did_web_unreachable` (name not
resolved, connection failed, HTTP status other than 200), `did_web_address_refused`,
`did_web_https_required` (no valid TLS connection), `did_web_redirect` (with
`location`), `did_web_document_invalid` (not a JSON object, too large, `id` not the
identifier), `did_web_key_not_published`.

## 2. Sign a mandate

1. Call `prepare_mandate_signature` with exactly the arguments you will pass to
   `create_mandate` (and optionally `signed_at`, default: now in UTC). Nothing is written.
   It returns `payload` (text), `payload_b64url` (the same bytes) and `signed_at`.
2. The principal signs the UTF-8 bytes of `payload` with its private key.
3. Call `create_mandate` with the same arguments plus `principal_signature` and
   `signed_at`.

Mandate payload (the principal decides every field in it; the registry only adds the
mandate id and timestamps):

```json
{
  "context": "amr.mandate.v1",
  "principal_id": "...", "agent_id": "...", "scope": "...",
  "legal_basis": {"regulation": "...", "article": "...", "jurisdiction": "EU"},
  "duration_hours": 24.0,
  "parent_mandate_id": null,
  "metadata": {},
  "perimeter": null,
  "signed_at": "2026-10-18T20:30:00+00:00"
}
```

`perimeter` is the requested perimeter in canonical form (for a sub-mandate, before
the registry narrows it by its parent).

## 3. Rules applied by `create_mandate`

| Situation | Result |
|---|---|
| Principal has no key, no signature, `AMR_REQUIRE_PRINCIPAL_SIGNATURE` false (default) | Created as before, unsigned |
| Principal has no key, no signature, `AMR_REQUIRE_PRINCIPAL_SIGNATURE` true | `principal_signature_required` |
| Principal has a key, no signature | `principal_signature_required` |
| Only one of `principal_signature` / `signed_at` | `principal_signature_incomplete` |
| Signature given, principal has no key | `principal_key_not_registered` |
| `signed_at` not ISO 8601 with a timezone | `signed_at_invalid` |
| `signed_at` more than `AMR_PRINCIPAL_SIGNATURE_MAX_AGE_SECONDS` (default 900) from the registry clock, past or future | `principal_signature_stale` |
| Signature does not match the arguments and the registered key | `principal_signature_invalid` |
| Signature already used for another mandate | `principal_signature_replayed` |

The rules apply to every mandate, sub-mandates included: the principal of a sub-mandate
is the agent of its parent, so an agent that registered a key must sign the
sub-mandates it grants.

## 4. Chain and Proof Pack

- A signed mandate adds `"principal_signature": {"signature", "signed_at", "key_id"}`
  to the data sealed in its `chain_hash`. Unsigned mandates keep exactly the previous
  hash payload, so existing hashes do not change.
- `get_proof` returns `mandate.principal_signature` =
  `{signature, signed_at, key_id, public_key, key_proof_signature, payload,
  algorithm: "Ed25519"}` (or null), and `chain_integrity.principal_signature_valid`:
  - true if the registered key still carries a valid proof of possession, the signature
    verifies with it, and the signed payload matches the stored mandate (principal,
    agent, scope, legal basis, parent, metadata, signed_at, duration to the second, and
    the perimeter: as signed for a root mandate, as signed then narrowed by the parent
    for a sub-mandate);
  - false otherwise, including when the signature is missing although the principal's
    key was registered before the mandate was created (a stripped signature);
  - null for an unsigned mandate whose principal had no key at the time.
- `mandate.principal_signature.key_domain_proof` is, for a `did:web` principal,
  `{did_document_url, did_document_sha256, verified_at, document, rechecked}`, else
  null. `rechecked` is true when: the key record rebuilt with this proof gives the
  key's stored `chain_hash` (also exported, as `key_chain_hash`), so the proof is the
  one sealed at registration; the URL is the one the identifier names; `verified_at`
  is the registration time; the stored document hashes to the stored SHA-256, has the
  principal as `id` and lists the registered key. These checks run on the registry's
  own database: they detect a proof row changed on its own, not someone who rewrites
  the whole key chain (section 5, last point). To see whether the domain still
  publishes the key today, re-read `did_document_url`.
- `mandate.principal_signature.did_web_unverified` is true when the principal's
  identifier is a `did:web` but its key has no domain proof or the proof fails its
  recheck (for example a key registered before this version). **A consumer that relies
  on a `did:web` principal must require `did_web_unverified: false`.** The mandate
  attestation (`principal_key_domain` with `rechecked`, and
  `principal_did_web_unverified`) and the insurer dossier carry the same information
  (URL, hash, time, recheck; not the document).

## 5. Known limits

- **First registration wins** (section 1) for ordinary principals: the key is not bound
  to a verified identity.
- **did:web proves control of a domain, at one moment.** It shows that the domain served
  the key when it was registered: not a qualified electronic signature, not who inside
  the organisation holds the key, and not that the domain still publishes it (no
  re-check after registration; key rotation is not in v1). Whoever controls the domain's
  web server or DNS, or obtains a certificate for it, controls what the registry reads.
- **did:web and unsigned mandates.** As for every principal, mandates in the name of a
  `did:web` principal that has no key yet are accepted unsigned unless
  `AMR_REQUIRE_PRINCIPAL_SIGNATURE` is true; they carry no signature and no domain proof.
- **Keys registered before did:web checks.** A key registered under a `did:web`
  identifier before this version was not checked against the domain: its
  `key_domain_proof` is null.
- **Per-registry replay protection**: a signature is refused if it already registered a
  mandate in the same database. The payload names no registry, so within the 15-minute
  window the same signed payload could be accepted by another AMR registry where the
  same key is registered. The registration proof does not expire.
- **Identifiers are compared exactly**: `user:victim` and `user:victim ` (trailing space)
  or Unicode look-alikes are different principals. The signature rule protects the exact
  `principal_id` that registered a key. Only the scheme prefix (`did:web:` and the like)
  is checked for look-alike characters; the rest of an identifier is not.
- **Race**: the key lookup and the mandate insert are not one transaction; an unsigned
  mandate whose creation started just before the principal's key registration can still
  be stored. `get_proof` then reports it as `false` if its `created_at` is after the
  registration.
- **No full hash re-check**: `get_proof` does not recompute the mandate's `chain_hash`
  (the stored row does not keep the raw `duration_hours`); it checks the signature and
  the key record as described in section 4. Someone with write access to the database
  file who replaces the key record with a key of their own (new proof of possession
  included) and re-signs the stored payloads is not detected by `get_proof`; the
  `principal_keys` and `mandates` chain hashes would change, but neither chain is
  re-verified by a tool yet. Protect the database file accordingly.

## 6. Compatibility

- Schema v9 adds the table `principal_key_domain_proofs`; no existing row changes, and
  keys of ordinary principals keep exactly the previous hash payload.
- **Behaviour change** for deployments that already use `did:web:` identifiers: with
  the default configuration, registering a key for such an identifier is now refused
  (`did_web_resolution_disabled`) instead of "first registration wins". Set
  `AMR_DID_WEB_RESOLVE=1` and publish the key in the DID document, or keep an ordinary
  identifier. Keys already registered stay valid and are reported with
  `did_web_unverified: true`. Registering an identifier whose `scheme:method:` prefix is
  not plain ASCII is refused (`principal_id_lookalike`).
- Existing databases are migrated in place (schema v4): four nullable columns on
  `mandates`, a new `principal_keys` table, a unique index on the signature. No existing
  row is modified.
- Existing mandates stay valid and keep their hashes, even after their principal
  registers a key: the requirement applies to new mandates only.
- Callers that never register a key see no change (one new `principal_signature: null`
  field in the `create_mandate` result, two new null fields in the Proof Pack).
