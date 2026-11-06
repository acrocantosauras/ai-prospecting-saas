"""Evidence Pydantic schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class EvidenceBase(BaseModel):
    label: str | None = Field(None, max_length=255)
    model_config = {"from_attributes": True}
    url: str | None = Field(None, max_length=1024)
    content: str | None = None
    evidence_type: str | None = Field(None, max_length=64)


class EvidenceCreate(EvidenceBase):
    prospect_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None


class EvidenceResponse(EvidenceBase):
    id: uuid.UUID
    prospect_id: uuid.UUID | None
    company_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
