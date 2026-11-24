# Action receipts: the receiver's line

Status: implemented (`record_action_receipt`, schema v13).

## Why

For each action an agent takes under a mandate, the registry already holds two lines:

1. **Authorization**: the action token it issued (`issue_action_token`, table
   `issued_tokens`). The registry checked the mandate, its perimeter and its whole
   delegation chain before signing it.
2. **Agent's declaration**: the action the agent logged (`log_action`), sealed to that
   token when the agent passes it (`action_log_tokens`).

Neither says what happened on the side of the system that received the action (a patient
record, an ERP, a payment service). Until now, what was done was known only through the
agent's own declaration. A receipt adds a third line, written by the receiver:

3. **Receiver's receipt**: the receiver received this token and executed the action, or
   refused it and why, and, if it wants, the SHA-256 of what it received.

## The tool

`record_action_receipt(token, audience, outcome, refusal_reason=None,
received_content_sha256=None)`, in the `receiver` profile (and `full`). Never in the
`agent` profile: a receipt the agent wrote about its own action would prove nothing.

| Input | Rule |
|---|---|
| `token` | A compact JWS this registry signed (EdDSA, this registry's key, its `iss`) and recorded in `issued_tokens`; the token's `jti`, mandate, action hash, audience and agent must match that record |
| `audience` | Must equal the token's `aud` |
| `outcome` | `executed` or `refused` |
| `refusal_reason` | 1 to 500 characters; required with `refused`, refused with `executed` |
| `received_content_sha256` | Optional, 64 lowercase hex |

Decisions:

- **One receipt per token.** A second one is refused (`receipt_already_recorded`); the
  primary key on `jti` also stops two concurrent calls.
- **After expiry.** The token's `exp` is not enforced, because a receiver acts inside the
  window and often records afterwards; `nbf` is. Past 7 days after `exp`, the receipt is
  refused (`receipt_too_late`).
- **Withdrawn or expired mandate.** Accepted. A receiver that refused an action because
  the mandate was withdrawn should be able to say so; the proof shows the withdrawal next
  to the receipt.
- **No registry.** If the database file does not exist, nothing is created
  (`registry_unavailable`).

Refusal codes: `invalid_input`, `malformed`, `wrong_algorithm`, `key_mismatch`,
`bad_signature`, `wrong_issuer`, `wrong_audience`, `token_not_yet_valid`,
`missing_claim`, `receipt_too_late`, `registry_unavailable`, `unknown_token`,
`token_record_mismatch`, `receipt_already_recorded`, `mandate_not_found` (the token's
mandate is gone from the registry), `internal_error`. They reach an MCP
client as errors, in the common shape (`code`, `message`, `field`).

## Storage and chaining

Table `action_receipts` (append-only): `jti` (primary key), `mandate_id`, `agent_id`,
`action_hash`, `audience`, `outcome`, `refusal_reason` (empty when executed),
`received_content_sha256`, `recorded_at`, `chain_hash`.

`chain_hash = compute_hash(data, previous)` where `previous` is the `chain_hash` of the
receipt recorded just before in the whole registry (`""` for the first) and `data` holds
the stored fields plus the `chain_hash` of the mandate. Existing mandates, tokens, actions
and their hashes are not modified.

## In the proof

`get_proof` adds `action_trail`: one entry per token issued under the mandate, plus one
per action logged without a token, oldest first:

```json
{"jti": "...",
 "authorization": {"issued_at": "...", "expires_at": "...", "audience": "...", "action_hash": "..."},
 "agent_declaration": {"action_id": "...", "timestamp": "...", "chain_hash": "..."},
 "receiver_receipt": {"outcome": "executed", "refusal_reason": null,
                      "received_content_sha256": "...", "recorded_at": "...",
                      "audience": "...", "chain_hash": "..."},
 "missing": []}
```

`missing` names the lines that are `null`. `chain_integrity.receipts_intact` is `null`
when the mandate has no receipt and the registry's receipt chain is whole, and `false`
when a receipt does not recompute from its row and the previous receipt, when it names a
token, action hash, agent or audience the registry did not issue under this mandate, or
when the receipt chain of the whole registry is broken. The whole chain is checked
because a receipt of this mandate may have been deleted: its successor, often a receipt
of another mandate, no longer recomputes, and every proof then says so. `chain_integrity.actions_with_receipt` counts
the receipts. `export_insurer_dossier` carries the entries of the period in
`action_trail` and `receipts_intact` in its integrity block.

## What a receipt is not

- It is what the receiver declares it did. It does not prove the content, and it does not
  prove that the action took place.
- It is not signed. Anyone who holds the token and can call this tool on the same
  registry could write it, and the first receipt recorded wins: if the agent reached a
  server with this tool first, the real receiver would get `receipt_already_recorded`.
  That is why it belongs to the receiver's profile only.
  A receipt signed with a key the receiver registered, verifiable without trusting the
  registry, is a separate step, not in this version.
- Deleting the very last receipt recorded in the whole registry is not detected by the
  chain alone (the same holds for the other chained tables). Any other deletion breaks
  the chain and shows as `receipts_intact: false` in every proof.
