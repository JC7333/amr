"""Pydantic models for action tokens issued by AMR."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


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


class CheckTokenRequest(BaseModel):
    """Input for re-checking an action token at execution time. Strictly validated."""

    model_config = {"extra": "forbid"}

    token: str = Field(..., min_length=1, max_length=8000)
    audience: str = Field(..., min_length=1, max_length=500)
    expected_action_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    max_token_age_seconds: int | None = Field(default=None, ge=1, le=86400, strict=True)


class RecordReceiptRequest(BaseModel):
    """Input of record_action_receipt (the receiver's receipt). Strictly validated."""

    model_config = {"extra": "forbid"}

    token: str = Field(..., min_length=1, max_length=8000)
    audience: str = Field(..., min_length=1, max_length=500)
    outcome: Literal["executed", "refused"]
    refusal_reason: str | None = Field(default=None, min_length=1, max_length=500)
    received_content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _reason_only_for_a_refusal(self) -> "RecordReceiptRequest":
        if self.outcome == "refused" and (
            self.refusal_reason is None or not self.refusal_reason.strip()
        ):
            raise ValueError("refusal_reason is required when outcome is refused")
        if self.outcome == "executed" and self.refusal_reason is not None:
            raise ValueError("refusal_reason is only for outcome refused")
        return self


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
    "action_type_required", "action_out_of_scope", "parent_mandate_revoked",
    "mandate_status_suspended", "parent_mandate_suspended").
    """

    denied: bool = True
    reason: str
    mandate_id: UUID | None = None
