# Registry timestamps (RFC 3161)

Status: implemented (`prepare_registry_timestamp`, `record_registry_timestamp`, schema v14).

## Why

A registry kept by its operator is evidence the operator could rewrite. The SHA-256
chains of AMR show an edit to a row only as long as nobody recomputes every hash after
it. An outside time-stamping authority (TSA) chosen by the operator closes that gap: it
signs a digest of the registry together with its own date. Anyone with a copy of the
registry database can later check that it held exactly these rows at that date. The
Proof Pack alone lets a third party check that the service signed and dated an anchor,
not that a given mandate's rows are inside it: the anchor's digests cover whole tables.

What a timestamp shows: the registry held these rows, in this state, at the service's
date. What it does not show: that what the rows say is true, or who wrote them.

## No network call

AMR never contacts a time-stamping service. There is no address setting and none built
in. The operator sends the request with their own tools (for example
`curl -H "Content-Type: application/timestamp-query" --data-binary @req.tsq <url>`) and
gives the response back. Only a SHA-256 digest leaves the registry.

## Anchor (version 1)

```json
{"anchor_version": 1,
 "computed_at": "<ISO 8601, UTC>",
 "nonce": <random integer, 0 <= n < 2^63>,
 "tables": {"<table>": {"last_rowid": <int>, "rows": <int>, "sha256": "<hex>"}, ...}}
```

Tables, each with a fixed list of columns (`ANCHOR_V1_COLUMNS` in
`src/amr/registry_timestamp.py`): `mandates`, `action_logs`, `mandate_events`,
`mandate_revocations`, `issued_tokens`, `principal_keys`, `issued_attestations`,
`token_amounts`, `action_contests`, `principal_key_domain_proofs`,
`mandate_pdf_signatures`, `action_log_tokens`, `token_validations`, `action_receipts`.

For a table: take the rows with `rowid <= last_rowid`, in rowid order. For each row,
`line = JSON([rowid, col1, col2, ...])`: separators `,` and `:` with no spaces; every
non-ASCII character escaped as `\uXXXX` (lowercase hex, surrogate pairs above U+FFFF:
Python `json.dumps` with `ensure_ascii=True`); integers in decimal; NULL as `null`; a
BLOB as `{"hex":"<lowercase hex>"}`.
`sha256 = SHA-256(SHA-256(line_1) || SHA-256(line_2) || ...)`. `rows` is the number of
lines. The anchor's digest is SHA-256 of the anchor as canonical JSON (sorted keys,
separators `,` and `:`, UTF-8). All tables are read in one transaction.

A later schema that adds a column keeps the version 1 list, so an old anchor is
re-checked on the columns it covered.

## Request

An RFC 3161 `TimeStampReq`, version 1, message imprint SHA-256 of the anchor's digest
input (the canonical JSON), `nonce` = the anchor's nonce, `certReq` true. Returned DER,
base64.

## Checks before recording

`record_registry_timestamp(anchor_json, timestamp_response)` records the response only
if, in this order:

1. the anchor has exactly the version 1 shape (`anchor_invalid` otherwise);
2. `AMR_TIMESTAMP_TRUST_ROOTS_PATH` names a readable PEM file
   (`timestamp_trust_roots_missing`);
3. the response is a `TimeStampResp` with status `granted` or `granted_with_mods`
   (`timestamp_malformed`, `timestamp_not_granted`);
4. its `TSTInfo` message imprint is SHA-256 and equals the anchor's digest
   (`timestamp_imprint_mismatch`), and its nonce is the anchor's nonce
   (`timestamp_nonce_mismatch`);
5. its `genTime` is not earlier than the anchor's `computed_at` by more than 300 seconds
   (`timestamp_before_anchor`);
6. it has one signer whose certificate it carries, the CMS signature verifies, and the
   certificate chains to one of the operator's roots at `genTime`
   (`timestamp_signature_invalid`, `timestamp_signer_not_trusted`); no revocation is
   checked and nothing is fetched;
7. inside one write transaction, the registry still holds exactly the anchored rows
   (`anchor_mismatch`), and no timestamp is recorded for this anchor yet
   (`timestamp_already_recorded`).

## Storage

Table `registry_timestamps` (append-only): `anchor_sha256` (primary key), `anchor_json`
(canonical), `response_der`, `gen_time`, `tsa` (signer subject), `serial_number`,
`policy`, `trust_roots_sha256`, `recorded_at`, `chain_hash`.
`chain_hash = compute_hash({anchor_sha256, response_sha256, gen_time, tsa,
serial_number, policy, trust_roots_sha256, recorded_at}, previous chain_hash)`, the
first one chained to `""`.

## In the Proof Pack

`get_proof` lists in `registry_timestamps` every recorded timestamp whose anchor covers
the mandate (the mandate's rowid is at most the anchored `mandates.last_rowid`), each
re-checked now: `anchor_intact`; `response_matches` (the stored response dates the
stored anchor with its nonce and agrees with the stored columns, checked without trust
roots); `signature_valid` (`null` without trust roots, `false` if the roots file cannot
be read); with `actions_covered`, the response (base64) and the anchor. `gen_time`,
`tsa` and `serial_number` are read from the signed response, never from the columns.
`chain_integrity.timestamps_intact` is `null` when no timestamp covers the mandate and
the chain is whole, `false` when a covering anchor no longer matches, a response does not
match, a signature no longer verifies, a stored anchor is malformed or no longer hashes to
its key, or the timestamp chain is broken, `true` otherwise.

## Limits

- Rows written after the last timestamp are not covered until the next one.
- AMR does not say whether a service is qualified under eIDAS: that is the operator's
  choice of trust roots.
- No revocation check of the service's certificate.
- The registry's own `registry_timestamps` table is not in the anchor; it is chained,
  but deleting its latest row is not detected (as for the end of any chain).
- Without trust roots at `get_proof` time, the operator who edits the registry could
  also rebuild a stored anchor and its chain; the stored response would then no longer
  date that anchor (`response_matches` false). A forged response needs the service's
  key, which only the signature check against trusted roots rules out.
- The anchor follows SQLite rowids. Do not run `VACUUM` on a registry that has
  timestamps: SQLite may renumber the rowids of tables without an INTEGER PRIMARY KEY,
  and the anchors would then show as broken (a false alarm, never a false "intact").

## Compatibility

Additive. Existing mandates, actions, tokens and their hashes do not change. Schema v14
only creates `registry_timestamps`. An older AMR version ignores the table.
