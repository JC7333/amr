# Token Issuance Specification v1.3

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

## Perimeter Enforcement (v1.1)
A mandate may carry a structured perimeter: `allowed_actions`, `forbidden_actions`
(patterns: exact type `invoice.pay`, prefix `invoice.*`, or `*`), `delegation_allowed`,
`max_amount` with `currency`, `amount_actions`, and a cumulative ceiling
`period_max_amount` with `period_days` (both or neither). Action types are dotted
lowercase ASCII identifiers. The two cumulative keys appear in the canonical perimeter
only when set, so perimeters without them keep their digest.

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
2. the `jti` is in `issued_tokens` (`unknown_token`) with the same mandate, agent,
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
The answer carries `checked_at`. A revocation recorded before the check is seen by
it. The registry writes nothing for a check: it is not evidence that the receiver
checked. The receiver that wants that evidence keeps the answer. The flag cannot
force a receiver to call: it tells the receiver that the principal asked for it.

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
