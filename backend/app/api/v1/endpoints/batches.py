"""Prospect batch API endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks

from app.core.database import get_db
from app.models import ProspectBatch, ICPProfile, ClientProfile, Workspace
from app.schemas import (
    ProspectBatchCreate,
    ProspectBatchUpdate,
    ProspectBatchStageUpdate,
    ProspectBatchResponse,
    ProspectBatchListResponse,
)
from app.services.prospecting import run_prospecting_pipeline

router = APIRouter()


def get_batch_or_404(db, batch_id: uuid.UUID, workspace_slug: str):
    batch = (
        db.query(ProspectBatch)
        .filter(ProspectBatch.id == batch_id, ProspectBatch.workspace.has(slug=workspace_slug))
        .first()
    )
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")
    return batch


@router.post("/", response_model=ProspectBatchResponse, status_code=status.HTTP_201_CREATED)
def create_batch(
    data: ProspectBatchCreate,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
):
    # Accept workspace_id as either a slug or a UUID
    workspace = db.query(Workspace).filter(Workspace.slug == data.workspace_id).first()
    if not workspace:
        # Try as UUID
        try:
            ws_uuid = uuid.UUID(data.workspace_id)
            workspace = db.query(Workspace).filter(Workspace.id == ws_uuid).first()
        except (ValueError, AttributeError):
            pass
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    icp = (
        db.query(ICPProfile)
        .filter(ICPProfile.id == data.icp_profile_id, ICPProfile.workspace_id == workspace.id)
        .first()
    )
    if not icp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ICP profile not found")
    batch = ProspectBatch(
        workspace_id=workspace.id,
        icp_profile_id=icp.id,
        # Fall back to the ICP's linked client profile so the pipeline always
        # has the customer context it needs to explain "why it fits".
        client_profile_id=data.client_profile_id or icp.client_profile_id,
        name=data.name,
        requested_prospect_count=data.requested_prospect_count,
        source_mode="demo",
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    background_tasks.add_task(run_prospecting_pipeline, str(batch.id), str(workspace.slug))
    return ProspectBatchResponse.model_validate(batch)


@router.get("/", response_model=ProspectBatchListResponse)
def list_batches(
    workspace_slug: str,
    db=Depends(get_db),
):
    batches = (
        db.query(ProspectBatch)
        .filter(ProspectBatch.workspace.has(slug=workspace_slug))
        .order_by(ProspectBatch.created_at.desc())
        .all()
    )
    items = [ProspectBatchResponse.model_validate(b).model_dump() for b in batches]
    return ProspectBatchListResponse(items=items, total=len(items))


@router.get("/{batch_id}", response_model=ProspectBatchResponse)
def get_batch(
    batch_id: uuid.UUID,
    workspace_slug: str,
    db=Depends(get_db),
):
    batch = get_batch_or_404(db, batch_id, workspace_slug)
    return ProspectBatchResponse.model_validate(batch)


@router.put("/{batch_id}", response_model=ProspectBatchResponse)
def update_batch(
    batch_id: uuid.UUID,
    data: ProspectBatchUpdate,
    workspace_slug: str,
    db=Depends(get_db),
):
    batch = get_batch_or_404(db, batch_id, workspace_slug)
    if batch.status not in ("pending",):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot modify a non-pending batch")
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
    workspace_slug: str,
    db=Depends(get_db),
):
    batch = get_batch_or_404(db, batch_id, workspace_slug)
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
    workspace_slug: str,
    db=Depends(get_db),
):
    batch = get_batch_or_404(db, batch_id, workspace_slug)
    db.delete(batch)
    db.commit()
    return None
