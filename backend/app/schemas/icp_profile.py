"""ICPProfile Pydantic schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ICPProfileBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    model_config = {"from_attributes": True}
    target_industries: str | None = None
    sub_industries: str | None = None
    target_countries: str | None = None
    target_regions: str | None = None
    company_size: str | None = Field(None, max_length=64)
    employee_count_min: int | None = Field(None, ge=0)
    employee_count_max: int | None = Field(None, ge=0)
    revenue_min: str | None = Field(None, max_length=64)
    revenue_max: str | None = Field(None, max_length=64)
    preferred_company_types: str | None = None
    target_audience: str | None = None
    decision_maker_roles: str | None = None
    additional_criteria: str | None = None
    max_prospects: int = Field(default=20, ge=1, le=100)
    is_active: bool = True


class ICPProfileCreate(ICPProfileBase):
    workspace_id: uuid.UUID
    client_profile_id: uuid.UUID | None = None
    model_config = {"from_attributes": True}

class ICPProfileUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    target_industries: str | None = None
    sub_industries: str | None = None
    target_countries: str | None = None
    target_regions: str | None = None
    company_size: str | None = Field(None, max_length=64)
    employee_count_min: int | None = Field(None, ge=0)
    employee_count_max: int | None = Field(None, ge=0)
    revenue_min: str | None = Field(None, max_length=64)
    revenue_max: str | None = Field(None, max_length=64)
    preferred_company_types: str | None = None
    target_audience: str | None = None
    decision_maker_roles: str | None = None
    additional_criteria: str | None = None
    max_prospects: int | None = Field(None, ge=1, le=100)
    is_active: bool | None = None


class ICPProfileResponse(ICPProfileBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    client_profile_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
