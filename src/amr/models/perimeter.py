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
"""

import hashlib
import json
import re
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

ACTION_TYPE_RE = re.compile(r"[a-z0-9][a-z0-9_-]*(?:\.[a-z0-9][a-z0-9_-]*)*", re.ASCII)
AMOUNT_RE = re.compile(r"[0-9]{1,18}(?:\.[0-9]{1,18})?", re.ASCII)
MAX_PATTERNS = 100
MAX_ACTION_TYPE_LENGTH = 200


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


def _canonical_amount(amount: Decimal) -> str:
    """Exact plain notation without trailing zeros (no rounding)."""
    text = format(amount, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


class Perimeter(BaseModel):
    """Machine-readable perimeter of a mandate. Immutable once created."""

    model_config = {"extra": "forbid", "frozen": True}

    allowed_actions: tuple[str, ...] = Field(..., min_length=1, max_length=MAX_PATTERNS)
    forbidden_actions: tuple[str, ...] = Field(default=(), max_length=MAX_PATTERNS)
    delegation_allowed: bool = False
    max_amount: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    amount_actions: tuple[str, ...] = Field(default=(), max_length=MAX_PATTERNS)

    @field_validator("allowed_actions", "forbidden_actions", "amount_actions")
    @classmethod
    def _normalize_patterns(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({_validate_pattern(p) for p in value}))

    @field_validator("max_amount", mode="before")
    @classmethod
    def _plain_decimal(cls, value: object) -> object:
        if value is None:
            return None
        parsed = parse_amount(value)
        if parsed is None:
            raise ValueError("max_amount must be a plain decimal such as '500' or '120.50'")
        return parsed

    @model_validator(mode="after")
    def _amount_actions_need_a_limit(self) -> "Perimeter":
        if self.amount_actions and self.max_amount is None:
            raise ValueError("amount_actions requires max_amount")
        return self

    # --- serialization ---------------------------------------------------------

    def canonical(self) -> dict[str, Any]:
        """Canonical dict, stable across runs (used in hashes, storage and proofs)."""
        return {
            "allowed_actions": list(self.allowed_actions),
            "forbidden_actions": list(self.forbidden_actions),
            "delegation_allowed": self.delegation_allowed,
            "max_amount": _canonical_amount(self.max_amount) if self.max_amount else None,
            "currency": self.currency,
            "amount_actions": list(self.amount_actions),
        }

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
        if self.max_amount is not None:
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
            if amount > self.max_amount:
                return f"amount_above_limit:{_canonical_amount(self.max_amount)} {self.currency}"
        return None

    def narrowed_by(self, parent: "Perimeter") -> "Perimeter":
        """Return this perimeter as a sub-mandate of ``parent``, or raise PerimeterError.

        Every allowed pattern must lie inside the parent's allowed patterns. The parent's
        forbidden patterns are inherited. The parent's amount ceiling is inherited when the
        child sets none, and a child ceiling may never exceed it.
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
        if parent.max_amount is not None:
            if max_amount is None:
                max_amount, currency = parent.max_amount, parent.currency
                amount_actions = parent.amount_actions
            elif currency != parent.currency:
                raise PerimeterError(
                    "limit_exceeds_parent",
                    f"currency {currency} differs from the parent mandate's {parent.currency}",
                )
            elif max_amount > parent.max_amount:
                raise PerimeterError(
                    "limit_exceeds_parent",
                    f"max_amount {_canonical_amount(max_amount)} is above the parent mandate's "
                    f"{_canonical_amount(parent.max_amount)}",
                )
            elif not amount_actions or not parent.amount_actions:
                amount_actions = ()  # an empty list means every action is limited
            else:
                amount_actions = tuple(set(amount_actions) | set(parent.amount_actions))
        try:
            return Perimeter(
                allowed_actions=self.allowed_actions,
                forbidden_actions=forbidden,
                delegation_allowed=self.delegation_allowed,
                max_amount=max_amount,
                currency=currency,
                amount_actions=amount_actions,
            )
        except ValueError as exc:
            raise PerimeterError("perimeter_invalid", str(exc)) from exc
