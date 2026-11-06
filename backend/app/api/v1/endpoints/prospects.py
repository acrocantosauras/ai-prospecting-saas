"""Prospect API endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status, Query

from app.core.database import get_db
from app.models import Prospect, Company, DecisionMaker, Evidence, EnrichmentRecord, VerificationRecord
from app.models import Workspace, ProspectBatch
from app.schemas.prospect import (
    ProspectResponse,
    ProspectListResponse,
    ProspectDetailResponse,
    ProspectUpdate,
)

router = APIRouter()


def get_prospect_or_404(db, prospect_id: uuid.UUID, workspace_slug: str):
    promise = (
        db.query(Prospect)
        .filter(Prospect.id == prospect_id)
        .join(Prospect.batch)
        .join(ProspectBatch.workspace)
        .filter(Workspace.slug == workspace_slug)
        .first()
    )
    if not promise:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect not found")
    return promise


@router.get("/", response_model=ProspectListResponse)
def list_prospects(
    workspace_slug: str,
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
    db=Depends(get_db),
):
    query = (
        db.query(Prospect)
        .join(Prospect.batch)
        .join(ProspectBatch.workspace)
        .filter(Workspace.slug == workspace_slug)
    )
    if batch_id:
        query = query.filter(Prospect.batch_id == batch_id)
    if search:
        term = f"%{search}%"
        query = query.filter(
            (Prospect.company_name.ilike(term))
            | (Prospect.full_name.ilike(term))
            | (Prospect.email.ilike(term))
            | (Prospect.role.ilike(term))
            | (Prospect.industry.ilike(term))
            | (Prospect.country.ilike(term))
        )
    if industry:
        query = query.filter(Prospect.industry.ilike(f"%{industry}%"))
    if country:
        query = query.filter(Prospect.country.ilike(f"%{country}%"))
    if min_score is not None:
        query = query.filter(Prospect.qualification_score >= min_score)
    if max_score is not None:
        query = query.filter(Prospect.qualification_score <= max_score)
    if email_status == "available":
        query = query.filter(Prospect.email.isnot(None))
    elif email_status == "unavailable":
        query = query.filter(Prospect.email.is_(None))
    elif email_status == "verified":
        query = query.filter(
            Prospect.email.isnot(None),
            Prospect.research_confidence.ilike("%verified%"),
        )
    elif email_status == "unverified":
        query = query.filter(Prospect.email.isnot(None))
    if ready_for_outreach is not None:
        query = query.filter(Prospect.is_ready_for_outreach == ready_for_outreach)

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
    workspace_slug: str,
    db=Depends(get_db),
):
    prospect = get_prospect_or_404(db, prospect_id, workspace_slug)
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
    workspace_slug: str,
    db=Depends(get_db),
):
    prospect = get_prospect_or_404(db, prospect_id, workspace_slug)
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(prospect, field, value)
    db.commit()
    db.refresh(prospect)
    return ProspectResponse.model_validate(prospect)
