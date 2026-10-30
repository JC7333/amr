# Mandate revocation

Status: v1 (schema v6). The principal's stop button: what triggers a revocation, who
may trigger it, and how fast it takes effect.

## What it does

`revoke_mandate(mandate_id, reason, principal_signature=None, signed_at=None)` records
a revocation. It is final: there is no "unrevoke". To grant the agent authority again,
create a new mandate.

Nothing is updated in place. The registry appends:

- one row to `mandate_revocations` (one per mandate at most, enforced by its primary
  key), chained with SHA-256 to the previous revocation, and anchored to the revoked
  mandate's own `chain_hash`;
- one `revoked` row to `mandate_events`, so the Proof Pack and the insurer dossier list
  it with the other status events.

The `mandates` row keeps `status = 'active'` (append-only rule). Every reader treats a
mandate with a revocation row as revoked:

| Reader | Effect of a revocation |
|---|---|
| `issue_action_token` | `{"denied": true, "reason": "mandate_status_revoked"}` |
| `issue_action_token` on any sub-mandate below | `parent_mandate_revoked`, `refused_by` = the revoked mandate |
| `verify_mandate` | the revoked mandate is skipped (an older unrevoked mandate of the same agent, if any, is returned) |
| `create_mandate` with it as parent | `parent_mandate_revoked` |
| `issue_mandate_attestation` | `{"denied": true, "reason": "mandate_status_revoked"}` |
| `issue_mandate_attestation` on any sub-mandate below | `parent_mandate_revoked`, `refused_by` = the revoked mandate |
| `log_action` | refused: no action is logged after the revocation |
| `log_action` on any sub-mandate below | refused, `reason` = `parent_mandate_revoked`, `refused_by` = the revoked mandate |
| `get_proof` | `mandate.status = "revoked"` (the stored value stays in `mandate.stored_status`), `mandate.revocation`, `chain_integrity.revocation_signature_valid` |
| `get_proof` on any sub-mandate below | `delegation_chain = {"broken": true, "reason": "parent_mandate_revoked", "refused_by": <the revoked mandate>}`; the sub-mandate's own `mandate.status` is unchanged |
| `export_insurer_dossier` | not in force, `mandate_revoked`; its whole branch is cut; `status.stored_status` keeps the stored value; `integrity.revocation_signature_valid` |

## What triggers it, and who

A revocation is a decision of the mandate's own principal, with a reason it states
(1 to 500 characters, kept in the registry and the Proof Pack). For a sub-mandate the
principal is the agent that delegated it; the root principal cuts a whole branch by
revoking the root.

Same signature policy as `create_mandate`:

- the principal has a registered key (`register_principal_key`): the revocation must
  carry its Ed25519 signature, otherwise `principal_signature_required`;
- `AMR_REQUIRE_PRINCIPAL_SIGNATURE=true`: every revocation must be signed;
- otherwise an unsigned revocation is accepted, so anyone who can call the tool can
  revoke. Expose `revoke_mandate` to principals (or their back office), like
  `create_mandate`.

Signed payload (canonical JSON, sorted keys, no whitespace, UTF-8), built by
`prepare_revocation_signature`:

```json
{"context":"amr.revocation.v1","mandate_id":"...","principal_id":"...","reason":"...","signed_at":"2026-10-23T20:30:00+00:00"}
```

`signed_at` must be within `AMR_PRINCIPAL_SIGNATURE_MAX_AGE_SECONDS` (default 900) of
the registry clock. The signature binds the mandate, the principal and the reason: it
cannot be reused for another mandate or another reason, and a mandate can be revoked
only once.

Errors: `invalid_input`, `mandate_not_found`, `mandate_already_revoked`,
`principal_signature_required`, `principal_signature_incomplete`,
`principal_signature_invalid`, `principal_signature_stale`, `principal_key_not_registered`,
`principal_signature_replayed`, `signed_at_invalid`.

`revocation_signature_valid` in the Proof Pack is `true` when the stored signature
matches the principal's registered key (itself re-checked) and this mandate, principal
and reason; `false` when it does not, when the signature was stripped although the
principal had a key at revocation time, or when a `revoked` event remains without its
revocation record (record deleted); `null` otherwise.

## How fast

- Every check made after `revoke_mandate` returns sees the revocation: no new token,
  no new attestation, no positive `verify_mandate`, no new sub-mandate, no new entry in
  the action journal (`log_action`), for the mandate and its whole branch.
- Action tokens already issued are signed JWS: they cannot be called back. A consumer
  that checks only the signature accepts them until their `exp`. The response says
  exactly how many are still valid and until when (`outstanding_tokens.still_valid`,
  `outstanding_tokens.last_expires_at`), counting the mandate and its sub-mandates. The
  default token lifetime is `AMR_TOKEN_LIFETIME_SECONDS` = 300 seconds. A consumer
  that re-checks the token with `check_action_token` when it acts gets
  `valid: false` (`mandate_status_revoked` or `parent_mandate_revoked`) as soon as the
  revocation is recorded; a risk class with `registry_check` asks it to (see
  `docs/token-issuance-spec.md`, Registry Check at Execution).
- Mandate attestations already issued (`issue_mandate_attestation`) are signed JWS too:
  a receiver that checks them offline accepts them until their `exp`. The default
  attestation lifetime is `AMR_ATTESTATION_LIFETIME_SECONDS` = 900 seconds. They are not
  counted in the `revoke_mandate` response (see Known limits).

## Known limits

- The `revoke_mandate` response counts outstanding action tokens only, not mandate
  attestations still within their lifetime (`issued_attestations`).
- A token lives at most `AMR_TOKEN_LIFETIME_SECONDS` (default 300 s) after it is issued,
  and never past the expiry of its mandate or of any mandate above it in the chain.
  `lifetime_override_seconds` can only shorten it. A token issued before a revocation
  stays valid until that expiry: the window after a revocation is at most one token
  lifetime, it does not add up along a chain of delegations (each token carries its own
  expiry, none is renewed by another).
- An unsigned revocation proves nothing about who revoked; a principal that registers
  its key afterwards does not make it signed (`revocation_signature_valid` stays null).
- `verify_mandate` looks only at the agent's most recent active, unexpired, unrevoked
  mandate: if that one is a sub-mandate under a revoked parent, it answers "chain
  broken" even when the agent holds another, older valid mandate.
- Two revocations written at the same instant by two processes could chain to the same
  previous hash (no exclusive transaction), as for the other chains of the registry.
- There is no revocation list for consumers: a token consumer that wants revocation
  faster than `exp` must ask the registry (`verify_mandate`) before acting.
