"""Prospect API endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import WorkspaceCtx, ensure_permission
from app.auth.permissions import Permission
from app.core.database import get_db
from app.models import Prospect, ProspectBatch, Workspace
from app.schemas.prospect import (
    ProspectDetailResponse,
    ProspectListResponse,
    ProspectResponse,
    ProspectUpdate,
)

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]


def _text_filters(
    search: str | None, industry: str | None, country: str | None
) -> list:
    """Build the free-text and location filters for the prospect list."""
    clauses: list = []
    if search:
        term = f"%{search}%"
        clauses.append(
            (Prospect.company_name.ilike(term))
            | (Prospect.full_name.ilike(term))
            | (Prospect.email.ilike(term))
            | (Prospect.role.ilike(term))
            | (Prospect.industry.ilike(term))
            | (Prospect.country.ilike(term))
        )
    if industry:
        clauses.append(Prospect.industry.ilike(f"%{industry}%"))
    if country:
        clauses.append(Prospect.country.ilike(f"%{country}%"))
    return clauses


def _quality_filters(
    min_score: float | None,
    max_score: float | None,
    email_status: str | None,
    ready_for_outreach: bool | None,
) -> list:
    """Build the score, email-status and readiness filters."""
    clauses: list = []
    if min_score is not None:
        clauses.append(Prospect.qualification_score >= min_score)
    if max_score is not None:
        clauses.append(Prospect.qualification_score <= max_score)
    if email_status == "available":
        clauses.append(Prospect.email.isnot(None))
    elif email_status == "unavailable":
        clauses.append(Prospect.email.is_(None))
    elif email_status == "verified":
        clauses.extend(
            [
                Prospect.email.isnot(None),
                Prospect.research_confidence.ilike("%verified%"),
            ]
        )
    elif email_status == "unverified":
        clauses.append(Prospect.email.isnot(None))
    if ready_for_outreach is not None:
        clauses.append(Prospect.is_ready_for_outreach == ready_for_outreach)
    return clauses


def get_prospect_or_404(db: Session, prospect_id: uuid.UUID, workspace: Workspace) -> Prospect:
    """Return a prospect that belongs to this workspace, or raise 404."""
    prospect = (
        db.query(Prospect)
        .filter(Prospect.id == prospect_id)
        .join(Prospect.batch)
        .join(ProspectBatch.workspace)
        .filter(Workspace.id == workspace.id)
        .first()
    )
    if not prospect:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect not found")
    return prospect


@router.get("/", response_model=ProspectListResponse)
def list_prospects(
    ctx: WorkspaceCtx,
    db: DbSession,
    batch_id: uuid.UUID | None = None,
    search: str | None = None,
    industry: str | None = None,
    country: str | None = None,
    min_score: float | None = Query(None, ge=0.0, le=100.0),
    max_score: float | None = Query(None, ge=0.0, le=100.0),
    email_status: str | None = None,
    ready_for_outreach: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
):
    """List prospects in the caller's workspace with filters and paging."""
    ensure_permission(ctx, Permission.VIEW_WORKSPACE)
    query = (
        db.query(Prospect)
        .join(Prospect.batch)
        .join(ProspectBatch.workspace)
        .filter(Workspace.id == ctx.workspace.id)
    )
    clauses = _text_filters(search, industry, country)
    if batch_id:
        clauses.append(Prospect.batch_id == batch_id)
    clauses.extend(
        _quality_filters(min_score, max_score, email_status, ready_for_outreach)
    )
    if clauses:
        query = query.filter(*clauses)

    total = query.count()
    sort_column = getattr(Prospect, sort_by, None)
    if sort_column is None:
        sort_column = Prospect.created_at
    query = query.order_by(sort_column.desc() if sort_order == "desc" else sort_column.asc())
    offset = (page - 1) * page_size
    items = query.offset(offset).limit(page_size).all()
    return ProspectListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{prospect_id}", response_model=ProspectDetailResponse)
def get_prospect_detail(
    prospect_id: uuid.UUID,
    ctx: WorkspaceCtx,
    db: DbSession,
):
    """Return full prospect detail including evidence and verification."""
    ensure_permission(ctx, Permission.VIEW_WORKSPACE)
    prospect = get_prospect_or_404(db, prospect_id, ctx.workspace)
    company_data = None
    decision_maker_data = None
    if prospect.company:
        company_data = {
            "id": prospect.company.id,
            "name": prospect.company.name,
            "website": prospect.company.website,
            "industry": prospect.company.industry,
            "location": prospect.company.location,
            "country": prospect.company.country,
            "city": prospect.company.city,
            "description": prospect.company.description,
            "products_services": prospect.company.products_services,
            "company_size": prospect.company.company_size,
            "employee_count": prospect.company.employee_count,
            "revenue": prospect.company.revenue,
            "linkedin_url": prospect.company.linkedin_url,
            "instagram_url": prospect.company.instagram_url,
            "source_url": prospect.company.source_url,
            "source_name": prospect.company.source_name,
        }
    if prospect.decision_maker:
        dm = prospect.decision_maker
        decision_maker_data = {
            "id": dm.id,
            "first_name": dm.first_name,
            "last_name": dm.last_name,
            "full_name": dm.full_name,
            "job_title": dm.job_title,
            "professional_profile_url": dm.professional_profile_url,
            "profile_source": dm.profile_source,
            "is_primary": dm.is_primary,
        }
    evidence = [
        {"id": e.id, "label": e.label, "url": e.url, "content": e.content, "evidence_type": e.evidence_type}
        for e in prospect.evidence_items
    ]
    enrichment = [
        {
            "id": er.id,
            "provider": er.provider,
            "provider_record_id": er.provider_record_id,
            "email": er.email,
            "email_status": er.email_status,
            "email_confidence": er.email_confidence,
            "linkedin_url": er.linkedin_url,
            "instagram_url": er.instagram_url,
            "other_profiles": er.other_profiles,
        }
        for er in prospect.enrichment_records
    ]
    verification = [
        {"id": vr.id, "email": vr.email, "status": vr.status, "provider": vr.provider, "details": vr.details}
        for vr in prospect.verification_records
    ]
    prospect_schema = ProspectResponse.model_validate(prospect)
    return ProspectDetailResponse(
        **prospect_schema.model_dump(mode='json'),
        company=company_data,
        decision_maker=decision_maker_data,
        evidence=evidence,
        enrichment_records=enrichment,
        verification_records=verification,
    )


@router.patch("/{prospect_id}", response_model=ProspectResponse)
def update_prospect(
    prospect_id: uuid.UUID,
    data: ProspectUpdate,
    ctx: WorkspaceCtx,
    db: DbSession,
):
    """Update manually reviewable research fields on a prospect."""
    ensure_permission(ctx, Permission.MANAGE_PROFILES)
    prospect = get_prospect_or_404(db, prospect_id, ctx.workspace)
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(prospect, field, value)
    db.commit()
    db.refresh(prospect)
    return ProspectResponse.model_validate(prospect)
