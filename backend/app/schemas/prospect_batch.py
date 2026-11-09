"""ProspectBatch Pydantic schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProspectBatchBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    model_config = {"from_attributes": True}
    icp_profile_id: uuid.UUID
    client_profile_id: uuid.UUID | None = None
    requested_prospect_count: int = Field(default=20, ge=1, le=100)


class ProspectBatchCreate(ProspectBatchBase):
    # Slug or UUID, validated against the caller's memberships on the server.
    workspace_id: str = Field(..., min_length=1, max_length=100)
    model_config = {"from_attributes": True}


class ProspectBatchUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    requested_prospect_count: int | None = Field(None, ge=1, le=100)


class ProspectBatchStageUpdate(BaseModel):
    current_stage: str | None = None
    total_discovered: int | None = None
    total_researched: int | None = None
    total_enriched: int | None = None
    total_qualified: int | None = None


class ProspectBatchResponse(ProspectBatchBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    status: str
    current_stage: str | None
    total_discovered: int
    total_researched: int
    total_enriched: int
    total_qualified: int
    error_message: str | None
    source_mode: str
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}




class ProspectBatchListResponse(BaseModel):
    items: list[ProspectBatchResponse]
    total: int
