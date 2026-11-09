"""Business profile API endpoints.

The workspace is resolved from the authenticated session and an active
membership. A ``workspace_slug``/``workspace_id`` supplied by the client is only
a selector: naming a workspace the caller does not belong to returns 404.
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
from app.models import ClientProfile, Workspace
from app.schemas import (
    ClientProfileCreate,
    ClientProfileResponse,
    ClientProfileUpdate,
)

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]


def get_client_profile_or_404(
    db: Session, profile_id: uuid.UUID, workspace: Workspace
) -> ClientProfile:
    """Return a client profile from this workspace, or raise 404."""
    profile = (
        db.query(ClientProfile)
        .filter(
            ClientProfile.id == profile_id,
            ClientProfile.workspace_id == workspace.id,
        )
        .first()
    )
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Client profile not found"
        )
    return profile


@router.post("/", response_model=ClientProfileResponse, status_code=status.HTTP_201_CREATED)
def create_client_profile(
    data: ClientProfileCreate,
    db: DbSession,
    user: CurrentUser,
) -> ClientProfileResponse:
    """Create a client profile in the caller's workspace."""
    ctx: WorkspaceContext = resolve_workspace_context(db, user, data.workspace_id)
    ensure_permission(ctx, Permission.MANAGE_PROFILES)
    profile = ClientProfile(
        workspace_id=ctx.workspace.id,
        name=data.name,
        website=data.website,
        description=data.description,
        products_services=data.products_services,
        value_proposition=data.value_proposition,
        target_audience=data.target_audience,
        problems_solved=data.problems_solved,
        usp=data.usp,
        is_active=data.is_active,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return ClientProfileResponse.model_validate(profile)


@router.get("/", response_model=list[ClientProfileResponse])
def list_client_profiles(
    db: DbSession,
    ctx: WorkspaceCtx,
) -> list[ClientProfileResponse]:
    """List client profiles in the caller's workspace."""
    ensure_permission(ctx, Permission.VIEW_WORKSPACE)
    profiles = (
        db.query(ClientProfile)
        .filter(ClientProfile.workspace_id == ctx.workspace.id)
        .order_by(ClientProfile.created_at.desc())
        .all()
    )
    return [ClientProfileResponse.model_validate(p) for p in profiles]


@router.get("/{profile_id}", response_model=ClientProfileResponse)
def get_client_profile(
    profile_id: uuid.UUID,
    db: DbSession,
    ctx: WorkspaceCtx,
) -> ClientProfileResponse:
    """Return one client profile from the caller's workspace."""
    ensure_permission(ctx, Permission.VIEW_WORKSPACE)
    profile = get_client_profile_or_404(db, profile_id, ctx.workspace)
    return ClientProfileResponse.model_validate(profile)


@router.put("/{profile_id}", response_model=ClientProfileResponse)
def update_client_profile(
    profile_id: uuid.UUID,
    data: ClientProfileUpdate,
    db: DbSession,
    ctx: WorkspaceCtx,
) -> ClientProfileResponse:
    """Update a client profile (members and above)."""
    ensure_permission(ctx, Permission.MANAGE_PROFILES)
    profile = get_client_profile_or_404(db, profile_id, ctx.workspace)
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return ClientProfileResponse.model_validate(profile)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client_profile(
    profile_id: uuid.UUID,
    db: DbSession,
    ctx: WorkspaceCtx,
) -> None:
    """Delete a client profile (members and above)."""
    ensure_permission(ctx, Permission.MANAGE_PROFILES)
    profile = get_client_profile_or_404(db, profile_id, ctx.workspace)
    db.delete(profile)
    db.commit()
    return None
