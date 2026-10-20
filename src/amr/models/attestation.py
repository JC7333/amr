"""Pydantic model for mandate attestation requests."""

from uuid import UUID

from pydantic import BaseModel, Field, StrictBool


class AttestationRequest(BaseModel):
    """Input for issuing a mandate attestation. Strictly validated."""

    model_config = {"extra": "forbid"}

    mandate_id: UUID
    agent_id: str = Field(..., min_length=1, max_length=200)
    audience: str | None = Field(default=None, min_length=1, max_length=500)
    lifetime_seconds: int | None = Field(default=None, ge=1)
    include_principal_payload: StrictBool = False
