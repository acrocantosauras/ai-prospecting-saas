"""DecisionMaker Pydantic schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DecisionMakerBase(BaseModel):
    first_name: str | None = Field(None, max_length=128)
    model_config = {"from_attributes": True}
    last_name: str | None = Field(None, max_length=128)
    full_name: str | None = Field(None, max_length=256)
    job_title: str | None = Field(None, max_length=256)
    professional_profile_url: str | None = Field(None, max_length=512)
    profile_source: str | None = Field(None, max_length=255)
    is_primary: bool = False


class DecisionMakerCreate(DecisionMakerBase):
    company_id: uuid.UUID


class DecisionMakerResponse(DecisionMakerBase):
    id: uuid.UUID
    company_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
