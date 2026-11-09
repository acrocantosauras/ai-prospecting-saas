"""ICP profile API endpoints.

Workspace isolation is derived from the authenticated membership, never from the
slug or id supplied by the client.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    CurrentUser,
    WorkspaceContext,
    WorkspaceCtx,
    ensure_permission,
    resolve_workspace_context,
)
from app.auth.permissions import Permission
from app.core.database import get_db
from app.models import ClientProfile, ICPProfile, Workspace
from app.schemas import (
    ICPProfileCreate,
    ICPProfileResponse,
    ICPProfileUpdate,
)

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]


def get_icp_or_404(db: Session, icp_id: uuid.UUID, workspace: Workspace) -> ICPProfile:
    """Return an ICP from this workspace, or raise 404."""
    icp = (
        db.query(ICPProfile)
        .filter(
            ICPProfile.id == icp_id,
            ICPProfile.workspace_id == workspace.id,
        )
        .first()
    )
    if not icp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ICP profile not found"
        )
    return icp


@router.post("/", response_model=ICPProfileResponse, status_code=status.HTTP_201_CREATED)
def create_icp(
    data: ICPProfileCreate,
    db: DbSession,
    user: CurrentUser,
) -> ICPProfileResponse:
    """Create an ICP inside the caller's workspace."""
    ctx: WorkspaceContext = resolve_workspace_context(db, user, data.workspace_id)
    ensure_permission(ctx, Permission.MANAGE_PROFILES)
    if data.client_profile_id is not None:
        profile = (
            db.query(ClientProfile)
            .filter(
                ClientProfile.id == data.client_profile_id,
                ClientProfile.workspace_id == ctx.workspace.id,
            )
            .first()
        )
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Client profile not found",
            )
    icp = ICPProfile(
        workspace_id=ctx.workspace.id,
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
def list_icps(db: DbSession, ctx: WorkspaceCtx) -> list[ICPProfileResponse]:
    """List ICPs in the caller's workspace."""
    ensure_permission(ctx, Permission.VIEW_WORKSPACE)
    icps = (
        db.query(ICPProfile)
        .filter(ICPProfile.workspace_id == ctx.workspace.id)
        .order_by(ICPProfile.created_at.desc())
        .all()
    )
    return [ICPProfileResponse.model_validate(i) for i in icps]


@router.get("/{icp_id}", response_model=ICPProfileResponse)
def get_icp(
    icp_id: uuid.UUID,
    db: DbSession,
    ctx: WorkspaceCtx,
) -> ICPProfileResponse:
    """Return one ICP from the caller's workspace."""
    ensure_permission(ctx, Permission.VIEW_WORKSPACE)
    icp = get_icp_or_404(db, icp_id, ctx.workspace)
    return ICPProfileResponse.model_validate(icp)


@router.put("/{icp_id}", response_model=ICPProfileResponse)
def update_icp(
    icp_id: uuid.UUID,
    data: ICPProfileUpdate,
    db: DbSession,
    ctx: WorkspaceCtx,
) -> ICPProfileResponse:
    """Update an ICP (members and above)."""
    ensure_permission(ctx, Permission.MANAGE_PROFILES)
    icp = get_icp_or_404(db, icp_id, ctx.workspace)
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
    db: DbSession,
    ctx: WorkspaceCtx,
) -> None:
    """Delete an ICP (members and above)."""
    ensure_permission(ctx, Permission.MANAGE_PROFILES)
    icp = get_icp_or_404(db, icp_id, ctx.workspace)
    db.delete(icp)
    db.commit()
    return None
