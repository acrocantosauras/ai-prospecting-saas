"""Company Pydantic schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CompanyBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    model_config = {"from_attributes": True}
    website: str | None = Field(None, max_length=512)
    industry: str | None = Field(None, max_length=255)
    location: str | None = Field(None, max_length=512)
    country: str | None = Field(None, max_length=128)
    city: str | None = Field(None, max_length=255)
    description: str | None = None
    products_services: str | None = None
    company_size: str | None = Field(None, max_length=128)
    employee_count: str | None = Field(None, max_length=64)
    revenue: str | None = Field(None, max_length=128)
    linkedin_url: str | None = Field(None, max_length=512)
    instagram_url: str | None = Field(None, max_length=512)
    source_url: str | None = Field(None, max_length=512)
    source_name: str | None = Field(None, max_length=255)


class CompanyCreate(CompanyBase):
    batch_id: uuid.UUID
    duplicate_of_id: uuid.UUID | None = None


class CompanyResponse(CompanyBase):
    id: uuid.UUID
    batch_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
