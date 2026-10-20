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

Issued only if, at issuance time:

- the mandate exists, belongs to `agent_id`, has status `active` and is not expired;
- every mandate above it (delegation chain) is active and not expired;
- no principal signature in the chain is invalid or stripped (same check as the Proof
  Pack's `principal_signature_valid`; a mandate whose principal had no key is attested
  with `principal_signature: null`).

Otherwise: `{"denied": true, "reason": ..., "mandate_id": ...}` with `reason` one of
`invalid_input: ...`, `mandate_not_found`, `agent_mismatch`, `mandate_status_<status>`,
`mandate_expired`, `parent_mandate_not_found`, `parent_mandate_<status>`,
`parent_mandate_expired`, `delegation_chain_too_deep`, `principal_signature_invalid`;
`refused_by` names the parent mandate when the problem is above. A refusal writes
nothing.

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

`principal_signature` is `null` or `{signature, signed_at, key_id, public_key,
key_proof_signature, payload, algorithm}`: the principal's own Ed25519 signature over
`payload`, the exact bytes it signed (see `docs/principal-signature-spec.md`).
Mandate `metadata` is not included (labels, not sealed into the chain hash).

## 4. Verify offline (receiver)

```bash
python -m amr.verify_attestation attestation.jws --public-key registry.pub \
    [--audience seller:acme] [--issuer amr://registry.example] [--leeway 30]
```

Or in Python: `amr.attestation.verify_attestation(attestation, public_key_pem,
audience=..., issuer=...)`. No database, no network. Result:
`{"valid": true, "reason": "ok", "attestation": {...}}` or
`{"valid": false, "reason": "<code>", "detail": "..."}`; the command exits 0 if
valid, 1 if not, 2 if the public key cannot be read.

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
   each parent's parent, ending at a root); every level is `active` and `exp` is not
   after any level's `expires_at`.
7. Principal signature, when present (`principal_signature_invalid`): `key_id` is the
   key id of `public_key`; the signature verifies over `payload`; the payload's
   `context` (`amr.mandate.v1`), `principal_id`, `agent_id`, `scope`, `legal_basis`,
   `parent_mandate_id` and `signed_at` equal the mandate's, and for a root mandate its
   `perimeter` too.

## 5. Not to be confused with action tokens

An action token authorizes one action at one audience; an attestation describes a
mandate. They share the registry key, so each side refuses the other: the attestation
verifier requires `typ: amr-attestation+jwt` and `amr_attestation`; action-token
consumers must check `amr_action_hash` (see `docs/token-issuance-spec.md`), which an
attestation does not carry.

## Known limits

- **Status at issuance, not now.** The receiver learns that the chain was active at
  `iat`. A revocation made later reaches it only when the attestation expires (15
  minutes by default). For an important act, ask the agent for a fresh attestation,
  with a short `lifetime_seconds` and your `audience`.
- **Bearer document.** Whoever holds the attestation can show it. It names the agent
  (`sub`), but proving that the party in front of you is that agent is outside v1.
- **Trust in the registry key.** The receiver trusts the operator's key. The
  principal's own signature, when present, can be re-checked independently of the
  registry; it proves possession of the key first registered for that `principal_id`,
  not a verified identity (see `docs/principal-signature-spec.md`).
- **Parents' principal signatures** are checked by the registry at issuance but not
  carried in the attestation (only the mandate's own is).
- **Not a legal opinion.** The attestation states facts recorded in the registry; what
  they are worth to a receiver is a legal question outside this document.
