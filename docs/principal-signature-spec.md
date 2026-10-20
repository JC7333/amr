# Principal signatures on mandates

Status: v1 (schema v4). First step towards answering "who really granted this mandate?".

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

**Limit: first registration wins.** The registry does not check who registers a key for
a given `principal_id`. Expose `register_principal_key` to principals (or their back
office) only, never to agents, and register each principal's key when the principal is
onboarded. Binding the key to a verified identity (eIDAS wallet, qualified certificate)
is a later step.

Errors: `principal_id_invalid`, `public_key_invalid`, `principal_signature_invalid`
(malformed proof), `principal_key_proof_invalid`, `principal_key_already_registered`.

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

## 5. Known limits

- **First registration wins** (section 1): the key is not bound to a verified identity.
- **Per-registry replay protection**: a signature is refused if it already registered a
  mandate in the same database. The payload names no registry, so within the 15-minute
  window the same signed payload could be accepted by another AMR registry where the
  same key is registered. The registration proof does not expire.
- **Identifiers are compared exactly**: `user:victim` and `user:victim ` (trailing space)
  or Unicode look-alikes are different principals. The signature rule protects the exact
  `principal_id` that registered a key.
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

- Existing databases are migrated in place (schema v4): four nullable columns on
  `mandates`, a new `principal_keys` table, a unique index on the signature. No existing
  row is modified.
- Existing mandates stay valid and keep their hashes, even after their principal
  registers a key: the requirement applies to new mandates only.
- Callers that never register a key see no change (one new `principal_signature: null`
  field in the `create_mandate` result, two new null fields in the Proof Pack).
