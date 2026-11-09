"""Prospecting engine API endpoints.

Every endpoint is workspace-scoped: a batch, prospect or company belonging to a
different workspace returns 404 rather than leaking data. The workspace itself
is resolved from the authenticated session plus an active membership; the
``workspace_slug``/``workspace_id`` sent by a client is only a selector.
"""

from __future__ import annotations

import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    CurrentUser,
    WorkspaceContext,
    WorkspaceCtx,
    ensure_permission,
    resolve_workspace_context,
)
from app.auth.permissions import Permission
from app.config import get_settings
from app.core.database import get_db
from app.engine.orchestrator import batch_progress, run_engine_pipeline
from app.engine.qualification import QualificationPolicy
from app.engine.registry import build_provider_bundle
from app.models import (
    ClientProfile,
    Company,
    CompanyResearchRecord,
    DecisionMaker,
    EnrichmentRecord,
    Evidence,
    ICPProfile,
    Prospect,
    ProspectBatch,
    ProviderUsage,
    QualificationRecord,
    VerificationRecord,
    Workspace,
)
from app.schemas.engine import (
    CompanyEvidenceResponse,
    EngineBatchCreate,
    EngineBatchProgressResponse,
    EngineBatchResponse,
    ProspectVerificationResponse,
    ProviderOverviewResponse,
    ProviderStatusResponse,
    QualificationResponse,
    StageRunResponse,
    UsageTotals,
)

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]

QUALIFICATION_NOTES = [
    "Only an independently verified mailbox satisfies the real-mode email gate.",
    "Demo mode is synthetic and illustrative: companies, people and emails are not real.",
    "Qualification and rejection decisions are stored with their gate-by-gate reasons.",
]


def _batch_or_404(
    db: Session, batch_id: uuid.UUID, workspace: Workspace
) -> ProspectBatch:
    batch = (
        db.query(ProspectBatch)
        .filter(
            ProspectBatch.id == batch_id,
            ProspectBatch.workspace_id == workspace.id,
        )
        .first()
    )
    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found"
        )
    return batch


def _prospect_or_404(
    db: Session, prospect_id: uuid.UUID, workspace: Workspace
) -> Prospect:
    prospect = (
        db.query(Prospect)
        .join(ProspectBatch, Prospect.batch_id == ProspectBatch.id)
        .filter(
            Prospect.id == prospect_id,
            ProspectBatch.workspace_id == workspace.id,
        )
        .first()
    )
    if prospect is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prospect not found"
        )
    return prospect


def _company_or_404(
    db: Session, company_id: uuid.UUID, workspace: Workspace
) -> Company:
    company = (
        db.query(Company)
        .join(ProspectBatch, Company.batch_id == ProspectBatch.id)
        .filter(
            Company.id == company_id,
            ProspectBatch.workspace_id == workspace.id,
        )
        .first()
    )
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company not found"
        )
    return company


def _json_value(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def _usage_summary(
    db: Session, workspace_id: uuid.UUID, batch_id: uuid.UUID | None = None
) -> UsageTotals:
    query = db.query(ProviderUsage).filter(ProviderUsage.workspace_id == workspace_id)
    if batch_id is not None:
        query = query.filter(ProviderUsage.batch_id == batch_id)
    rows = query.all()
    total_cost = round(sum(row.cost_usd for row in rows), 6)
    by_capability: dict[str, float] = {}
    for row in rows:
        by_capability[row.capability] = round(
            by_capability.get(row.capability, 0.0) + row.cost_usd, 6
        )
    companies = 0
    decision_makers = 0
    verified_emails = 0
    qualified_prospects = 0
    if batch_id is not None:
        companies = (
            db.query(CompanyResearchRecord)
            .filter(CompanyResearchRecord.batch_id == batch_id)
            .count()
        )
        decision_makers = (
            db.query(DecisionMaker)
            .join(Company, DecisionMaker.company_id == Company.id)
            .filter(Company.batch_id == batch_id)
            .count()
        )
        verified_emails = (
            db.query(VerificationRecord)
            .join(Prospect, VerificationRecord.prospect_id == Prospect.id)
            .filter(
                Prospect.batch_id == batch_id,
                VerificationRecord.status == "verified",
            )
            .count()
        )
        qualified_prospects = (
            db.query(Prospect)
            .filter(
                Prospect.batch_id == batch_id,
                Prospect.is_ready_for_outreach.is_(True),
            )
            .count()
        )

    def per_unit(total: float, count: int) -> float | None:
        return round(total / count, 6) if count else None

    settings = get_settings()
    return UsageTotals(
        total_cost_usd=total_cost,
        total_calls=len(rows),
        by_capability=by_capability,
        per_company_usd=per_unit(total_cost, companies),
        per_decision_maker_usd=per_unit(total_cost, decision_makers),
        per_verified_email_usd=per_unit(total_cost, verified_emails),
        per_qualified_prospect_usd=per_unit(total_cost, qualified_prospects),
        budget_usd=settings.batch_cost_budget_usd,
    )


def _company_status_counts(db: Session, batch_id: uuid.UUID) -> dict[str, int]:
    rows = (
        db.query(QualificationRecord.status, func.count())
        .filter(
            QualificationRecord.batch_id == batch_id,
            QualificationRecord.scope == "company",
        )
        .group_by(QualificationRecord.status)
        .all()
    )
    counts = {"qualified": 0, "qualified_illustrative": 0, "rejected": 0, "recheck_later": 0}
    for value, count in rows:
        counts[value] = count
    return {
        "qualified_companies": counts["qualified"] + counts["qualified_illustrative"],
        "rejected_companies": counts["rejected"],
        "recheck_companies": counts["recheck_later"],
    }


def _qualification_payload(row: QualificationRecord) -> QualificationResponse:
    return QualificationResponse(
        id=row.id,
        company_id=row.company_id,
        prospect_id=row.prospect_id,
        scope=row.scope,
        status=row.status,
        score=row.score,
        confidence=row.confidence,
        reasons=row.reasons,
        missing=_json_value(row.missing_requirements_json, []),
        evidence_urls=_json_value(row.evidence_urls_json, []),
        gates=_json_value(row.gates_json, []),
        policy=_json_value(row.policy_json, {}),
        created_at=row.created_at,
    )


@router.post(
    "/batches/",
    response_model=EngineBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_engine_batch(
    data: EngineBatchCreate,
    background_tasks: BackgroundTasks,
    db: DbSession,
    user: CurrentUser,
) -> EngineBatchResponse:
    """Create a batch and run the engine pipeline in the background."""
    ctx: WorkspaceContext = resolve_workspace_context(db, user, data.workspace_id)
    ensure_permission(ctx, Permission.RUN_BATCHES)
    workspace = ctx.workspace
    icp = (
        db.query(ICPProfile)
        .filter(
            ICPProfile.id == data.icp_profile_id,
            ICPProfile.workspace_id == workspace.id,
        )
        .first()
    )
    if icp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ICP profile not found"
        )
    # Never trust a client_profile_id from another tenant: it would feed another
    # workspace's offering into this batch's analysis and reference its rows.
    resolved_profile_id = data.client_profile_id or icp.client_profile_id
    if resolved_profile_id is not None:
        profile = (
            db.query(ClientProfile)
            .filter(
                ClientProfile.id == resolved_profile_id,
                ClientProfile.workspace_id == workspace.id,
            )
            .first()
        )
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Client profile not found",
            )
    settings = get_settings()
    requested_mode = data.mode or (
        "real" if (settings.prospecting_mode or "").lower() == "real" else "demo"
    )
    if requested_mode == "real":
        bundle = build_provider_bundle(settings, mode="real")
        discovery_status = bundle.discovery.status()
        if not discovery_status.available:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Real prospecting is not configured: "
                    f"{discovery_status.detail or discovery_status.state}"
                ),
            )
    batch = ProspectBatch(
        workspace_id=workspace.id,
        icp_profile_id=icp.id,
        client_profile_id=resolved_profile_id,
        name=data.name,
        requested_prospect_count=data.requested_prospect_count,
        source_mode=requested_mode,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    background_tasks.add_task(
        run_engine_pipeline, str(batch.id), str(batch.workspace_id)
    )
    return EngineBatchResponse.model_validate(batch)


@router.get("/batches/{batch_id}/progress", response_model=EngineBatchProgressResponse)
def get_batch_progress(
    batch_id: uuid.UUID,
    ctx: WorkspaceCtx,
    db: DbSession,
) -> EngineBatchProgressResponse:
    """Return stage-by-stage progress, counts and measured cost for a batch."""
    ensure_permission(ctx, Permission.VIEW_WORKSPACE)
    workspace = ctx.workspace
    batch = _batch_or_404(db, batch_id, workspace)
    snapshot = batch_progress(batch)
    return EngineBatchProgressResponse(
        batch=EngineBatchResponse.model_validate(batch),
        progress_percent=snapshot["percent"],
        stages=[StageRunResponse(**stage) for stage in snapshot["stages"]],
        usage=_usage_summary(db, workspace.id, batch.id),
        **_company_status_counts(db, batch.id),
    )


@router.post("/batches/{batch_id}/cancel", response_model=EngineBatchResponse)
def cancel_batch(
    batch_id: uuid.UUID,
    ctx: WorkspaceCtx,
    db: DbSession,
) -> EngineBatchResponse:
    """Request cancellation of a pending or running batch."""
    ensure_permission(ctx, Permission.RUN_BATCHES)
    workspace = ctx.workspace
    batch = _batch_or_404(db, batch_id, workspace)
    if batch.status not in ("pending", "running"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only a pending or running batch can be cancelled",
        )
    batch.status = "cancelled"
    batch.current_stage = "cancelled"
    db.commit()
    db.refresh(batch)
    return EngineBatchResponse.model_validate(batch)


@router.get(
    "/batches/{batch_id}/qualifications",
    response_model=list[QualificationResponse],
)
def list_qualifications(
    batch_id: uuid.UUID,
    ctx: WorkspaceCtx,
    db: DbSession,
    status_filter: str | None = Query(None, alias="status"),
    scope: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
) -> list[QualificationResponse]:
    """Return qualification decisions (including rejections) with gate detail."""
    ensure_permission(ctx, Permission.VIEW_WORKSPACE)
    workspace = ctx.workspace
    batch = _batch_or_404(db, batch_id, workspace)
    query = db.query(QualificationRecord).filter(
        QualificationRecord.batch_id == batch.id
    )
    if status_filter:
        query = query.filter(QualificationRecord.status == status_filter)
    if scope:
        query = query.filter(QualificationRecord.scope == scope)
    rows = (
        query.order_by(QualificationRecord.created_at.desc()).limit(limit).all()
    )
    return [_qualification_payload(row) for row in rows]


@router.get(
    "/prospects/{prospect_id}/verification",
    response_model=ProspectVerificationResponse,
)
def get_prospect_verification(
    prospect_id: uuid.UUID,
    ctx: WorkspaceCtx,
    db: DbSession,
) -> ProspectVerificationResponse:
    """Return verification, enrichment and missing-information detail."""
    ensure_permission(ctx, Permission.VIEW_WORKSPACE)
    workspace = ctx.workspace
    prospect = _prospect_or_404(db, prospect_id, workspace)
    enrichment = (
        db.query(EnrichmentRecord)
        .filter(EnrichmentRecord.prospect_id == prospect.id)
        .all()
    )
    verification = (
        db.query(VerificationRecord)
        .filter(VerificationRecord.prospect_id == prospect.id)
        .all()
    )
    evidence = (
        db.query(Evidence).filter(Evidence.prospect_id == prospect.id).all()
    )
    email_verified = any(
        row.status == "verified" and row.email == prospect.email
        for row in verification
    )
    missing = [
        item.strip()
        for item in (prospect.missing_information or "").split(";")
        if item.strip()
    ]
    return ProspectVerificationResponse(
        prospect_id=prospect.id,
        email=prospect.email,
        email_verified=email_verified,
        email_status=next(
            (row.status for row in verification if row.status), None
        ),
        qualification_status=prospect.qualification_status,
        missing_information=missing,
        enrichment=[
            {
                "provider": row.provider,
                "email": row.email,
                "email_status": row.email_status,
                "email_confidence": row.email_confidence,
                "linkedin_url": row.linkedin_url,
                "method": None,
                "notes": row.raw_response,
                "fetched_at": row.fetched_at,
            }
            for row in enrichment
        ],
        verification=[
            {
                "provider": row.provider,
                "email": row.email,
                "status": row.status,
                "details": row.details,
                "verified_at": row.verified_at,
            }
            for row in verification
        ],
        evidence=[
            {
                "label": row.label,
                "url": row.url,
                "content": row.content,
                "evidence_type": row.evidence_type,
            }
            for row in evidence
        ],
    )


@router.get("/companies/{company_id}/evidence", response_model=CompanyEvidenceResponse)
def get_company_evidence(
    company_id: uuid.UUID,
    ctx: WorkspaceCtx,
    db: DbSession,
) -> CompanyEvidenceResponse:
    """Return stored research findings and their evidence for a company."""
    ensure_permission(ctx, Permission.VIEW_WORKSPACE)
    workspace = ctx.workspace
    company = _company_or_404(db, company_id, workspace)
    record = (
        db.query(CompanyResearchRecord)
        .filter(CompanyResearchRecord.company_id == company.id)
        .order_by(CompanyResearchRecord.research_timestamp.desc())
        .first()
    )
    evidence = db.query(Evidence).filter(Evidence.company_id == company.id).all()
    research: dict[str, Any] | None = None
    if record is not None:
        research = {
            "provider": record.provider,
            "what_it_does": record.what_it_does,
            "what_it_sells": record.what_it_sells,
            "who_it_serves": record.who_it_serves,
            "positioning": record.positioning,
            "public_developments": record.public_developments,
            "observable_signals": _json_value(record.observable_signals_json, []),
            "missing_information": _json_value(record.missing_information_json, []),
            "confidence": record.confidence,
            "synthetic": record.synthetic,
            "research_timestamp": record.research_timestamp,
        }
    return CompanyEvidenceResponse(
        company_id=company.id,
        company_name=company.name,
        research=research,
        evidence=[
            {
                "label": row.label,
                "url": row.url,
                "content": row.content,
                "evidence_type": row.evidence_type,
            }
            for row in evidence
        ],
    )


@router.get("/providers", response_model=ProviderOverviewResponse)
def provider_overview(
    ctx: WorkspaceCtx,
    db: DbSession,
) -> ProviderOverviewResponse:
    """Report provider availability, capabilities and the qualification policy."""
    ensure_permission(ctx, Permission.VIEW_WORKSPACE)
    settings = get_settings()
    bundle = build_provider_bundle(settings)
    policy = QualificationPolicy.from_settings(settings, bundle.mode)
    return ProviderOverviewResponse(
        mode=bundle.mode,
        providers=[
            ProviderStatusResponse(
                name=item.name,
                capability=item.capability,
                state=item.state,
                synthetic=item.synthetic,
                available=item.available,
                detail=item.detail,
                cost_per_call_usd=item.cost_per_call_usd,
            )
            for item in bundle.statuses()
        ],
        policy=policy.model_dump(),
        notes=QUALIFICATION_NOTES,
    )


@router.get("/usage", response_model=UsageTotals)
def get_usage(
    ctx: WorkspaceCtx,
    db: DbSession,
    batch_id: uuid.UUID | None = None,
) -> UsageTotals:
    """Return measured provider usage and derived unit costs."""
    ensure_permission(ctx, Permission.VIEW_WORKSPACE)
    return _usage_summary(db, ctx.workspace.id, batch_id)
