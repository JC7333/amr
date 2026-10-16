"""Mandate template model: a named, versioned perimeter with a catalog of action types."""

import hashlib
import json
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from amr.models.perimeter import Perimeter, parse_amount, pattern_reaches

TEMPLATE_ID_RE = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
VERSION_RE = r"^[0-9]+\.[0-9]+\.[0-9]+$"


class LegalReference(BaseModel):
    """A legal text the principal should check before relying on the template."""

    model_config = {"extra": "forbid", "frozen": True}

    reference: str = Field(..., min_length=1, max_length=200)
    topic: str = Field(..., min_length=1, max_length=300)
    status: Literal["to_verify", "verified"] = "to_verify"


class MandateTemplate(BaseModel):
    """A ready-made perimeter for one kind of agent. Immutable once defined.

    ``actions`` is the catalog: every action type named in the perimeter (allowed or
    forbidden) has a plain-language meaning, so that an agent or a reviewer can read
    what the mandate permits without guessing from the identifiers.
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
        return self

    # --- serialization -------------------------------------------------------------

    def canonical(self) -> dict[str, Any]:
        """Canonical dict, stable across runs (used for the digest and the docs)."""
        return {
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
        }

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
        self, max_amount: str | None = None, metadata: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Return the perimeter arguments and metadata to pass to ``create_mandate``.

        ``max_amount`` lets the principal set its own ceiling (plain decimal string, same
        currency). It may lower the template's ceiling, never raise it. ``metadata`` adds
        the principal's own annotations; the ``template_*`` keys are reserved.

        The ``template_*`` metadata is a label: like all mandate metadata it is not sealed
        into the chain hash. The perimeter, which is sealed, is what the token issuer
        enforces.
        """
        reserved = sorted(k for k in (metadata or {}) if k.startswith("template_"))
        if reserved:
            raise ValueError(f"metadata keys reserved for the template: {reserved}")
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
        return {
            "allowed_actions": canonical["allowed_actions"],
            "forbidden_actions": canonical["forbidden_actions"],
            "delegation_allowed": perimeter.delegation_allowed,
            "max_amount": None if ceiling is None else format(ceiling, "f"),
            "currency": perimeter.currency,
            "amount_actions": canonical["amount_actions"] or None,
            "metadata": {
                **(metadata or {}),
                "template_id": self.template_id,
                "template_version": self.version,
                "template_digest": self.digest(),
            },
        }
