"""VerificationRecord Pydantic schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class VerificationRecordBase(BaseModel):
    email: str | None = Field(None, max_length=512)
    model_config = {"from_attributes": True}
    status: str | None = Field(None, max_length=64)
    provider: str | None = Field(None, max_length=128)
    details: str | None = Field(None, max_length=512)


class VerificationRecordCreate(VerificationRecordBase):
    prospect_id: uuid.UUID


class VerificationRecordResponse(VerificationRecordBase):
    id: uuid.UUID
    prospect_id: uuid.UUID
    verified_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}
