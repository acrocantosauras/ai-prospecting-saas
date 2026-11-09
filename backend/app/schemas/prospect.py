"""Prospect Pydantic schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProspectBase(BaseModel):
    first_name: str | None = Field(None, max_length=128)
    model_config = {"from_attributes": True}
    last_name: str | None = Field(None, max_length=128)
    full_name: str | None = Field(None, max_length=256)
    email: str | None = Field(None, max_length=512)
    role: str | None = Field(None, max_length=256)
    linkedin_url: str | None = Field(None, max_length=512)
    instagram_url: str | None = Field(None, max_length=512)
    company_name: str | None = Field(None, max_length=256)
    company_website: str | None = Field(None, max_length=512)
    industry: str | None = Field(None, max_length=256)
    country: str | None = Field(None, max_length=128)
    research_summary: str | None = None
    business_problem: str | None = None
    problem_evidence: str | None = None
    solution_match: str | None = None
    qualification_score: float = Field(default=0.0, ge=0.0, le=100.0)
    qualification_reasons: str | None = None
    research_confidence: str | None = Field(None, max_length=64)
    missing_information: str | None = None
    source_links: str | None = None
    qualification_status: str | None = None
    qualification_confidence: float | None = None
    synthetic: bool | None = None
    is_ready_for_outreach: bool | None = None


class ProspectCreate(ProspectBase):
    batch_id: uuid.UUID
    company_id: uuid.UUID | None = None
    decision_maker_id: uuid.UUID | None = None


class ProspectUpdate(BaseModel):
    research_summary: str | None = None
    business_problem: str | None = None
    problem_evidence: str | None = None
    solution_match: str | None = None
    qualification_score: float | None = Field(None, ge=0.0, le=100.0)
    qualification_reasons: str | None = None
    research_confidence: str | None = Field(None, max_length=64)
    missing_information: str | None = None
    source_links: str | None = None
    is_ready_for_outreach: bool | None = None


class ProspectResponse(ProspectBase):
    id: uuid.UUID
    batch_id: uuid.UUID
    company_id: uuid.UUID | None
    decision_maker_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}




class ProspectListResponse(BaseModel):
    items: list[ProspectResponse]
    total: int
    page: int
    page_size: int


class ProspectDetailResponse(ProspectResponse):
    company: dict | None = None
    decision_maker: dict | None = None
    evidence: list[dict] = []
    enrichment_records: list[dict] = []
    verification_records: list[dict] = []
