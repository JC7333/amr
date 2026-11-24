# Token Issuance Specification v1.5

v1.5 (24/11/2026): a perimeter may require a human validation for some action types
(`validation_actions`); the token then carries `amr_validation_required`,
`amr_validated_by` and `amr_validated_content_sha256`. Tokens for other actions, and
all tokens under mandates without it, are unchanged.
v1.4 (22/11/2026): `log_action` may log an action under its token (`action_token`),
and an operator may require it (`AMR_REQUIRE_ACTION_TOKEN_FOR_LOG`). Tokens and
their claims are unchanged.
v1.3 (29/10/2026): a risk class may require a registry check at execution
(`registry_check`, claim `amr_registry_check`, tool `check_action_token`).
v1.2 (28/10/2026): risk classes bound the token lifetime by action type.
v1.1 (14/10/2026): structured mandate perimeter and delegation chain checks.
Tokens issued under a root mandate without a perimeter are unchanged from v1.0
(same claims, same action hash). Breaking for sub-mandates: tokens under any
sub-mandate now require every parent to be active and unexpired, and a new
sub-mandate requires a parent whose perimeter allows delegation.

## Goal
Enforce structural hard-stop: no valid mandate → no token → no action.

## Token Format
JWS Compact Serialization (RFC 7515) with Ed25519 signature (EdDSA).
Header: {"alg":"EdDSA","typ":"JWT","kid":"<key-id>"}.

## Required Claims
- `iss` (issuer): "amr://localhost" or configured issuer URI
- `sub` (subject): agent_id
- `aud` (audience): runtime/platform identifier where the token will be presented
- `exp` (expiration): issued_at + configurable lifetime (default 300s), and never later than the expiry of the mandate or of any mandate above it in the delegation chain, and never above the shortest risk class reaching the action (Risk Classes); a caller can shorten it, never lengthen it
- `iat` (issued_at): UTC epoch
- `nbf` (not before): iat
- `jti` (JWT ID): UUIDv4, used for replay prevention
- `amr_mandate_id`: mandate UUID that authorized this token
- `amr_action_hash`: SHA-256 of the canonical action descriptor
  (prevents token reuse for other actions)
- `amr_scope_digest`: SHA-256 of the mandate scope at issuance time

## Optional Claims (v1.1)
- `amr_action_type`: the dotted action type named by the request. It was checked
  against a perimeter only when `amr_perimeter_digest` is also present; under a
  free-text mandate it is sealed but unchecked.
- `amr_perimeter_digest`: SHA-256 of the mandate's canonical perimeter JSON,
  present when the mandate has a structured perimeter. A consumer that relies on
  perimeter enforcement MUST require this claim (and `amr_action_type`).
- `amr_risk_classes`: sorted names of the risk classes that reached `amr_action_type`
  in any perimeter of the delegation chain, present only when at least one did. The
  token's lifetime was bounded by the shortest of them (see Risk Classes).
- `amr_registry_check` (v1.3): `true` when a risk class reaching `amr_action_type`
  in any perimeter of the chain sets `registry_check`; absent otherwise. The consumer
  MUST then re-check the token with the registry when it acts (Registry Check at
  Execution).
- `amr_validation_required` (v1.5): `true` when a perimeter of the chain lists
  `amr_action_type` in `validation_actions`; absent otherwise. It comes with
  `amr_validated_by` (the validator the agent declared) and
  `amr_validated_content_sha256` (SHA-256 of the content validated). See Human
  Validation.

## Perimeter Enforcement (v1.1)
A mandate may carry a structured perimeter: `allowed_actions`, `forbidden_actions`
(patterns: exact type `invoice.pay`, prefix `invoice.*`, or `*`), `delegation_allowed`,
`max_amount` with `currency`, `amount_actions`, and a cumulative ceiling
`period_max_amount` with `period_days` (both or neither), and `max_delegation_depth`
(1 to 16, requires `delegation_allowed`; creation of a deeper sub-mandate is refused with
`delegation_depth_exceeded`). Action types are dotted lowercase ASCII identifiers. The
three optional keys appear in the canonical perimeter only when set, so perimeters
without them keep their digest.

Fail-safe pattern semantics: in `allowed_actions`, an exact pattern allows exactly that
type and `invoice.*` allows the strict sub-types of `invoice`; in `forbidden_actions`
and `amount_actions`, a pattern also reaches every sub-type (`agent.create` reaches
`agent.create.batch`, `agent.*` reaches `agent`).

Before issuing a token, AMR walks the delegation chain from the mandate up through
each `parent_mandate_id`. Every parent must be active (`parent_mandate_<status>`)
and unexpired (`parent_mandate_expired`). Then, for every mandate in the chain that
has a perimeter:
1. the request must name an `action_type` (`action_type_required`);
2. no forbidden pattern may reach it (`action_out_of_scope`, detail `forbidden:<pattern>`);
3. an allowed pattern must match it (`action_out_of_scope`, detail `not_allowed:<type>`);
4. if `max_amount` or `period_max_amount` is set and the action is an amount action
   (or declares an `amount`),
   the metadata must carry `amount` as a plain decimal (ASCII digits, optional dot and
   decimals: no sign, exponent, spaces or separators) at or below the ceiling, and
   `currency` equal to the perimeter's currency, exactly (`amount_required`,
   `amount_invalid`, `currency_required`, `currency_mismatch:<CUR>`,
   `amount_above_limit:<max> <CUR>`). `max_amount` applies per action;
5. if `period_max_amount` is set, the amounts of the tokens already issued under this
   mandate and every mandate below it, over the last `period_days` days (rolling,
   from issuance time), plus this action's amount, must stay at or below it
   (`period_amount_above_limit:<max> <CUR>/<days>d`). Every token whose action
   declares a valid `amount` and `currency` is recorded in `token_amounts` against
   each mandate of its chain; it counts once issued, used or not. The read and the
   insert run in one `BEGIN IMMEDIATE` transaction, so concurrent issuers cannot spend
   the same remainder.
Perimeter denials carry `refused_by`, the id of the mandate whose perimeter refused.

Sub-mandates are validated at creation: the parent must be active, unexpired, allow
delegation, and have the sub-mandate's principal as its agent; the sub-mandate must
declare `allowed_actions` covered by the parent's, a ceiling (per action or
cumulative) no higher than the parent's in the same currency, and an expiry no later
than the parent's. The parent's cumulative ceiling is not copied into the
sub-mandate: rule 5 already applies it to the whole branch. It inherits
the parent's forbidden patterns (and its ceiling when it sets none). Every mandate
above the parent must be active and unexpired, and a chain is limited to 16 levels.

Revocation is read from the mandate's `status` column, as in v1.0; there is no
revocation tool yet. Mandate creation is not authenticated: `create_mandate` must be
exposed to principals only, never to the agents they govern.

## Risk Classes (v1.2)
A perimeter may carry `risk_classes`: at most 20 objects `{name, actions,
max_token_seconds}`. `name` is unique in the perimeter (lowercase, `^[a-z][a-z0-9_-]{0,39}$`);
`actions` are patterns read broadly, like `forbidden_actions` (`invoice.pay` reaches
`invoice.pay.partial`); `max_token_seconds` is an integer from 1 to 86400. The key
appears in the canonical perimeter only when there is at least one class, sorted by
name, so perimeters without classes keep their digest and the mandates their hash.

When a token is issued, its lifetime is the smallest of: `AMR_TOKEN_LIFETIME_SECONDS`,
`lifetime_override_seconds` if given, and `max_token_seconds` of every class reaching
the action type in every perimeter of the delegation chain; it never ends after the
expiry of any mandate in the chain. A class never lengthens a token. A sub-mandate
inherits the parent's classes into its stored perimeter, so `verify_mandate`, the
Proof Pack, the attestation and the insurer dossier show every bound that applies to
it. It may add its own classes, and reuse a parent class name only with a
`max_token_seconds` no higher than the parent's (else `limit_exceeds_parent`); the
merged class then reaches the actions of both. A sub-mandate can shorten a window,
never lengthen one. The issuer still applies the classes of every perimeter in the
chain. The matched class names are sealed in `amr_risk_classes`.

A class whose patterns reach no allowed action bounds nothing: patterns are not
checked against `allowed_actions`. Classes bound the window during which an issued
token stays usable, including after a revocation; to close that window for the actions
that matter, a class sets `registry_check` (next section).

## Registry Check at Execution (v1.3)
A risk class may carry `registry_check: true` (strict boolean, default `false`). It
appears in the canonical class only when `true`, so classes without it keep their
form, perimeters their digest and mandates their hash. A sub-mandate inherits it with
the parent's classes; when it reuses a parent class name, the merged class keeps
`registry_check` if either side sets it: a sub-mandate cannot drop it.

A token whose action type is reached by such a class, in any perimeter of the chain,
carries `amr_registry_check: true`. Its receiver MUST, at the moment of acting and
after its own offline checks, call `check_action_token(token, audience,
expected_action_hash?, max_token_age_seconds?)` and act only on `valid: true`. Any
receiver MAY call it for any token. The check, read only, verifies in order:
1. header `alg` is EdDSA (`wrong_algorithm`) and `kid` is this registry's key
   (`key_mismatch`); signature (`bad_signature`); `iss` (`wrong_issuer`); `aud` equals
   the given audience (`wrong_audience`); `exp` (`token_expired`); `nbf`
   (`token_not_yet_valid`); the claims of the Required Claims list that the check
   reads are present (`missing_claim`);
2. the registry database exists (`registry_unavailable`; it is opened read-only and
   never created by the check), and the `jti` is in `issued_tokens` (`unknown_token`) with the same mandate, agent,
   action hash and audience (`token_record_mismatch`);
3. `expected_action_hash`, if given, equals `amr_action_hash` (`action_mismatch`);
4. `max_token_age_seconds`, if given (1 to 86400), is not exceeded since `iat`
   (`token_too_old`): the receiver can make the check stricter than the mandate's
   classes, never looser, since `exp` is always enforced;
5. the mandate exists (`mandate_not_found`), is held by the token's `sub`
   (`agent_mismatch`), is active (`mandate_status_<status>`), not revoked
   (`mandate_status_revoked`) and not expired (`mandate_expired`), and every mandate
   above it is too (`parent_mandate_*`, `delegation_chain_too_deep`, with
   `refused_by`).
An unexpected error gives `internal_error`, with the text in `detail`. The answer
carries `checked_at`. A revocation recorded before the check is seen by it. Status
values other than `active` (`mandate_status_<status>`) are checked defensively: no
tool writes them today, revocation goes through `mandate_revocations`.

The answer is unsigned JSON and the registry writes nothing for a check: it is not
evidence that the receiver checked. The receiver MUST call the registry over its own
channel and MUST NOT accept a check result relayed by the agent whose token it is.
The flag cannot force a receiver to call: it tells the receiver that the principal
asked for it.

Downgrade: an AMR version before v1.3 rejects a risk class carrying `registry_check`
(`extra="forbid"`), so once such a mandate exists, rolling back fails closed for it
(no token, no verification) rather than ignoring the flag.

## Logging under a token (v1.4)

`log_action` takes an optional `action_token`: the compact JWS `issue_action_token`
returned for the action being logged. With it, the action is logged only if:

1. the header and signature check as in `check_action_token` (EdDSA only, key of this
   registry), with `iss`, `exp` and `nbf` (the token must still be within its window
   when the action is logged);
2. the token is one this registry issued: its `jti` is in `issued_tokens` and the
   record's mandate, action hash, audience and agent equal the token's claims;
3. it was issued under the very mandate the action is logged under, to that mandate's
   agent;
4. it has not already covered another logged action: one token, one logged action
   (`action_log_tokens.jti` is UNIQUE, so a race cannot log two);
5. the mandate and every mandate above it still stand (the checks `log_action` always
   made).

`aud` is not compared with a caller's identity (the registry is not the receiver), only
with the issued record. The token's `jti` and `amr_action_hash` are then stored in
`action_log_tokens` (schema v11, append-only) and sealed into the action's
`chain_hash` as `action_token_jti` and `action_token_action_hash`. `get_proof` lists
both keys on covered actions only, and counts them in
`chain_integrity.actions_with_token`; deleting or adding a link breaks
`actions_chain_valid`.

Refusals: `{"error": "...", "reason": ...}` with `action_token_required`, `malformed`,
`wrong_algorithm`, `key_mismatch`, `bad_signature`, `wrong_issuer`, `token_expired`,
`token_not_yet_valid`, `missing_claim`, `unknown_token`, `token_record_mismatch`,
`token_mandate_mismatch`, `agent_mismatch` or `token_already_used`. Nothing is written.

`AMR_REQUIRE_ACTION_TOKEN_FOR_LOG=true` (default `false`) refuses every action logged
without a token. Off, an action without a token is logged as before: same fields, same
`chain_hash`, and nothing in the journal says it was authorized.

Downgrade: an AMR version before v1.4 does not read `action_log_tokens`. Once an action
has been logged with a token, that version's `get_proof` rebuilds the action's hash
without the two sealed keys and reports `actions_chain_valid: false` for the mandate.
Do not roll back a registry that has logged an action under a token.

Strict mode and short tokens: the token must still be within its window when the
action is logged. With `AMR_REQUIRE_ACTION_TOKEN_FOR_LOG=true`, log right after acting:
an action logged after its token's `exp` (a risk class may cut it to seconds) is
refused and cannot be logged later.

What it does not prove: that the action described in `action` is the one the token
was issued for. The registry never sees the action itself; the receiver's
`amr_action_hash` check (consumer contract, check 5) is what binds them.

## Human Validation (v1.5)
A perimeter may carry `validation_actions`: patterns (broad match, like
`forbidden_actions`: a pattern also reaches every sub-type) of the action types that
need a human validation. The key appears in the canonical perimeter only when the list
is not empty, so perimeters without it keep their digest, mandates their hash and
principal signatures their payload.

For an action type it reaches, in any perimeter of the delegation chain, the action
metadata MUST carry:
- `validated_by`: who validated, as the agent declares it (1 to 200 characters, not
  blank, no control, format such as zero-width or bidi, line or paragraph separator
  character);
- `validated_content_sha256`: SHA-256 of the content validated, 64 lowercase hex.

Otherwise the token is refused with `action_out_of_scope` and the detail
`validation_required:<missing keys>` or `validation_invalid:<key>`, and `refused_by`
names the first mandate of the chain, from the requested one upward, whose perimeter
required it (for an inherited requirement, the sub-mandate itself). The check runs after `forbidden_actions`
and `allowed_actions` and before the amount ceilings. Both values are part of the
metadata, hence of `amr_action_hash`: a token for one validated content does not cover
another. The token also carries them as `amr_validated_by` and
`amr_validated_content_sha256`, with `amr_validation_required: true`, and the registry
records them (table `token_validations`, schema v12, append-only, same transaction as
`issued_tokens`). `check_action_token` returns them on a valid token
(`validation_required`, `validated_by`, `validated_content_sha256`); `get_proof` lists
them under `validated_actions`, with the logged action the token covered, if any.

A sub-mandate inherits the parent's `validation_actions` into its stored perimeter and
may add its own; it cannot lift one. The issuer checks every perimeter of the chain, so
a sub-mandate stored without the parent's list is still bound by it.

Limits. The registry records the validator the agent declares; it does not
authenticate that person and does not see the content. The receiver MUST compare
`validated_by` with who it knows validated (the person signed in on its side) and
`validated_content_sha256` with the SHA-256 of the content it receives, and refuse on
a mismatch. A validation is not single-use: the same `validated_by` and hash can back
several tokens (another `action` text, or the same one after the previous token
expired); a receiver that needs one action per validation MUST deduplicate on its
side. The `token_validations` rows are not hash-chained; the signed token is the
evidence of what was declared at issuance.

Downgrade: an AMR version before v1.5 rejects a perimeter carrying
`validation_actions` (`extra="forbid"`), so rolling back fails closed for such
mandates (no token) rather than ignoring the requirement.

## Replay Prevention
The `issued_tokens` table stores every issued jti with its expiration.
A token cannot be issued twice for the same `(mandate_id, action_hash)`
within the expiration window (idempotency enforced).

Note: `action_hash` does NOT include the mandate_id. The replay
prevention is keyed on `(mandate_id, action_hash)` in the DB index,
which correctly handles the case of two mandates for the same agent
requesting the same action — each gets its own token.

## Offline Verification Contract (for consumers)
Consumers of the token (agent runtimes, platforms) validate the token
using the Ed25519 public key, which AMR publishes at a well-known path
or exposes via config.

Consumers MUST check, in this order:
1. JWS signature is valid against the AMR public key (algorithm fixed to EdDSA).
2. `iss` matches the expected AMR issuer URI.
3. `aud` matches the consumer's own audience identifier
   (prevents audience confusion attacks — a token for audience A must
   not be accepted by audience B).
4. `exp` is in the future AND `nbf` is in the past (with reasonable clock skew).
5. `amr_action_hash` matches the SHA-256 of the action they are about to perform
   (canonical JSON form — see _canonical_action_hash in issue_action_token.py).
   When the token carries `amr_action_type`, the canonical descriptor includes the
   key `action_type`, and the consumer MUST check that it names the operation it is
   about to execute.

If any check fails, the consumer MUST reject the token and refuse the action.
The same registry key also signs mandate attestations (header
`typ: amr-attestation+jwt`, see `docs/mandate-attestation-spec.md`): they carry no
`amr_action_hash`, so check 5 rejects them; a consumer SHOULD also reject that `typ`.

## Security Notes
- Private key is generated once, stored at `settings.signing_key_path`,
  file permissions 0600 on POSIX.
- Algorithm is fixed to EdDSA in both encoding and decoding;
  no algorithm negotiation to prevent confusion attacks.
- Key rotation: out of scope for v1 (documented as v2 follow-up).
- Token revocation before expiration: out of scope for v1.
  Short token lifetime (5 min default) limits revocation window.
