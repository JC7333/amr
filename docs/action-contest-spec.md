# Contested actions

Status: v1 (schema v8). What the registry records when the principal disputes an act
the agent has already performed, and how the response deadline is reminded.

## Why

Revocation (`docs/revocation-spec.md`) stops what an agent does next. It says nothing
about an act already performed. When the principal finds out after the fact that an act
was not wanted, the registry should hold a dated trace that the act was disputed, and
the principal needs a reminder before its own response deadline passes.

## What it does

`contest_action(mandate_id, action_id, reason, response_days, contested_by=None,
principal_signature=None, signed_at=None)` appends:

- one row to `action_contests` (primary key `action_id`: one contest per logged
  action, final, no withdrawal, no edit), chained with SHA-256 to the previous contest
  and anchored to both the mandate's `chain_hash` and the contested action's
  `chain_hash`;
- one `action_contested` row to `mandate_events`, whose reason starts with
  `action <action_id>:`.

Nothing else changes: the `action_logs` row, the mandate, its hash and its status stay
as they are; tokens and attestations follow their usual rules. To stop the agent, call
`revoke_mandate` as well.

## Who may contest

The mandate's own principal (default), or the principal of any mandate above it in the
delegation chain, whatever the status of those mandates: an organization can dispute
what a sub-agent did under a sub-mandate it delegated, even after cutting the branch.
Anyone else gets `contester_not_in_chain`.

Signature policy, identical to `create_mandate` and `revoke_mandate`, applied to the
contesting principal:

| Contesting principal | Contest |
|---|---|
| has a registered key | must be signed (`principal_signature_required` otherwise) |
| no key, `AMR_REQUIRE_PRINCIPAL_SIGNATURE=true` | must be signed |
| no key, default settings | may be unsigned |

The signed payload (`prepare_contest_signature`) is the canonical JSON of
`{context: "amr.action_contest.v1", mandate_id, action_id, contested_by, reason,
response_days, signed_at}`. `signed_at` must be within
`AMR_PRINCIPAL_SIGNATURE_MAX_AGE_SECONDS` of the registry clock; a signature records
one contest only (`principal_signature_replayed`, a defensive check: the payload names
the action, so a replayed signature meets `action_already_contested` first).
`prepare_contest_signature` also refuses an action already contested.

## The response deadline

`respond_by = contested_at + response_days` (1 to 365 days). The delay is chosen by
the operator, for example the one its counsel gives before keeping or using what was
ordered could be read as accepting the act. AMR computes no legal deadline, asserts
none, and does not say what happens when it passes.

`list_action_contests(mandate_id=None, contested_by=None, due_within_days=None)` is the
reminder. Read-only; `mandate_id`, `contested_by` or both must be given. It returns the
contests nearest `respond_by` first, each with
`reminder = {respond_by, days_left, deadline_passed}` (`days_left` in whole days,
negative once passed). `due_within_days` keeps the contests due within that many days,
including those already passed. At most 500 are returned (`truncated: true` beyond).

## In the Proof Pack

`get_proof` adds `action_contests` (oldest first, each with
`principal_signature_valid`: `null` when unsigned and the contesting principal had no
key at the time, `false` when the signature does not verify or is missing although
the principal had a key) and `chain_integrity.contests_intact`, false when:

- an `action_contested` event has no contest record, or a contest record has no
  event (one of the two was deleted);
- a contest's `chain_hash` does not recompute from its row, the mandate's
  `chain_hash` and the `chain_hash` of the contest recorded just before it in the
  registry (a field was edited, or a contest was removed from the middle);
- a contest names an action that is not in this mandate's log, or whose `chain_hash`
  differs from the one recorded at contest time;
- a contest signature does not verify.

## Compatibility

Schema v8 only adds a table and two indexes. Existing mandates, action logs and their
hashes are unchanged. The Proof Pack gains two keys (`action_contests`, empty when
nothing is contested, and `chain_integrity.contests_intact`); `proof_pack_version`
stays `0.1.0` because nothing is removed or renamed. `events` and `total_events` now
also count `action_contested` events: a consumer that read every event as a status
change must skip this type. The insurer dossier gains `integrity.contested_actions`
and `integrity.contests_intact`.

## Known limits

- A contest is a record, not a remedy: it does not undo the act, notify the
  counterparty or decide who bears a loss.
- The contest chain proves the order and integrity of contests as long as the registry
  database is not rewritten as a whole; like every other table, the registry trusts
  its own file. Deleting the newest contest of the whole registry together with its
  event leaves no trace in the chain (nothing comes after it to break).
- Concurrent contests are serialized by a write transaction (`BEGIN IMMEDIATE`), so
  two of them never chain to the same previous hash.
- There is no "resolved" state yet: the outcome of a dispute is kept outside AMR.
- The reminder is a query: AMR sends nothing by itself (no network call); the operator
  schedules `list_action_contests`.
