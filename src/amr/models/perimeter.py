"""Structured mandate perimeter.

A perimeter is the machine-readable part of a mandate: which action types the agent
may request, which ones it may never request, whether it may delegate (create a
sub-mandate for another agent), and an optional amount ceiling per action.

Action types are dotted, lowercase identifiers chosen by the principal, for example
``invoice.read``, ``invoice.pay`` or ``agent.create``. A pattern is an exact action
type, a prefix pattern ending in ``.*``, or ``*`` (every action type).

Fail-safe semantics: allow-lists are read narrowly, deny-lists broadly.

- In ``allowed_actions``, ``invoice.pay`` allows exactly ``invoice.pay``, and
  ``invoice.*`` allows the sub-types of ``invoice`` (``invoice.pay``,
  ``invoice.pay.partial``) but not ``invoice`` itself.
- In ``forbidden_actions`` and ``amount_actions``, a pattern also reaches every
  sub-type: forbidding ``agent.create`` forbids ``agent.create.batch`` too, and
  ``agent.*`` also covers ``agent`` itself.
- Forbidden patterns always win over allowed patterns.

An amount ceiling (``max_amount``) applies to the actions reached by ``amount_actions``
(every action when ``amount_actions`` is empty): they must carry ``amount`` and
``currency`` metadata, the amount at or below the ceiling. Any other action that
declares an amount is checked the same way. Amounts use plain decimal notation with
a dot (``500``, ``120.50``): no sign, exponent, spaces, separators or non-ASCII digits.

A cumulative ceiling (``period_max_amount`` over a rolling window of ``period_days``
days, same ``currency``) caps the total of the amounts of the action tokens issued
under the mandate and every sub-mandate below it within the window. The same actions
must carry ``amount`` and ``currency``. The token issuer sums the issued tokens (used or
not); this model only validates the ceiling. Perimeters without it keep their exact
canonical form, so existing hashes and digests are unchanged.

Risk classes (``risk_classes``) let the principal bound the lifetime of the action
tokens by how much is at stake: each class names the action types it reaches (broad
match, like ``forbidden_actions``) and the longest lifetime, in seconds, of a token for
them, for example a short window for irreversible actions. An action reached by several
classes gets the shortest. The token issuer applies the classes of every mandate in the
delegation chain, so a sub-mandate can shorten a window but never lengthen one.
A class may also set ``registry_check``: its tokens then carry ``amr_registry_check``,
telling the receiver to ask the registry (check_action_token) at the moment of acting
whether the mandate and its whole chain still stand. A sub-mandate inherits the flag
and cannot drop it. Perimeters without classes, and classes without the flag, keep
their exact canonical form.
"""

import hashlib
import json
import re
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

ACTION_TYPE_RE = re.compile(r"[a-z0-9][a-z0-9_-]*(?:\.[a-z0-9][a-z0-9_-]*)*", re.ASCII)
AMOUNT_RE = re.compile(r"[0-9]{1,18}(?:\.[0-9]{1,18})?", re.ASCII)
MAX_PATTERNS = 100
MAX_ACTION_TYPE_LENGTH = 200
MAX_PERIOD_DAYS = 366
MAX_RISK_CLASSES = 20
MAX_TOKEN_SECONDS = 86400
RISK_CLASS_NAME_RE = r"^[a-z][a-z0-9_-]{0,39}$"


class PerimeterError(ValueError):
    """A perimeter rule was violated. ``code`` is a stable, machine-readable reason."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def is_valid_action_type(action_type: str) -> bool:
    """Return True if ``action_type`` is a dotted lowercase ASCII identifier."""
    return len(action_type) <= MAX_ACTION_TYPE_LENGTH and bool(
        ACTION_TYPE_RE.fullmatch(action_type)
    )


def parse_amount(raw: object) -> Decimal | None:
    """Parse a plain decimal amount (``500`` or ``120.50``); None if not in that form."""
    if isinstance(raw, Decimal):
        raw = format(raw, "f")
    if not isinstance(raw, str) or not AMOUNT_RE.fullmatch(raw):
        return None
    return Decimal(raw)


def _validate_pattern(pattern: str) -> str:
    if pattern == "*":
        return pattern
    base = pattern[:-2] if pattern.endswith(".*") else pattern
    if not is_valid_action_type(base):
        raise ValueError(
            f"invalid action pattern {pattern!r}: expected an action type such as "
            "'invoice.pay', a prefix pattern such as 'invoice.*', or '*'"
        )
    return pattern


def pattern_matches(pattern: str, action_type: str) -> bool:
    """Narrow match, for allowed_actions: exact type, strict sub-types of a prefix, or '*'."""
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        return action_type.startswith(pattern[:-1])
    return action_type == pattern


def pattern_reaches(pattern: str, action_type: str) -> bool:
    """Broad match, for forbidden_actions and amount_actions: the type and all its sub-types."""
    if pattern == "*":
        return True
    base = pattern[:-2] if pattern.endswith(".*") else pattern
    return action_type == base or action_type.startswith(base + ".")


def pattern_covers(outer: str, inner: str) -> bool:
    """Return True if every action type allowed by ``inner`` is allowed by ``outer``."""
    if outer == "*":
        return True
    if inner == "*":
        return False
    if outer.endswith(".*"):
        outer_prefix = outer[:-1]
        if inner.endswith(".*"):
            return inner[:-2] + "." == outer_prefix or inner.startswith(outer_prefix)
        return inner.startswith(outer_prefix)
    return inner == outer


def _union_limited(child: tuple[str, ...], parent: tuple[str, ...]) -> tuple[str, ...]:
    """Actions bound by either limit; an empty list means every action is limited."""
    if not child or not parent:
        return ()
    return tuple(set(child) | set(parent))


def _inherit_risk_classes(
    child: tuple["RiskClass", ...], parent: tuple["RiskClass", ...]
) -> tuple["RiskClass", ...]:
    """Child classes plus the parent's; a shared name keeps the shorter, wider class."""
    merged = {rc.name: rc for rc in parent}
    for rc in child:
        inherited = merged.get(rc.name)
        if inherited is None:
            merged[rc.name] = rc
            continue
        if rc.max_token_seconds > inherited.max_token_seconds:
            raise PerimeterError(
                "limit_exceeds_parent",
                f"risk class '{rc.name}' allows {rc.max_token_seconds} s, above the parent "
                f"mandate's {inherited.max_token_seconds} s",
            )
        try:
            merged[rc.name] = RiskClass(
                name=rc.name,
                actions=tuple(set(rc.actions) | set(inherited.actions)),
                max_token_seconds=rc.max_token_seconds,
                registry_check=rc.registry_check or inherited.registry_check,
            )
        except ValueError as exc:
            raise PerimeterError("perimeter_invalid", str(exc)) from exc
    return tuple(merged.values())


def _canonical_amount(amount: Decimal) -> str:
    """Exact plain notation without trailing zeros (no rounding)."""
    text = format(amount, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


class RiskClass(BaseModel):
    """A class of actions whose tokens live at most ``max_token_seconds``.

    With ``registry_check``, the receiver of such a token must re-check the registry
    when it acts (check_action_token), not only the token's signature.
    """

    model_config = {"extra": "forbid", "frozen": True}

    name: str = Field(..., pattern=RISK_CLASS_NAME_RE)
    actions: tuple[str, ...] = Field(..., min_length=1, max_length=MAX_PATTERNS)
    max_token_seconds: int = Field(..., ge=1, le=MAX_TOKEN_SECONDS, strict=True)
    registry_check: bool = Field(default=False, strict=True)

    @field_validator("actions")
    @classmethod
    def _normalize_patterns(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({_validate_pattern(p) for p in value}))

    def reaches(self, action_type: str) -> bool:
        """True if this class applies to ``action_type`` (the type and all its sub-types)."""
        return any(pattern_reaches(p, action_type) for p in self.actions)

    def canonical(self) -> dict[str, Any]:
        """Canonical dict; ``registry_check`` appears only when set, so older classes
        keep their exact form (and the mandates their hash)."""
        canonical: dict[str, Any] = {
            "name": self.name,
            "actions": list(self.actions),
            "max_token_seconds": self.max_token_seconds,
        }
        if self.registry_check:
            canonical["registry_check"] = True
        return canonical


class Perimeter(BaseModel):
    """Machine-readable perimeter of a mandate. Immutable once created."""

    model_config = {"extra": "forbid", "frozen": True}

    allowed_actions: tuple[str, ...] = Field(..., min_length=1, max_length=MAX_PATTERNS)
    forbidden_actions: tuple[str, ...] = Field(default=(), max_length=MAX_PATTERNS)
    delegation_allowed: bool = False
    max_amount: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    amount_actions: tuple[str, ...] = Field(default=(), max_length=MAX_PATTERNS)
    period_max_amount: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    period_days: int | None = Field(default=None, ge=1, le=MAX_PERIOD_DAYS, strict=True)
    risk_classes: tuple[RiskClass, ...] = Field(default=(), max_length=MAX_RISK_CLASSES)

    @field_validator("allowed_actions", "forbidden_actions", "amount_actions")
    @classmethod
    def _normalize_patterns(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({_validate_pattern(p) for p in value}))

    @field_validator("risk_classes")
    @classmethod
    def _unique_risk_classes(cls, value: tuple[RiskClass, ...]) -> tuple[RiskClass, ...]:
        names = [risk_class.name for risk_class in value]
        if len(names) != len(set(names)):
            raise ValueError("risk class names must be unique")
        return tuple(sorted(value, key=lambda risk_class: risk_class.name))

    @field_validator("max_amount", "period_max_amount", mode="before")
    @classmethod
    def _plain_decimal(cls, value: object, info: ValidationInfo) -> object:
        if value is None:
            return None
        parsed = parse_amount(value)
        if parsed is None:
            raise ValueError(
                f"{info.field_name} must be a plain decimal such as '500' or '120.50'"
            )
        return parsed

    @model_validator(mode="after")
    def _amount_actions_need_a_limit(self) -> "Perimeter":
        if (self.period_max_amount is None) != (self.period_days is None):
            raise ValueError("period_max_amount and period_days must be given together")
        if self.amount_actions and not self.has_amount_limit:
            raise ValueError("amount_actions requires max_amount or period_max_amount")
        return self

    @property
    def has_amount_limit(self) -> bool:
        """True if the perimeter has a per-action or a cumulative amount ceiling."""
        return self.max_amount is not None or self.period_max_amount is not None

    def period_detail(self) -> str:
        """Denial detail when the cumulative ceiling would be exceeded."""
        if self.period_max_amount is None or self.period_days is None:
            raise ValueError("this perimeter has no cumulative ceiling")
        return (
            f"period_amount_above_limit:{_canonical_amount(self.period_max_amount)} "
            f"{self.currency}/{self.period_days}d"
        )

    def token_lifetime_cap(self, action_type: str) -> tuple[int | None, tuple[str, ...]]:
        """Shortest ``max_token_seconds`` of the risk classes reaching ``action_type``.

        Returns (None, ()) when no class reaches it, else (seconds, class names).
        """
        matched = [rc for rc in self.risk_classes if rc.reaches(action_type)]
        if not matched:
            return None, ()
        return (
            min(rc.max_token_seconds for rc in matched),
            tuple(rc.name for rc in matched),
        )

    def requires_registry_check(self, action_type: str) -> bool:
        """True if a risk class reaching ``action_type`` sets ``registry_check``."""
        return any(
            rc.registry_check and rc.reaches(action_type) for rc in self.risk_classes
        )

    # --- serialization ---------------------------------------------------------

    def canonical(self) -> dict[str, Any]:
        """Canonical dict, stable across runs (used in hashes, storage and proofs).

        The cumulative ceiling keys appear only when it is set, and ``risk_classes`` only
        when there is at least one, so a perimeter without them keeps the exact form (and
        hashes) it had before they existed.
        """
        canonical: dict[str, Any] = {
            "allowed_actions": list(self.allowed_actions),
            "forbidden_actions": list(self.forbidden_actions),
            "delegation_allowed": self.delegation_allowed,
            "max_amount": _canonical_amount(self.max_amount) if self.max_amount else None,
            "currency": self.currency,
            "amount_actions": list(self.amount_actions),
        }
        if self.period_max_amount is not None:
            canonical["period_max_amount"] = _canonical_amount(self.period_max_amount)
            canonical["period_days"] = self.period_days
        if self.risk_classes:
            canonical["risk_classes"] = [rc.canonical() for rc in self.risk_classes]
        return canonical

    def to_json(self) -> str:
        """Canonical JSON (sorted keys, compact separators)."""
        return json.dumps(self.canonical(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> "Perimeter":
        """Rebuild a perimeter from its stored canonical JSON."""
        return cls.model_validate(json.loads(raw))

    def digest(self) -> str:
        """SHA-256 of the canonical JSON; sealed into action tokens."""
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    # --- enforcement -------------------------------------------------------------

    def check_action(self, action_type: str, metadata: dict[str, str]) -> str | None:
        """Return None if the action is inside the perimeter, else a short reason detail."""
        for pattern in self.forbidden_actions:
            if pattern_reaches(pattern, action_type):
                return f"forbidden:{pattern}"
        if not any(pattern_matches(p, action_type) for p in self.allowed_actions):
            return f"not_allowed:{action_type}"
        if self.has_amount_limit:
            raw = metadata.get("amount")
            if raw is None:
                limited = not self.amount_actions or any(
                    pattern_reaches(p, action_type) for p in self.amount_actions
                )
                return "amount_required" if limited else None
            amount = parse_amount(raw)
            if amount is None:
                return "amount_invalid"
            currency = metadata.get("currency")
            if currency is None:
                return "currency_required"
            if currency != self.currency:
                return f"currency_mismatch:{self.currency}"
            if self.max_amount is not None and amount > self.max_amount:
                return f"amount_above_limit:{_canonical_amount(self.max_amount)} {self.currency}"
            if self.period_max_amount is not None and amount > self.period_max_amount:
                return self.period_detail()
        return None

    def narrowed_by(self, parent: "Perimeter") -> "Perimeter":
        """Return this perimeter as a sub-mandate of ``parent``, or raise PerimeterError.

        Every allowed pattern must lie inside the parent's allowed patterns. The parent's
        forbidden patterns are inherited. The parent's amount ceiling is inherited when the
        child sets none, and a child ceiling may never exceed it. A child cumulative
        ceiling may never exceed the parent's; the parent's own cumulative ceiling is not
        copied into the child because the token issuer already applies it to the whole
        branch below the parent. Both limits must use the same currency.
        The parent's risk classes are inherited, so the child's stored perimeter shows
        every lifetime bound that applies to it. A child class may reuse a parent class
        name only with a ``max_token_seconds`` no higher than the parent's; it then also
        reaches the parent class's actions. The issuer still applies every class of
        the chain.
        """
        for pattern in self.allowed_actions:
            if not any(pattern_covers(outer, pattern) for outer in parent.allowed_actions):
                raise PerimeterError(
                    "perimeter_exceeds_parent",
                    f"'{pattern}' is not within the parent mandate's allowed actions",
                )
        forbidden = tuple(sorted(set(self.forbidden_actions) | set(parent.forbidden_actions)))
        max_amount, currency = self.max_amount, self.currency
        amount_actions = self.amount_actions
        if self.has_amount_limit and parent.has_amount_limit and currency != parent.currency:
            raise PerimeterError(
                "limit_exceeds_parent",
                f"currency {currency} differs from the parent mandate's {parent.currency}",
            )
        if (
            self.period_max_amount is not None
            and parent.period_max_amount is not None
            and self.period_max_amount > parent.period_max_amount
        ):
            raise PerimeterError(
                "limit_exceeds_parent",
                f"period_max_amount {_canonical_amount(self.period_max_amount)} is above the "
                f"parent mandate's {_canonical_amount(parent.period_max_amount)}",
            )
        if parent.max_amount is not None:
            if max_amount is None:
                max_amount, currency = parent.max_amount, parent.currency
                if self.period_max_amount is None:
                    amount_actions = parent.amount_actions
                else:
                    amount_actions = _union_limited(amount_actions, parent.amount_actions)
            elif max_amount > parent.max_amount:
                raise PerimeterError(
                    "limit_exceeds_parent",
                    f"max_amount {_canonical_amount(max_amount)} is above the parent mandate's "
                    f"{_canonical_amount(parent.max_amount)}",
                )
            else:
                amount_actions = _union_limited(amount_actions, parent.amount_actions)
        risk_classes = _inherit_risk_classes(self.risk_classes, parent.risk_classes)
        try:
            return Perimeter(
                allowed_actions=self.allowed_actions,
                forbidden_actions=forbidden,
                delegation_allowed=self.delegation_allowed,
                max_amount=max_amount,
                currency=currency,
                amount_actions=amount_actions,
                period_max_amount=self.period_max_amount,
                period_days=self.period_days,
                risk_classes=risk_classes,
            )
        except ValueError as exc:
            raise PerimeterError("perimeter_invalid", str(exc)) from exc
