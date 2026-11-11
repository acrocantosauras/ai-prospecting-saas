"""Schemas for the prospecting engine API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class EngineBatchCreate(BaseModel):
    """Request to create an engine-managed prospecting batch."""

    workspace_id: str
    icp_profile_id: uuid.UUID
    client_profile_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    requested_prospect_count: int = Field(default=20, ge=1, le=100)
    mode: Literal["demo", "real"] | None = None


class EngineBatchResponse(BaseModel):
    """Batch summary returned by the engine endpoints."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    status: str
    current_stage: str | None
    source_mode: str
    requested_prospect_count: int
    total_discovered: int
    total_discovered_companies: int | None = None
    total_researched: int
    total_enriched: int
    total_qualified: int
    total_rejected: int | None = None
    error_message: str | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StageRunResponse(BaseModel):
    """Status of one pipeline stage."""

    stage: str
    status: str
    detail: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class UsageTotals(BaseModel):
    """Measured provider usage and derived unit costs."""

    total_cost_usd: float
    total_calls: int
    by_capability: dict[str, float]
    per_company_usd: float | None = None
    per_decision_maker_usd: float | None = None
    per_verified_email_usd: float | None = None
    per_qualified_prospect_usd: float | None = None
    budget_usd: float | None = None


class EngineBatchProgressResponse(BaseModel):
    """Progress, stage states, counts and cost for a batch."""

    batch: EngineBatchResponse
    progress_percent: float
    stages: list[StageRunResponse]
    usage: UsageTotals
    qualified_companies: int
    rejected_companies: int
    recheck_companies: int


class GateResponse(BaseModel):
    """One qualification gate outcome."""

    name: str
    label: str
    passed: bool
    required: bool
    weight: float
    reason: str
    missing: str | None = None
    relaxed: bool = False
    blocked_by_capability: bool = False


class QualificationResponse(BaseModel):
    """An auditable qualification decision."""

    id: uuid.UUID
    company_id: uuid.UUID | None
    prospect_id: uuid.UUID | None
    scope: str
    status: str
    score: float
    confidence: float
    reasons: str | None
    missing: list[str]
    evidence_urls: list[str]
    gates: list[dict[str, Any]]
    policy: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class ProviderStatusResponse(BaseModel):
    """Capability/health report for a single provider."""

    name: str
    capability: str
    state: str
    synthetic: bool
    available: bool
    detail: str | None = None
    cost_per_call_usd: float = 0.0


class ProviderOverviewResponse(BaseModel):
    """Provider readiness plus the active qualification policy."""

    mode: str
    providers: list[ProviderStatusResponse]
    policy: dict[str, Any]
    notes: list[str]


class ProspectVerificationResponse(BaseModel):
    """Verification/enrichment detail for one prospect."""

    prospect_id: uuid.UUID
    email: str | None
    email_verified: bool
    email_status: str | None
    qualification_status: str | None
    missing_information: list[str]
    enrichment: list[dict[str, Any]]
    verification: list[dict[str, Any]]
    evidence: list[dict[str, Any]]


class CompanyEvidenceResponse(BaseModel):
    """Research findings and evidence for one company."""

    company_id: uuid.UUID
    company_name: str
    research: dict[str, Any] | None
    evidence: list[dict[str, Any]]
    freshness: dict[str, Any] | None = None
