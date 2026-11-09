"""Prospect batch API endpoints.

Creating a batch requires membership plus the ``batches:run`` permission. The
batch stores ``workspace_id`` and the background task re-loads it from that
persisted association, so finishing an authorized job never needs a live user
session (and never trusts a slug supplied by a caller).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
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
from app.models import ClientProfile, ICPProfile, ProspectBatch, Workspace
from app.schemas import (
    ProspectBatchCreate,
    ProspectBatchListResponse,
    ProspectBatchResponse,
    ProspectBatchStageUpdate,
    ProspectBatchUpdate,
)
from app.services.prospecting import run_prospecting_pipeline

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]


def get_batch_or_404(
    db: Session, batch_id: uuid.UUID, workspace: Workspace
) -> ProspectBatch:
    """Return a batch from this workspace, or raise 404."""
    batch = (
        db.query(ProspectBatch)
        .filter(
            ProspectBatch.id == batch_id,
            ProspectBatch.workspace_id == workspace.id,
        )
        .first()
    )
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found"
        )
    return batch


@router.post("/", response_model=ProspectBatchResponse, status_code=status.HTTP_201_CREATED)
def create_batch(
    data: ProspectBatchCreate,
    background_tasks: BackgroundTasks,
    db: DbSession,
    user: CurrentUser,
) -> ProspectBatchResponse:
    """Create a batch and start the legacy prospecting pipeline."""
    ctx: WorkspaceContext = resolve_workspace_context(db, user, data.workspace_id)
    ensure_permission(ctx, Permission.RUN_BATCHES)
    icp = (
        db.query(ICPProfile)
        .filter(
            ICPProfile.id == data.icp_profile_id,
            ICPProfile.workspace_id == ctx.workspace.id,
        )
        .first()
    )
    if not icp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ICP profile not found"
        )
    # Never accept a client profile from another workspace.
    resolved_profile_id = data.client_profile_id or icp.client_profile_id
    if resolved_profile_id is not None:
        profile = (
            db.query(ClientProfile)
            .filter(
                ClientProfile.id == resolved_profile_id,
                ClientProfile.workspace_id == ctx.workspace.id,
            )
            .first()
        )
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Client profile not found",
            )
    batch = ProspectBatch(
        workspace_id=ctx.workspace.id,
        icp_profile_id=icp.id,
        client_profile_id=resolved_profile_id,
        name=data.name,
        requested_prospect_count=data.requested_prospect_count,
        source_mode="demo",
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    background_tasks.add_task(
        run_prospecting_pipeline, str(batch.id), str(batch.workspace_id)
    )
    return ProspectBatchResponse.model_validate(batch)


@router.get("/", response_model=ProspectBatchListResponse)
def list_batches(db: DbSession, ctx: WorkspaceCtx) -> ProspectBatchListResponse:
    """List batches in the caller's workspace."""
    ensure_permission(ctx, Permission.VIEW_WORKSPACE)
    batches = (
        db.query(ProspectBatch)
        .filter(ProspectBatch.workspace_id == ctx.workspace.id)
        .order_by(ProspectBatch.created_at.desc())
        .all()
    )
    items = [ProspectBatchResponse.model_validate(b).model_dump() for b in batches]
    return ProspectBatchListResponse(items=items, total=len(items))


@router.get("/{batch_id}", response_model=ProspectBatchResponse)
def get_batch(
    batch_id: uuid.UUID,
    db: DbSession,
    ctx: WorkspaceCtx,
) -> ProspectBatchResponse:
    """Return one batch from the caller's workspace."""
    ensure_permission(ctx, Permission.VIEW_WORKSPACE)
    batch = get_batch_or_404(db, batch_id, ctx.workspace)
    return ProspectBatchResponse.model_validate(batch)


@router.put("/{batch_id}", response_model=ProspectBatchResponse)
def update_batch(
    batch_id: uuid.UUID,
    data: ProspectBatchUpdate,
    db: DbSession,
    ctx: WorkspaceCtx,
) -> ProspectBatchResponse:
    """Update a still-pending batch."""
    ensure_permission(ctx, Permission.RUN_BATCHES)
    batch = get_batch_or_404(db, batch_id, ctx.workspace)
    if batch.status not in ("pending",):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify a non-pending batch",
        )
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(batch, field, value)
    db.commit()
    db.refresh(batch)
    return ProspectBatchResponse.model_validate(batch)


@router.patch("/{batch_id}/stage", response_model=ProspectBatchResponse)
def update_stage(
    batch_id: uuid.UUID,
    data: ProspectBatchStageUpdate,
    db: DbSession,
    ctx: WorkspaceCtx,
) -> ProspectBatchResponse:
    """Record a manual stage update for a batch."""
    ensure_permission(ctx, Permission.RUN_BATCHES)
    batch = get_batch_or_404(db, batch_id, ctx.workspace)
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(batch, field, value)
    db.commit()
    db.refresh(batch)
    return ProspectBatchResponse.model_validate(batch)


@router.delete("/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_batch(
    batch_id: uuid.UUID,
    db: DbSession,
    ctx: WorkspaceCtx,
) -> None:
    """Delete a batch from the caller's workspace."""
    ensure_permission(ctx, Permission.RUN_BATCHES)
    batch = get_batch_or_404(db, batch_id, ctx.workspace)
    db.delete(batch)
    db.commit()
    return None
