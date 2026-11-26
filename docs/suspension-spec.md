# Mandate suspension

Status: v1 (schema v15). A pause that the principal can lift, next to revocation, which
stays final. Asked by a consultant in agent security (23 and 25/11/2026): cutting must
be easier than granting, with a key designated in advance.

## Who may suspend, who may resume

- **Suspend**: only a key the mandate designates. The principal lists, in
  `create_mandate`, up to five Ed25519 public keys (`suspension_keys`, base64url): a
  security officer, an on-call person. Any one of them suspends alone. The list is part
  of the structured perimeter, so it is sealed in the mandate's `chain_hash` and covered
  by the principal's signature when the mandate is signed. It needs `allowed_actions`.
- **Resume**: only the mandate's own principal, with `resume_mandate`. Same signature
  policy as `revoke_mandate`: signed when the principal has a registered key; with
  `AMR_REQUIRE_PRINCIPAL_SIGNATURE=true`, always signed; otherwise an unsigned
  resumption is accepted, so expose `resume_mandate` to principals only. A key holder
  cannot lift the suspension it made.
- A mandate without `suspension_keys` keeps its exact perimeter, hash and behaviour,
  and cannot be suspended (`suspension_not_designated`); its principal can still revoke
  it.
- Sub-mandates do not inherit the keys: suspending a mandate already cuts every
  sub-mandate below it. A sub-mandate may designate its own keys.

## Signed payloads

Canonical JSON (sorted keys, no whitespace, UTF-8), built by
`prepare_suspension_signature(mandate_id, action, reason, public_key="", signed_at=None)`:

```json
{"action":"suspend","context":"amr.suspension.v1","key_id":"...","mandate_id":"...","principal_id":"...","reason":"...","signed_at":"2026-11-26T21:30:00+00:00"}
```

`action` is `suspend` (signed by the designated key, whose `key_id` is in the payload)
or `resume` (signed by the principal's registered key). `signed_at` must be within
`AMR_PRINCIPAL_SIGNATURE_MAX_AGE_SECONDS` (default 900) of the registry clock. A
signature binds the action, the mandate, the principal, the reason and the key: it
cannot be reused for another mandate, another reason or the other action, and a
signature is recorded once (`suspension_signature_replayed`,
`principal_signature_replayed`).

## What is recorded

Nothing is updated in place. Each suspension or resumption appends:

- one row to `mandate_suspensions` (`action` = `suspend` or `resume`, reason, time,
  key id, public key, signature, signed payload), chained with SHA-256 to the previous
  row of that table and anchored to the mandate's own `chain_hash`;
- one `suspended` or `resumed` row to `mandate_events`.

The latest row of a mandate says whether the suspension is in force. The `mandates`
row keeps its stored status.

## Effect while suspended

| Reader | Effect |
|---|---|
| `issue_action_token`, `issue_mandate_attestation` | `{"denied": true, "reason": "mandate_status_suspended"}`; on a sub-mandate below, `parent_mandate_suspended` |
| `check_action_token` | `valid: false`, `mandate_status_suspended` or `parent_mandate_suspended` |
| `log_action` | refused, `mandate_status_suspended` (below: `parent_mandate_suspended`) |
| `verify_mandate` | without `mandate_id`, the suspended mandate is skipped (an older valid mandate of the agent, if any, is returned); with it, `authorized: false`, `Mandate suspended` |
| `create_mandate` with it as parent | `parent_mandate_suspended` |
| `get_proof` | `mandate.status = "suspended"` (stored value in `mandate.stored_status`), `mandate.suspension`, the history in `suspensions`, `chain_integrity.suspensions_valid` |
| `export_insurer_dossier` | not in force, `mandate_suspended`; its branch is cut |
| public registry export | `recorded_status: "suspended"`, so a verifier answers `inactive`, `mandate_suspended` (below: `parent_mandate_suspended`) |

A revoked mandate cannot be suspended or resumed (`mandate_already_revoked`): its
status stays `revoked`.

`suspensions_valid` is `null` when the mandate was never suspended, and `true` only if
the records alternate (suspend, resume, ...), each `chain_hash` recomputes, each
suspension is signed by a key the mandate designates, each resumption is signed by the
principal's registered key (or unsigned while it had none), and every `suspended` and
`resumed` event still has its record.

## Errors

`invalid_input`, `mandate_not_found`, `mandate_already_revoked`,
`mandate_already_suspended`, `mandate_not_suspended`, `suspension_not_designated`,
`suspension_key_not_designated`, `suspension_signature_invalid`,
`suspension_signature_replayed`, `public_key_invalid`, and the principal signature codes
of `revoke_mandate` (`principal_signature_required`, `principal_signature_incomplete`,
`principal_signature_invalid`, `principal_signature_stale`,
`principal_key_not_registered`, `principal_signature_replayed`, `signed_at_invalid`).

## Known limits

- Tokens and attestations already issued are signed JWS: they stay valid until their
  `exp` for a receiver that does not re-check with `check_action_token`, as after a
  revocation.
- The registry checks that the key is designated and that it signed; it does not know
  who holds the key. Designating a key is the principal's decision.
- Lifting a suspension needs the principal alone; a resumption by two key holders
  together is not implemented.
- The anchor of a registry timestamp (`prepare_registry_timestamp`, anchor format v1)
  does not cover `mandate_suspensions`.
- A row deleted from `mandate_suspensions` lifts the suspension for every reader;
  `get_proof` then shows `suspensions_valid: false` (the event remains), and deleting a
  row of another mandate breaks the recomputed chain of the next one.
- A public registry snapshot is a photograph: a suspension made after `generated_at` is
  not shown until the next export.
