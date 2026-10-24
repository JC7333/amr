"""Organ decision: the collective decision that authorizes an agent.

In an organization, the principal of a mandate is often a body rather than a person: a
committee or a board decides that an AI agent may perform a predefined list of actions,
and designates who carries that decision out. The organ decision records that decision
on the mandate: which body decided, the decision's title and date, an optional internal
reference, and the persons or roles it designates (``authorized_personnel``).

It travels in the mandate metadata under the reserved key ``organ_decision``, as the
compact canonical JSON produced by ``OrganDecision.to_metadata_value()``. Because it is
metadata, a principal signature covers it; ``create_mandate`` also seals it into the
mandate's chain hash. Mandates without it keep their exact hash.

The predefined actions are the mandate's perimeter (``allowed_actions``): create_mandate
accepts an organ decision only with a closed list (no ``*`` pattern), and anything not on
it is refused at token issuance. The organ decision does not widen or narrow it. It is
recorded on root mandates only: an agent cannot declare one for its own sub-agent.
"""

import json
import re
from datetime import date
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

ORGAN_DECISION_KEY = "organ_decision"
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", re.ASCII)
MAX_PERSONNEL = 50


class OrganDecisionError(ValueError):
    """An organ decision is malformed. ``code`` is a stable, machine-readable reason."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _clean(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("must not be blank")
    if stripped != value:
        raise ValueError("must not start or end with whitespace")
    return value


class OrganDecision(BaseModel):
    """The decision of a body (committee, board) that authorizes the agent. Immutable."""

    model_config = {"extra": "forbid", "frozen": True}

    body: str = Field(..., min_length=1, max_length=200)
    title: str = Field(..., min_length=1, max_length=300)
    decided_on: str
    reference: str | None = Field(default=None, min_length=1, max_length=200)
    authorized_personnel: tuple[str, ...] = Field(..., min_length=1, max_length=MAX_PERSONNEL)

    @field_validator("body", "title", "reference")
    @classmethod
    def _not_blank(cls, value: str | None) -> str | None:
        return None if value is None else _clean(value)

    @field_validator("decided_on")
    @classmethod
    def _iso_date(cls, value: str) -> str:
        if not isinstance(value, str) or not DATE_RE.fullmatch(value):
            raise ValueError("decided_on must be a date written YYYY-MM-DD")
        date.fromisoformat(value)
        return value

    @field_validator("authorized_personnel")
    @classmethod
    def _personnel(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for entry in value:
            if len(entry) > 200:
                raise ValueError("each authorized_personnel entry is 200 characters at most")
            _clean(entry)
        if len(set(value)) != len(value):
            raise ValueError("authorized_personnel entries must be unique")
        return value

    @property
    def decided_on_date(self) -> date:
        return date.fromisoformat(self.decided_on)

    def canonical(self) -> dict[str, Any]:
        """Canonical dict (personnel kept in the decision's order)."""
        return {
            "body": self.body,
            "title": self.title,
            "decided_on": self.decided_on,
            "reference": self.reference,
            "authorized_personnel": list(self.authorized_personnel),
        }

    def to_metadata_value(self) -> str:
        """Compact canonical JSON, the only accepted form of the ``organ_decision`` key."""
        return json.dumps(
            self.canonical(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    @classmethod
    def from_metadata_value(cls, raw: str) -> "OrganDecision":
        """Parse the ``organ_decision`` metadata value; raise OrganDecisionError."""
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            raise OrganDecisionError(
                "organ_decision_invalid", "organ_decision must be a JSON object"
            ) from None
        if not isinstance(data, dict):
            raise OrganDecisionError(
                "organ_decision_invalid", "organ_decision must be a JSON object"
            )
        try:
            decision = cls.model_validate(data)
        except ValidationError as exc:
            raise OrganDecisionError("organ_decision_invalid", str(exc)) from None
        if decision.to_metadata_value() != raw:
            raise OrganDecisionError(
                "organ_decision_not_canonical",
                "organ_decision must be the exact output of OrganDecision.to_metadata_value()",
            )
        return decision


def organ_decision_from_metadata(metadata: dict[str, str]) -> OrganDecision | None:
    """Return the organ decision carried by mandate metadata, or None if there is none."""
    if ORGAN_DECISION_KEY not in metadata:
        return None
    return OrganDecision.from_metadata_value(metadata[ORGAN_DECISION_KEY])


def recorded_organ_decision(metadata_json: str) -> dict[str, Any] | None:
    """The organ decision recorded in a stored mandate's metadata JSON, or None.

    A value that is not a valid canonical organ decision (possible only for a mandate
    created before the key was reserved) is reported as no decision.
    """
    try:
        decision = organ_decision_from_metadata(json.loads(metadata_json))
    except (OrganDecisionError, ValueError, TypeError):
        return None
    return decision.canonical() if decision is not None else None
