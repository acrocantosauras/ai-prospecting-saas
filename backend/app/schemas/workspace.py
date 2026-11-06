"""Workspace Pydantic schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class WorkspaceBase(BaseModel):
    slug: str = Field(..., min_length=1, max_length=100)
    model_config = {"from_attributes": True}
    name: str = Field(..., min_length=1, max_length=255)


class WorkspaceCreate(WorkspaceBase):
    pass


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)


class WorkspaceResponse(WorkspaceBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
