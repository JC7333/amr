"""Structured mandate perimeter.

A perimeter is the machine-readable part of a mandate: which action types the agent
may request, which ones it may never request, whether it may delegate (create a
sub-mandate for another agent), and an optional amount limit per action.

Action types are dotted, lowercase identifiers chosen by the principal, for example
``invoice.read``, ``invoice.pay`` or ``agent.create``. A pattern is either an exact
action type, a prefix pattern ending in ``.*`` (``invoice.*`` matches ``invoice.pay``
and ``invoice.pay.partial`` but not ``invoice``), or ``*`` (every action type).

Forbidden patterns always win over allowed patterns.

An amount limit (``max_amount``) applies to the actions matched by ``amount_actions``
(every action when ``amount_actions`` is empty): those actions must carry an ``amount``
metadata value at or below the limit. Any other action that declares an amount is
checked against the limit too.
"""

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

ACTION_TYPE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)*$")
MAX_PATTERNS = 100
MAX_ACTION_TYPE_LENGTH = 200


class PerimeterError(ValueError):
    """A perimeter rule was violated. ``code`` is a stable, machine-readable reason."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def is_valid_action_type(action_type: str) -> bool:
    """Return True if ``action_type`` is a dotted lowercase identifier."""
    return len(action_type) <= MAX_ACTION_TYPE_LENGTH and bool(ACTION_TYPE_RE.match(action_type))


def _validate_pattern(pattern: str) -> str:
    if pattern == "*":
        return pattern
    base = pattern[:-2] if pattern.endswith(".*") else pattern
    if not is_valid_action_type(base):
        raise ValueError(
            f"invalid action pattern '{pattern}': expected an action type such as "
            "'invoice.pay', a prefix pattern such as 'invoice.*', or '*'"
        )
    return pattern


def pattern_matches(pattern: str, action_type: str) -> bool:
    """Return True if ``pattern`` matches the concrete ``action_type``."""
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        return action_type.startswith(pattern[:-1])
    return action_type == pattern


def pattern_covers(outer: str, inner: str) -> bool:
    """Return True if every action type matched by ``inner`` is matched by ``outer``."""
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
    return format(amount.normalize(), "f")


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
            if pattern_matches(pattern, action_type):
                return f"forbidden:{pattern}"
        if not any(pattern_matches(p, action_type) for p in self.allowed_actions):
            return f"not_allowed:{action_type}"
        if self.max_amount is not None:
            raw = metadata.get("amount")
            if raw is None:
                limited = not self.amount_actions or any(
                    pattern_matches(p, action_type) for p in self.amount_actions
                )
                return "amount_required" if limited else None
            try:
                amount = Decimal(raw)
            except InvalidOperation:
                return "amount_invalid"
            if not amount.is_finite() or amount < 0:
                return "amount_invalid"
            currency = metadata.get("currency")
            if currency is not None and currency.upper() != self.currency:
                return f"currency_mismatch:{self.currency}"
            if amount > self.max_amount:
                return f"amount_above_limit:{_canonical_amount(self.max_amount)} {self.currency}"
        return None

    def narrowed_by(self, parent: "Perimeter") -> "Perimeter":
        """Return this perimeter as a sub-mandate of ``parent``, or raise PerimeterError.

        Every allowed pattern must lie inside the parent's allowed patterns. The parent's
        forbidden patterns are inherited. The parent's amount limit is inherited when the
        child sets none, and a child limit may never exceed it.
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
        return Perimeter(
            allowed_actions=self.allowed_actions,
            forbidden_actions=forbidden,
            delegation_allowed=self.delegation_allowed,
            max_amount=max_amount,
            currency=currency,
            amount_actions=amount_actions,
        )
