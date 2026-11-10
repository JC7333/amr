"""Mandate template model: a named, versioned perimeter with a catalog of action types."""

import hashlib
import json
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from amr.models.organ_decision import ORGAN_DECISION_KEY, OrganDecision
from amr.models.perimeter import (
    MAX_RISK_CLASSES,
    Perimeter,
    RiskClass,
    parse_amount,
    pattern_reaches,
)

TEMPLATE_ID_RE = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
VERSION_RE = r"^[0-9]+\.[0-9]+\.[0-9]+$"


class LegalReference(BaseModel):
    """A legal text the principal should check before relying on the template."""

    model_config = {"extra": "forbid", "frozen": True}

    reference: str = Field(..., min_length=1, max_length=200)
    topic: str = Field(..., min_length=1, max_length=300)
    status: Literal["to_verify", "verified"] = "to_verify"


class Stewardship(BaseModel):
    """Who holds a template (the sector baseline) and how the sector may take it over.

    ``status`` is ``provisional`` while the registry publishes the baseline itself, and
    ``sector`` once a body of the sector holds it. ``reviewers`` lists the practitioners
    whose review has actually been recorded: it stays empty until then, and nothing in
    the code fills it in.
    """

    model_config = {"extra": "forbid", "frozen": True}

    status: Literal["provisional", "sector"]
    held_by: str = Field(..., min_length=1, max_length=200)
    handover: str = Field(..., min_length=1, max_length=1000)
    reviewers: tuple[str, ...] = ()

    @field_validator("held_by", "handover")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("reviewers")
    @classmethod
    def _reviewers_are_named(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not name.strip() or len(name) > 200 for name in value):
            raise ValueError("every reviewer needs a name of 1 to 200 characters")
        if len(set(value)) != len(value):
            raise ValueError("reviewers must be unique")
        return value

    def canonical(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "held_by": self.held_by,
            "handover": self.handover,
            "reviewers": list(self.reviewers),
        }


def _reach_covers(outer: str, inner: str) -> bool:
    """True if every action type that ``inner`` reaches (broad match) ``outer`` reaches."""
    if outer == "*":
        return True
    if inner == "*":
        return False
    return pattern_reaches(outer, inner.removesuffix(".*"))


class MandateTemplate(BaseModel):
    """A ready-made perimeter for one kind of agent. Immutable once defined.

    ``actions`` is the catalog: every action type named in the perimeter (allowed or
    forbidden) has a plain-language meaning, so that an agent or a reviewer can read
    what the mandate permits without guessing from the identifiers.

    ``organ_decision`` says whether a mandate built from the template records the
    decision of a body (committee, board) that authorized the agent: ``none`` (not
    asked), ``optional`` (recorded when given) or ``required`` (refused without it).

    ``stewardship`` says who holds the template as a sector baseline, whether it is still
    provisional and which practitioners reviewed it. The perimeter's ``risk_classes`` are
    the baseline's minimum thresholds per risk class: a mandate built from the template
    may tighten them, never loosen them (see ``create_mandate_kwargs``).
    """

    model_config = {"extra": "forbid", "frozen": True}

    template_id: str = Field(..., pattern=TEMPLATE_ID_RE, max_length=64)
    version: str = Field(..., pattern=VERSION_RE)
    title: str = Field(..., min_length=1, max_length=200)
    sector: str = Field(..., pattern=TEMPLATE_ID_RE, max_length=64)
    summary: str = Field(..., min_length=1, max_length=2000)
    perimeter: Perimeter
    actions: Mapping[str, str] = Field(..., min_length=1)
    default_duration_hours: float = Field(..., gt=0, le=8760)
    legal_references: tuple[LegalReference, ...] = ()
    notes: tuple[str, ...] = ()
    organ_decision: Literal["none", "optional", "required"] = "none"
    stewardship: Stewardship | None = None

    @field_validator("actions", mode="after")
    @classmethod
    def _read_only_catalog(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        return MappingProxyType(dict(value))

    @model_validator(mode="after")
    def _catalog_matches_perimeter(self) -> "MandateTemplate":
        named = (
            set(self.perimeter.allowed_actions)
            | set(self.perimeter.forbidden_actions)
            | set(self.perimeter.amount_actions)
        )
        missing = sorted(named - set(self.actions))
        if missing:
            raise ValueError(f"actions catalog has no meaning for: {missing}")
        extra = sorted(set(self.actions) - named)
        if extra:
            raise ValueError(f"actions catalog names types outside the perimeter: {extra}")
        if any(not text.strip() for text in self.actions.values()):
            raise ValueError("every catalog entry needs a meaning")
        overlap = sorted(
            allowed
            for allowed in self.perimeter.allowed_actions
            if allowed != "*"
            and any(
                pattern_reaches(forbidden, allowed.removesuffix(".*"))
                for forbidden in self.perimeter.forbidden_actions
            )
        )
        if overlap:
            raise ValueError(f"allowed actions blocked by a forbidden pattern: {overlap}")
        # A body authorizes a predefined list of actions: no pattern may widen it.
        wildcards = sorted(a for a in self.perimeter.allowed_actions if a.endswith("*"))
        if self.organ_decision != "none" and wildcards:
            raise ValueError(
                f"a template that records an organ decision needs a closed list of "
                f"allowed actions, not patterns: {wildcards}"
            )
        return self

    # --- serialization -------------------------------------------------------------

    def canonical(self) -> dict[str, Any]:
        """Canonical dict, stable across runs (used for the digest and the docs).

        ``stewardship`` appears only when set, so a template without it keeps its exact
        form and digest.
        """
        canonical: dict[str, Any] = {
            "template_id": self.template_id,
            "version": self.version,
            "title": self.title,
            "sector": self.sector,
            "summary": self.summary,
            "perimeter": self.perimeter.canonical(),
            "actions": dict(sorted(self.actions.items())),
            "default_duration_hours": self.default_duration_hours,
            "legal_references": [ref.model_dump() for ref in self.legal_references],
            "notes": list(self.notes),
            "organ_decision": self.organ_decision,
        }
        if self.stewardship is not None:
            canonical["stewardship"] = self.stewardship.canonical()
        return canonical

    def to_json(self, indent: int | None = None) -> str:
        """Canonical JSON (sorted keys). Compact unless ``indent`` is given."""
        separators = (",", ":") if indent is None else (",", ": ")
        return json.dumps(
            self.canonical(),
            sort_keys=True,
            separators=separators,
            indent=indent,
            ensure_ascii=False,
        )

    def digest(self) -> str:
        """SHA-256 of the compact canonical JSON; recorded in the mandate metadata."""
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    # --- use ---------------------------------------------------------------------------

    def create_mandate_kwargs(
        self,
        max_amount: str | None = None,
        metadata: dict[str, str] | None = None,
        organ_decision: OrganDecision | None = None,
        risk_classes: Sequence[RiskClass | Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Return the perimeter arguments and metadata to pass to ``create_mandate``.

        ``max_amount`` lets the principal set its own ceiling (plain decimal string, same
        currency). It may lower the template's ceiling, never raise it. ``metadata`` adds
        the principal's own annotations; the ``template_*`` keys and ``organ_decision``
        are reserved. ``organ_decision`` records the decision of the body that authorized
        the agent (allowed when the template's ``organ_decision`` is not ``none``,
        mandatory when it is ``required``); create_mandate seals it into the chain hash.

        ``risk_classes`` lets the principal tighten the template's minimum thresholds:
        a class with the name of a template class replaces it only if it is at least as
        strict (no longer ``max_token_seconds``, reaches every action the template class
        reaches, keeps ``registry_check``); a class with a new name is added. Anything
        looser is refused with a ValueError. Template classes not named are kept as is.
        When the template has a stewardship block, its status is recorded as
        ``template_status``.

        The ``template_*`` metadata is a label: like other mandate metadata (except the
        ``organ_decision`` key, which create_mandate seals) it is not sealed
        into the chain hash. The perimeter, which is sealed, is what the token issuer
        enforces.
        """
        reserved = sorted(
            k for k in (metadata or {}) if k.startswith("template_") or k == ORGAN_DECISION_KEY
        )
        if reserved:
            raise ValueError(f"metadata keys reserved for the template: {reserved}")
        if organ_decision is not None and self.organ_decision == "none":
            raise ValueError(f"template {self.template_id!r} does not record an organ decision")
        if organ_decision is None and self.organ_decision == "required":
            raise ValueError(f"template {self.template_id!r} requires an organ decision")
        decision_metadata = (
            {ORGAN_DECISION_KEY: organ_decision.to_metadata_value()}
            if organ_decision is not None
            else {}
        )
        perimeter = self.perimeter
        ceiling = perimeter.max_amount
        if max_amount is not None:
            parsed = parse_amount(max_amount)
            if parsed is None or parsed <= 0:
                raise ValueError("max_amount must be a positive plain decimal such as '50'")
            if ceiling is None:
                raise ValueError(f"template {self.template_id!r} has no amount ceiling")
            if parsed > ceiling:
                raise ValueError(
                    f"max_amount {max_amount} is above the template ceiling "
                    f"{perimeter.canonical()['max_amount']} {perimeter.currency}"
                )
            ceiling = parsed
        canonical = perimeter.canonical()
        period = (
            {
                "period_max_amount": canonical["period_max_amount"],
                "period_days": perimeter.period_days,
            }
            if perimeter.period_max_amount is not None
            else {}
        )
        classes = self._hardened_risk_classes(risk_classes or ())
        risk = {"risk_classes": [rc.canonical() for rc in classes]} if classes else {}
        status = (
            {"template_status": self.stewardship.status} if self.stewardship is not None else {}
        )
        return {
            **period,
            **risk,
            "allowed_actions": canonical["allowed_actions"],
            "forbidden_actions": canonical["forbidden_actions"],
            "delegation_allowed": perimeter.delegation_allowed,
            "max_amount": None if ceiling is None else format(ceiling, "f"),
            "currency": perimeter.currency,
            "amount_actions": canonical["amount_actions"] or None,
            "metadata": {
                **(metadata or {}),
                **decision_metadata,
                "template_id": self.template_id,
                "template_version": self.version,
                "template_digest": self.digest(),
                **status,
            },
        }

    def _hardened_risk_classes(
        self, given: Sequence[RiskClass | Mapping[str, Any]]
    ) -> tuple[RiskClass, ...]:
        """The template's risk classes, tightened by ``given``; refuse any loosening."""
        if isinstance(given, (str, bytes, Mapping)):
            raise ValueError("risk_classes must be a list of risk classes")
        parsed = tuple(
            rc if isinstance(rc, RiskClass) else RiskClass.model_validate(rc) for rc in given
        )
        names = [rc.name for rc in parsed]
        if len(set(names)) != len(names):
            raise ValueError("risk class names must be unique")
        merged = {rc.name: rc for rc in self.perimeter.risk_classes}
        for rc in parsed:
            floor = merged.get(rc.name)
            if floor is not None and rc is not floor:
                self._check_not_looser(rc, floor)
            merged[rc.name] = rc
        if len(merged) > MAX_RISK_CLASSES:
            raise ValueError(
                f"at most {MAX_RISK_CLASSES} risk classes, template classes included "
                f"({len(merged)} asked)"
            )
        return tuple(sorted(merged.values(), key=lambda rc: rc.name))

    def _check_not_looser(self, rc: RiskClass, floor: RiskClass) -> None:
        where = (
            f"risk class {rc.name!r} of template {self.template_id!r}: a mandate may "
            "tighten the template's thresholds, never loosen them"
        )
        if rc.max_token_seconds > floor.max_token_seconds:
            raise ValueError(
                f"{where} ({rc.max_token_seconds} s asked, template minimum threshold "
                f"{floor.max_token_seconds} s)"
            )
        if floor.registry_check and not rc.registry_check:
            raise ValueError(f"{where} (registry_check cannot be dropped)")
        uncovered = sorted(
            action
            for action in floor.actions
            if not any(_reach_covers(pattern, action) for pattern in rc.actions)
        )
        if uncovered:
            raise ValueError(f"{where} (actions left out: {uncovered})")
