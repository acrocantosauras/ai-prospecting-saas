"""ClientProfile Pydantic schemas."""

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _to_iso(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return value


class ClientProfileBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)

    model_config = {"from_attributes": True}
    website: str | None = Field(None, max_length=512)
    description: str | None = None
    products_services: str | None = None
    value_proposition: str | None = None
    target_audience: str | None = None
    problems_solved: str | None = None
    usp: str | None = None
    is_active: bool = True


class ClientProfileCreate(ClientProfileBase):
    workspace_id: uuid.UUID
    model_config = {"from_attributes": True}

class ClientProfileUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    website: str | None = Field(None, max_length=512)
    description: str | None = None
    products_services: str | None = None
    value_proposition: str | None = None
    target_audience: str | None = None
    problems_solved: str | None = None
    usp: str | None = None
    is_active: bool | None = None


class ClientProfileResponse(ClientProfileBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
