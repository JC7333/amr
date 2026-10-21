"""Pydantic model for the insurer dossier export request."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, field_validator, model_validator


class InsurerDossierRequest(BaseModel):
    """Input for exporting a signed insurer dossier. Strictly validated."""

    model_config = {"extra": "forbid"}

    mandate_id: UUID
    period_start: datetime | None = None
    period_end: datetime | None = None
    format: Literal["json", "html"] = "json"

    @field_validator("period_start", "period_end")
    @classmethod
    def _aware_utc(cls, value: datetime | None) -> datetime | None:
        """Naive datetimes read as UTC, as everywhere else in the registry."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _ordered(self) -> "InsurerDossierRequest":
        if (
            self.period_start is not None
            and self.period_end is not None
            and self.period_start > self.period_end
        ):
            raise ValueError("period_start must not be after period_end")
        return self
