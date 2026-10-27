# Token Issuance Specification v1.1

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
- `exp` (expiration): issued_at + configurable lifetime (default 300s), and never later than the expiry of the mandate or of any mandate above it in the delegation chain; a caller can shorten it, never lengthen it
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

## Perimeter Enforcement (v1.1)
A mandate may carry a structured perimeter: `allowed_actions`, `forbidden_actions`
(patterns: exact type `invoice.pay`, prefix `invoice.*`, or `*`), `delegation_allowed`,
`max_amount` with `currency`, and `amount_actions`. Action types are dotted lowercase
ASCII identifiers.

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
4. if `max_amount` is set and the action is an amount action (or declares an `amount`),
   the metadata must carry `amount` as a plain decimal (ASCII digits, optional dot and
   decimals: no sign, exponent, spaces or separators) at or below the ceiling, and
   `currency` equal to the perimeter's currency, exactly (`amount_required`,
   `amount_invalid`, `currency_required`, `currency_mismatch:<CUR>`,
   `amount_above_limit:<max> <CUR>`). The ceiling applies per action, not cumulatively.
Perimeter denials carry `refused_by`, the id of the mandate whose perimeter refused.

Sub-mandates are validated at creation: the parent must be active, unexpired, allow
delegation, and have the sub-mandate's principal as its agent; the sub-mandate must
declare `allowed_actions` covered by the parent's, a ceiling no higher than the
parent's in the same currency, and an expiry no later than the parent's. It inherits
the parent's forbidden patterns (and its ceiling when it sets none). Every mandate
above the parent must be active and unexpired, and a chain is limited to 16 levels.

Revocation is read from the mandate's `status` column, as in v1.0; there is no
revocation tool yet. Mandate creation is not authenticated: `create_mandate` must be
exposed to principals only, never to the agents they govern.

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
