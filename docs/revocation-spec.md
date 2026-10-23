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
| `get_proof` | `mandate.status = "revoked"`, `mandate.revocation`, `chain_integrity.revocation_signature_valid` |
| `export_insurer_dossier` | not in force, `mandate_revoked`; its whole branch is cut |

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
`signed_at_invalid`.

## How fast

- Every check made after `revoke_mandate` returns sees the revocation: no new token,
  no positive `verify_mandate`, no new sub-mandate, for the mandate and its whole branch.
- Action tokens already issued are signed JWS: they cannot be called back. A consumer
  that checks only the signature accepts them until their `exp`. The response says
  exactly how many are still valid and until when (`outstanding_tokens.still_valid`,
  `outstanding_tokens.last_expires_at`), counting the mandate and its sub-mandates. The
  default token lifetime is `AMR_TOKEN_LIFETIME_SECONDS` = 300 seconds.

## Known limits

- `issue_action_token` still accepts `lifetime_override_seconds` from its caller, with
  no upper bound: a token asked with a long lifetime outlives a revocation by as much.
  Bounding token lifetime by the mandate's expiry, and removing that parameter from what
  agents can call, is a separate, queued change.
- An unsigned revocation proves nothing about who revoked; a principal that registers
  its key afterwards does not make it signed (`revocation_signature_valid` stays null).
- There is no revocation list for consumers: a token consumer that wants revocation
  faster than `exp` must ask the registry (`verify_mandate`) before acting.
