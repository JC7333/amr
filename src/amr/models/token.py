"""Pydantic models for action tokens issued by AMR."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class IssueTokenRequest(BaseModel):
    """Input for issuing an action token. Strictly validated."""

    model_config = {"extra": "forbid"}

    mandate_id: UUID
    agent_id: str = Field(..., min_length=1, max_length=200)
    action: str = Field(..., min_length=1, max_length=2000)
    audience: str = Field(..., min_length=1, max_length=500)
    action_metadata: dict[str, str] = Field(default_factory=dict)
    action_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        pattern=r"^[a-z0-9][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)*$",
    )


class TokenIssueResult(BaseModel):
    """Result of a successful token issuance."""

    token: str
    jti: UUID
    expires_at: datetime
    key_id: str


class TokenDenyResult(BaseModel):
    """Result of a denied token issuance.

    reason is a machine-readable code (e.g. "mandate_not_found",
    "mandate_expired", "replay_detected_active_token_exists",
    "action_type_required", "action_out_of_scope", "parent_mandate_revoked").
    """

    denied: bool = True
    reason: str
    mandate_id: UUID | None = None
