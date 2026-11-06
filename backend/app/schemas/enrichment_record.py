"""EnrichmentRecord Pydantic schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class EnrichmentRecordBase(BaseModel):
    provider: str | None = Field(None, max_length=128)
    model_config = {"from_attributes": True}
    provider_record_id: str | None = Field(None, max_length=256)
    email: str | None = Field(None, max_length=512)
    email_status: str | None = Field(None, max_length=64)
    email_confidence: float | None = Field(None, ge=0.0, le=1.0)
    linkedin_url: str | None = Field(None, max_length=512)
    instagram_url: str | None = Field(None, max_length=512)
    other_profiles: str | None = None
    raw_response: str | None = None


class EnrichmentRecordCreate(EnrichmentRecordBase):
    prospect_id: uuid.UUID


class EnrichmentRecordResponse(EnrichmentRecordBase):
    id: uuid.UUID
    prospect_id: uuid.UUID
    fetched_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}
