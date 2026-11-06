"""Business profile API endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.database import get_db
from app.models import ClientProfile, Workspace
from app.schemas import (
    ClientProfileCreate,
    ClientProfileUpdate,
    ClientProfileResponse,
)

router = APIRouter()


def get_client_profile_or_404(db, profile_id: uuid.UUID, workspace_slug: str):
    profile = db.query(ClientProfile).filter(
        ClientProfile.id == profile_id,
        ClientProfile.workspace.has(slug=workspace_slug),
    ).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client profile not found")
    return profile


@router.post("/", response_model=ClientProfileResponse, status_code=status.HTTP_201_CREATED)
def create_client_profile(
    data: ClientProfileCreate,
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
    profile = ClientProfile(
        workspace_id=workspace.id,
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
    workspace_slug: str,
    db=Depends(get_db),
):
    profiles = (
        db.query(ClientProfile)
        .filter(ClientProfile.workspace.has(slug=workspace_slug))
        .order_by(ClientProfile.created_at.desc())
        .all()
    )
    return [ClientProfileResponse.model_validate(p) for p in profiles]


@router.get("/{profile_id}", response_model=ClientProfileResponse)
def get_client_profile(
    profile_id: uuid.UUID,
    workspace_slug: str,
    db=Depends(get_db),
):
    profile = get_client_profile_or_404(db, profile_id, workspace_slug)
    return ClientProfileResponse.model_validate(profile)


@router.put("/{profile_id}", response_model=ClientProfileResponse)
def update_client_profile(
    profile_id: uuid.UUID,
    data: ClientProfileUpdate,
    workspace_slug: str,
    db=Depends(get_db),
):
    profile = get_client_profile_or_404(db, profile_id, workspace_slug)
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
    workspace_slug: str,
    db=Depends(get_db),
):
    profile = get_client_profile_or_404(db, profile_id, workspace_slug)
    db.delete(profile)
    db.commit()
    return None
