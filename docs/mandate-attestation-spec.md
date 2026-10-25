# Mandate attestations: third-party verification without an account

Status: v1 (`amr_attestation: "mandate.v1"`, schema v5).

The question it answers: when an agent arrives at a seller, a hospital or an insurer
and says "I act for X", how does the receiver check it, alone, without an account at
the registry and without calling it?

The agent asks the registry for an **attestation** of its mandate and shows it. The
receiver verifies it offline with the registry's public key, obtained once.

## 1. Get the registry's public key: `get_registry_public_key`

No parameters. Returns:

```json
{
  "issuer": "amr://localhost",
  "key_id": "3aefdd8e4e99821e",
  "algorithm": "EdDSA",
  "public_key_pem": "-----BEGIN PUBLIC KEY-----\n...",
  "public_key_jwk": {"kty": "OKP", "crv": "Ed25519", "x": "...", "kid": "...", "alg": "EdDSA"}
}
```

This is the same key that signs action tokens (`amr_signing_key.pub`); only the public
half is returned. **Trust:** the receiver fetches it once, through a channel it trusts
(the operator's website, a contract annex), and compares `key_id` with the one the
operator publishes. Whoever controls the key the receiver trusts controls what it
accepts. Key rotation is not in v1.

## 2. Issue an attestation: `issue_mandate_attestation`

| Parameter | Description |
|---|---|
| `mandate_id` | UUID of the mandate to attest |
| `agent_id` | Must match the mandate's `agent_id` |
| `audience` | Optional: the receiver it is addressed to (e.g. `"seller:acme"`) |
| `lifetime_seconds` | Optional: a shorter lifetime; it never extends the maximum |
| `include_principal_payload` | Optional, default `false`: also carry the principal's signature and the exact bytes it signed, so the receiver re-checks it without trusting the registry. Those bytes contain the mandate `metadata`, which is then disclosed to the receiver |

Issued only if, at issuance time:

- the mandate exists, belongs to `agent_id`, has status `active`, is not expired and is not revoked (`revoke_mandate`);
- every mandate above it (delegation chain) is active, not expired and not revoked;
- no principal signature in the chain is invalid or stripped (same check as the Proof
  Pack's `principal_signature_valid`; a mandate whose principal had no key is attested
  with `principal_signature: null`).

Otherwise: `{"denied": true, "reason": ..., "mandate_id": ...}` (`mandate_id` is
`null` for invalid input) with `reason` one of `invalid_input: ...`, `mandate_not_found`, `agent_mismatch`, `mandate_status_<status>`,
`mandate_status_revoked`, `mandate_expired`, `parent_mandate_not_found`,
`parent_mandate_<status>`, `parent_mandate_revoked`,
`parent_mandate_expired`, `delegation_chain_too_deep`, `principal_signature_invalid`;
`refused_by` names the parent mandate when the problem is above; an unexpected error
gives `internal_error: ...`. A refusal writes nothing.

Lifetime: `exp` is the earliest of now + lifetime (at most
`AMR_ATTESTATION_LIFETIME_SECONDS`, default 900), the mandate's `expires_at` and every
parent's `expires_at`, rounded down to the second.

Success: `{"attestation", "jti", "issued_at", "expires_at", "key_id", "issuer"}`. Each
issuance is appended to the `issued_attestations` table (jti, mandate, agent, audience,
times, key id, SHA-256 of the claims). Nothing else is written; mandates and their
hashes are untouched.

## 3. Format

JWS Compact Serialization (RFC 7515), Ed25519 (EdDSA, hardcoded on both sides).

Header: `{"alg": "EdDSA", "typ": "amr-attestation+jwt", "kid": "<key_id>"}`.

Claims:

| Claim | Content |
|---|---|
| `iss` | The registry (`AMR_TOKEN_ISSUER`) |
| `sub` | The agent (`amr_mandate.agent_id`) |
| `aud` | Only if `audience` was given |
| `iat`, `nbf` | Issuance time: the moment the status was checked |
| `exp` | See lifetime above |
| `jti` | Unique id of this attestation |
| `amr_attestation` | `"mandate.v1"` |
| `amr_mandate` | `id`, `principal_id`, `agent_id`, `scope`, `legal_basis`, `status` (`"active"`), `created_at`, `expires_at`, `parent_mandate_id`, `perimeter` (canonical, or `null`), `perimeter_digest` (SHA-256 of the canonical perimeter JSON, as in action tokens, or `null`), `chain_hash`, `principal_signature` |
| `amr_chain` | The parent mandates, nearest first, up to the root: `id`, `principal_id`, `agent_id`, `status`, `expires_at`, `parent_mandate_id`, `perimeter_digest` |

`principal_signature` is `null` (unsigned mandate) or, by default,
`{key_id, public_key, signed_at, algorithm}`: the registry checked the signature at
issuance and vouches for it. With `include_principal_payload`, it is
`{signature, signed_at, key_id, public_key, key_proof_signature, payload, algorithm}`:
the principal's own Ed25519 signature over `payload`, the exact bytes it signed (see
`docs/principal-signature-spec.md`), which the receiver re-checks.

Mandate `metadata` (labels, possibly personal data) is not in `amr_mandate`. It is
inside the signed `payload`, so it reaches the receiver only with
`include_principal_payload`.

`chain_hash` is informational: it lets someone who also holds the registry's Proof
Pack match the two. The receiver cannot re-check it offline.

## 4. Verify offline (receiver)

```bash
python -m amr.verify_attestation attestation.jws --public-key registry.pub \
    [--audience seller:acme] [--issuer amr://registry.example] [--leeway 30]
```

`--public-key` takes the PEM, or the JSON returned by `get_registry_public_key`.
Or in Python: `amr.attestation.verify_attestation(attestation, public_key_pem,
audience=..., issuer=...)`. No database, no network. Result:
`{"valid": true, "reason": "ok", "attestation": {...}}` or
`{"valid": false, "reason": "<code>", "detail": "..."}`; the command exits 0 if
valid, 1 if not (an unusable key gives `public_key_invalid`), 2 if the key file
cannot be read. The summary says `principal_signed` and
`principal_signature_rechecked` (true only when the receiver re-checked the
principal's signature itself).

Checks, in this order (another implementation MUST do all of them):

1. Header: `alg` is `EdDSA` (`wrong_algorithm`), `typ` is `amr-attestation+jwt`
   (`not_an_attestation`), `kid` is the key id of the trusted key (`key_mismatch`).
2. Ed25519 signature with the trusted key (`bad_signature`).
3. `iss` equals the expected registry, when you expect one (`wrong_issuer`).
4. Audience: an attestation that carries `aud` is accepted only by a receiver that
   names that audience; a receiver that names an audience refuses one without `aud`
   (`wrong_audience`).
5. `iss`, `sub`, `iat`, `nbf`, `exp`, `jti` present, times are integers,
   `amr_attestation` is `mandate.v1` (`claims_invalid`, `not_an_attestation`);
   `nbf <= now` (`not_yet_valid`) and `now < exp` (`expired`), within the leeway.
6. Content (`claims_invalid`): `sub` equals the mandate's agent; `perimeter_digest`
   matches the perimeter; the chain is complete and in order (mandate's parent, then
   each parent's parent, ending at a root); each mandate's `principal_id` is the
   `agent_id` of the mandate above it; every level is `active` and `exp` is not after
   any level's `expires_at`.
7. Principal signature, when present (`principal_signature_invalid`): `key_id` is the
   key id of `public_key`. When `payload` is carried: the signature verifies over
   `payload`; `key_proof_signature`, when present, verifies over the key registration
   payload; the payload's `context` (`amr.mandate.v1`), `principal_id`, `agent_id`,
   `scope`, `legal_basis`, `parent_mandate_id` and `signed_at` equal the mandate's,
   its `duration_hours` equals `expires_at - created_at` (within a second), and for a
   root mandate its `perimeter` equals the mandate's.

These content checks catch an inconsistent attestation even when the registry signed
it. They cannot catch a consistent false one: the registry key vouches for the facts
(see Known limits).

## 5. Not to be confused with action tokens

An action token authorizes one action at one audience; an attestation describes a
mandate. They share the registry key, so each side refuses the other: the attestation
verifier requires `typ: amr-attestation+jwt` and `amr_attestation`; action-token
consumers must check `amr_action_hash` (see `docs/token-issuance-spec.md`), which an
attestation does not carry.

## Known limits

- **Status at issuance, not now.** The receiver learns that the chain was active at
  `iat`. A revocation made later (`revoke_mandate`) reaches it only when the attestation expires (15
  minutes by default). For an important act, ask the agent for a fresh attestation,
  with a short `lifetime_seconds` and your `audience`.
- **Bearer document.** Whoever holds the attestation can show it. It names the agent
  (`sub`), but proving that the party in front of you is that agent is outside v1.
- **Trust in the registry key.** The receiver trusts the operator's key. The
  principal's own signature, when present, can be re-checked independently of the
  registry; it proves possession of the key first registered for that `principal_id`,
  not a verified identity (see `docs/principal-signature-spec.md`).
- **The registry trusts its own database.** At issuance, principal signatures are
  re-checked, but the mandate's `chain_hash` is not recomputed: someone who can write
  to the database file can change an unsigned mandate (scope, perimeter, expiry) or
  any mandate's status, and the registry will attest the changed row. The same holds
  for action tokens today. Protect the database file; for a signed mandate, ask for
  `include_principal_payload` to re-check the principal's signature yourself.
- **What the receiver can re-check without the registry** is limited to the
  principal's signature, when carried: principal, agent, scope, legal basis, duration
  and, for a root mandate only, the perimeter. A sub-mandate's effective perimeter
  (narrowed by its parents) and the parents' principal signatures are checked by the
  registry at issuance but not carried in the attestation.
- **Not a legal opinion.** The attestation states facts recorded in the registry; what
  they are worth to a receiver is a legal question outside this document.
