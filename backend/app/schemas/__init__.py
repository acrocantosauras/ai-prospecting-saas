"""All Pydantic schemas with datetime serialization fixes."""

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _to_iso(value):
    """Convert a datetime value to an ISO string, handling naive datetimes."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return value


class WorkspaceBase(BaseModel):
    slug: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    model_config = {"from_attributes": True}


class WorkspaceCreate(WorkspaceBase):
    pass


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)


class WorkspaceResponse(WorkspaceBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def _to_iso(cls, v):
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            return v.isoformat()
        return v

    from pydantic import field_serializer

    @field_serializer("created_at", "updated_at")
    def _serialize_datetime(self, v, _info):
        return self._to_iso(v)


class ClientProfileBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    website: str | None = Field(None, max_length=512)
    description: str | None = None
    products_services: str | None = None
    value_proposition: str | None = None
    target_audience: str | None = None
    problems_solved: str | None = None
    usp: str | None = None
    is_active: bool = True
    model_config = {"from_attributes": True}


class ClientProfileCreate(ClientProfileBase):
    workspace_id: uuid.UUID


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

    @classmethod
    def _to_iso(cls, v):
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            return v.isoformat()
        return v

    from pydantic import field_serializer

    @field_serializer("created_at", "updated_at")
    def _serialize_datetime(self, v, _info):
        return self._to_iso(v)


class ICPProfileBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
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
    model_config = {"from_attributes": True}


class ICPProfileCreate(ICPProfileBase):
    workspace_id: uuid.UUID
    client_profile_id: uuid.UUID | None = None


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

    @classmethod
    def _to_iso(cls, v):
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            return v.isoformat()
        return v

    from pydantic import field_serializer

    @field_serializer("created_at", "updated_at")
    def _serialize_datetime(self, v, _info):
        return self._to_iso(v)


class ProspectBatchBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    icp_profile_id: uuid.UUID
    client_profile_id: uuid.UUID | None = None
    requested_prospect_count: int = Field(default=20, ge=1, le=100)
    model_config = {"from_attributes": True}


class ProspectBatchCreate(ProspectBatchBase):
    workspace_id: str


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

    @classmethod
    def _to_iso(cls, v):
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            return v.isoformat()
        return v

    from pydantic import field_serializer

    @field_serializer("completed_at", "created_at", "updated_at")
    def _serialize_datetime(self, v, _info):
        return self._to_iso(v) if v else None


class ProspectBatchListResponse(BaseModel):
    items: list[dict]
    total: int


class CompanyBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
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
    model_config = {"from_attributes": True}


class CompanyCreate(CompanyBase):
    batch_id: uuid.UUID
    duplicate_of_id: uuid.UUID | None = None


class CompanyResponse(CompanyBase):
    id: uuid.UUID
    batch_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def _to_iso(cls, v):
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            return v.isoformat()
        return v

    from pydantic import field_serializer

    @field_serializer("created_at", "updated_at")
    def _serialize_datetime(self, v, _info):
        return self._to_iso(v)


class DecisionMakerBase(BaseModel):
    first_name: str | None = Field(None, max_length=128)
    last_name: str | None = Field(None, max_length=128)
    full_name: str | None = Field(None, max_length=256)
    job_title: str | None = Field(None, max_length=256)
    professional_profile_url: str | None = Field(None, max_length=512)
    profile_source: str | None = Field(None, max_length=255)
    is_primary: bool = False
    model_config = {"from_attributes": True}


class DecisionMakerCreate(DecisionMakerBase):
    company_id: uuid.UUID


class DecisionMakerResponse(DecisionMakerBase):
    id: uuid.UUID
    company_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def _to_iso(cls, v):
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            return v.isoformat()
        return v

    from pydantic import field_serializer

    @field_serializer("created_at", "updated_at")
    def _serialize_datetime(self, v, _info):
        return self._to_iso(v)


class ProspectBase(BaseModel):
    first_name: str | None = Field(None, max_length=128)
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
    is_ready_for_outreach: bool | None = None
    model_config = {"from_attributes": True}


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

    @classmethod
    def _to_iso(cls, v):
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            return v.isoformat()
        return v

    from pydantic import field_serializer

    @field_serializer("created_at", "updated_at")
    def _serialize_datetime(self, v, _info):
        return self._to_iso(v)


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


class EvidenceBase(BaseModel):
    label: str | None = Field(None, max_length=255)
    url: str | None = Field(None, max_length=1024)
    content: str | None = None
    evidence_type: str | None = Field(None, max_length=64)
    model_config = {"from_attributes": True}


class EvidenceCreate(EvidenceBase):
    prospect_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None


class EvidenceResponse(EvidenceBase):
    id: uuid.UUID
    prospect_id: uuid.UUID | None
    company_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def _to_iso(cls, v):
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            return v.isoformat()
        return v

    from pydantic import field_serializer

    @field_serializer("created_at")
    def _serialize_datetime(self, v, _info):
        return self._to_iso(v)


class EnrichmentRecordBase(BaseModel):
    provider: str | None = Field(None, max_length=128)
    provider_record_id: str | None = Field(None, max_length=256)
    email: str | None = Field(None, max_length=512)
    email_status: str | None = Field(None, max_length=64)
    email_confidence: float | None = Field(None, ge=0.0, le=1.0)
    linkedin_url: str | None = Field(None, max_length=512)
    instagram_url: str | None = Field(None, max_length=512)
    other_profiles: str | None = None
    raw_response: str | None = None
    model_config = {"from_attributes": True}


class EnrichmentRecordCreate(EnrichmentRecordBase):
    prospect_id: uuid.UUID


class EnrichmentRecordResponse(EnrichmentRecordBase):
    id: uuid.UUID
    prospect_id: uuid.UUID
    fetched_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def _to_iso(cls, v):
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            return v.isoformat()
        return v

    from pydantic import field_serializer

    @field_serializer("fetched_at", "created_at")
    def _serialize_datetime(self, v, _info):
        return self._to_iso(v)


class VerificationRecordBase(BaseModel):
    email: str | None = Field(None, max_length=512)
    status: str | None = Field(None, max_length=64)
    provider: str | None = Field(None, max_length=128)
    details: str | None = Field(None, max_length=512)
    model_config = {"from_attributes": True}


class VerificationRecordCreate(VerificationRecordBase):
    prospect_id: uuid.UUID


class VerificationRecordResponse(VerificationRecordBase):
    id: uuid.UUID
    prospect_id: uuid.UUID
    verified_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def _to_iso(cls, v):
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            return v.isoformat()
        return v

    from pydantic import field_serializer

    @field_serializer("verified_at", "created_at")
    def _serialize_datetime(self, v, _info):
        return self._to_iso(v)


class LeadExportRow(BaseModel):
    lead_id: str
    first_name: str | None
    last_name: str | None
    email: str | None
    company: str | None
    website: str | None
    role: str | None
    client_id: str
    status: str = "new"
    draft_date: str | None = None
    notes: str | None = None


__all__ = [
    "WorkspaceBase",
    "WorkspaceCreate",
    "WorkspaceUpdate",
    "WorkspaceResponse",
    "ClientProfileBase",
    "ClientProfileCreate",
    "ClientProfileUpdate",
    "ClientProfileResponse",
    "ICPProfileBase",
    "ICPProfileCreate",
    "ICPProfileUpdate",
    "ICPProfileResponse",
    "ProspectBatchBase",
    "ProspectBatchCreate",
    "ProspectBatchUpdate",
    "ProspectBatchStageUpdate",
    "ProspectBatchResponse",
    "ProspectBatchListResponse",
    "CompanyBase",
    "CompanyCreate",
    "CompanyResponse",
    "DecisionMakerBase",
    "DecisionMakerCreate",
    "DecisionMakerResponse",
    "ProspectBase",
    "ProspectCreate",
    "ProspectUpdate",
    "ProspectResponse",
    "ProspectListResponse",
    "ProspectDetailResponse",
    "EvidenceBase",
    "EvidenceCreate",
    "EvidenceResponse",
    "EnrichmentRecordBase",
    "EnrichmentRecordCreate",
    "EnrichmentRecordResponse",
    "VerificationRecordBase",
    "VerificationRecordCreate",
    "VerificationRecordResponse",
    "LeadExportRow",
]
