"""AMR Pydantic models for mandates, actions, and verification results."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MandateStatus(StrEnum):
    """Status of an agent mandate."""

    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class LegalBasis(BaseModel):
    """Legal basis for an agent mandate, referencing a regulation and article."""

    regulation: str = Field(..., min_length=1, max_length=500)
    article: str = Field(..., min_length=1, max_length=500)
    jurisdiction: str = Field(default="EU", max_length=10)


class MandateCreate(BaseModel):
    """Input model for creating a new mandate. All fields are strictly validated."""

    model_config = {"extra": "forbid"}

    principal_id: str = Field(..., min_length=1, max_length=200)
    agent_id: str = Field(..., min_length=1, max_length=200)
    scope: str = Field(..., min_length=1, max_length=2000)
    legal_basis: LegalBasis
    duration_hours: float = Field(..., gt=0, le=8760)
    parent_mandate_id: UUID | None = Field(default=None)
    metadata: dict[str, str] = Field(default_factory=dict)


class Mandate(BaseModel):
    """A fully instantiated mandate, including id, status, timestamps, and chain hash."""

    id: UUID = Field(default_factory=uuid4)
    principal_id: str = Field(..., min_length=1, max_length=200)
    agent_id: str = Field(..., min_length=1, max_length=200)
    scope: str = Field(..., min_length=1, max_length=2000)
    legal_basis: LegalBasis
    duration_hours: float = Field(..., gt=0, le=8760)
    parent_mandate_id: UUID | None = Field(default=None)
    metadata: dict[str, str] = Field(default_factory=dict)
    status: MandateStatus = Field(default=MandateStatus.ACTIVE)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime
    chain_hash: str


class ActionLog(BaseModel):
    """A logged action performed by an agent under a mandate."""

    id: UUID = Field(default_factory=uuid4)
    mandate_id: UUID
    agent_id: str
    action: str = Field(..., min_length=1, max_length=2000)
    evidence: str = Field(default="", max_length=5000)
    result: str = Field(default="", max_length=2000)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    chain_hash: str


class VerifyResult(BaseModel):
    """Result of a mandate verification check."""

    authorized: bool
    mandate_id: UUID | None
    reason: str
    scope: str
    expires_at: datetime | None
