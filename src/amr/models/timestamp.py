"""Input of record_registry_timestamp. Strictly validated."""

from pydantic import BaseModel, Field


class RecordTimestampRequest(BaseModel):
    """An anchor from prepare_registry_timestamp and a time-stamping service's response."""

    model_config = {"extra": "forbid"}

    # An anchor lists 14 tables: a few kilobytes. A response with its certificates: a
    # few kilobytes too; 1 MB of base64 leaves room for long chains.
    anchor_json: str = Field(..., min_length=2, max_length=20000)
    timestamp_response: str = Field(..., min_length=4, max_length=1_000_000)
