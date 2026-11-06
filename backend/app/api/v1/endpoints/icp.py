"""ICP profile API endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.database import get_db
from app.models import ICPProfile, Workspace
from app.schemas import (
    ICPProfileCreate,
    ICPProfileUpdate,
    ICPProfileResponse,
)

router = APIRouter()


def get_icp_or_404(db, icp_id: uuid.UUID, workspace_slug: str):
    icp = db.query(ICPProfile).filter(
        ICPProfile.id == icp_id,
        ICPProfile.workspace.has(slug=workspace_slug),
    ).first()
    if not icp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ICP profile not found")
    return icp


@router.post("/", response_model=ICPProfileResponse, status_code=status.HTTP_201_CREATED)
def create_icp(
    data: ICPProfileCreate,
    db=Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.slug == data.workspace_id).first()
    if not workspace:
        try:
            ws_uuid = uuid.UUID(data.workspace_id)
            workspace = db.query(Workspace).filter(Workspace.id == ws_uuid).first()
        except (ValueError, AttributeError):
            pass
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    icp = ICPProfile(
        workspace_id=workspace.id,
        client_profile_id=data.client_profile_id,
        name=data.name,
        target_industries=data.target_industries,
        sub_industries=data.sub_industries,
        target_countries=data.target_countries,
        target_regions=data.target_regions,
        company_size=data.company_size,
        employee_count_min=data.employee_count_min,
        employee_count_max=data.employee_count_max,
        revenue_min=data.revenue_min,
        revenue_max=data.revenue_max,
        preferred_company_types=data.preferred_company_types,
        target_audience=data.target_audience,
        decision_maker_roles=data.decision_maker_roles,
        additional_criteria=data.additional_criteria,
        max_prospects=data.max_prospects,
        is_active=data.is_active,
    )
    db.add(icp)
    db.commit()
    db.refresh(icp)
    return ICPProfileResponse.model_validate(icp)


@router.get("/", response_model=list[ICPProfileResponse])
def list_icps(
    workspace_slug: str,
    db=Depends(get_db),
):
    icps = (
        db.query(ICPProfile)
        .filter(ICPProfile.workspace.has(slug=workspace_slug))
        .order_by(ICPProfile.created_at.desc())
        .all()
    )
    return [ICPProfileResponse.model_validate(i) for i in icps]


@router.get("/{icp_id}", response_model=ICPProfileResponse)
def get_icp(
    icp_id: uuid.UUID,
    workspace_slug: str,
    db=Depends(get_db),
):
    icp = get_icp_or_404(db, icp_id, workspace_slug)
    return ICPProfileResponse.model_validate(icp)


@router.put("/{icp_id}", response_model=ICPProfileResponse)
def update_icp(
    icp_id: uuid.UUID,
    data: ICPProfileUpdate,
    workspace_slug: str,
    db=Depends(get_db),
):
    icp = get_icp_or_404(db, icp_id, workspace_slug)
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(icp, field, value)
    db.commit()
    db.refresh(icp)
    return ICPProfileResponse.model_validate(icp)


@router.delete("/{icp_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_icp(
    icp_id: uuid.UUID,
    workspace_slug: str,
    db=Depends(get_db),
):
    icp = get_icp_or_404(db, icp_id, workspace_slug)
    db.delete(icp)
    db.commit()
    return None
