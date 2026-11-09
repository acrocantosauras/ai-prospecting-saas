"""Workspace membership and settings endpoints.

Workspace deletion is intentionally absent: the schema defines no cascade rules,
so deleting a workspace would orphan batches, prospects, usage and qualification
records. That needs a product and migration decision rather than a shortcut here
(see the sprint report). The ``workspace:delete`` permission stays reserved for
owners so the API can add it once cascades exist.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, WorkspaceCtx, ensure_permission
from app.auth.permissions import Permission, Role, parse_role
from app.auth.service import (
    get_user_by_email,
    memberships_for_user,
    owner_count,
    upsert_membership,
)
from app.core.database import get_db
from app.models import User, WorkspaceMembership
from app.schemas.auth import (
    MemberAddRequest,
    MemberResponse,
    MemberUpdateRequest,
    WorkspaceAccessResponse,
    WorkspaceSettingsUpdate,
)

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]


def _member_payload(membership: WorkspaceMembership, user: User) -> MemberResponse:
    return MemberResponse(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=membership.role,
        is_active=membership.is_active,
        created_at=membership.created_at,
    )


def _membership_or_404(
    db: Session, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[WorkspaceMembership, User]:
    row = (
        db.query(WorkspaceMembership, User)
        .join(User, WorkspaceMembership.user_id == User.id)
        .filter(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Member not found"
        )
    return row


@router.get("/", response_model=list[WorkspaceAccessResponse])
def list_my_workspaces(
    user: CurrentUser,
    db: DbSession,
    workspace_slug: str | None = Query(
        default=None, max_length=100, description="Optional workspace selector."
    ),
) -> list[WorkspaceAccessResponse]:
    """Return every workspace the caller is an active member of.

    When a ``workspace_slug`` is supplied it is used only to validate that the
    caller is authorized for that specific workspace; unauthorized selectors
    return 404 rather than confirming that another tenant exists.
    """
    accesses = memberships_for_user(db, user)
    wanted = (workspace_slug or "").strip()
    if wanted:
        match = next(
            (
                access
                for access in accesses
                if access.workspace.slug == wanted
                or str(access.workspace.id) == wanted
            ),
            None,
        )
        if match is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
            )
        # Return the single matching workspace so the selector is never silently ignored.
        return [
            WorkspaceAccessResponse(
                id=match.workspace.id,
                slug=match.workspace.slug,
                name=match.workspace.name,
                role=match.role,
            )
        ]
    return [
        WorkspaceAccessResponse(
            id=access.workspace.id,
            slug=access.workspace.slug,
            name=access.workspace.name,
            role=access.role,
        )
        for access in accesses
    ]


@router.get("/{slug}/members", response_model=list[MemberResponse])
def list_members(
    ctx: WorkspaceCtx,
    db: DbSession,
) -> list[MemberResponse]:
    """List members of the active workspace."""
    ensure_permission(ctx, Permission.VIEW_WORKSPACE)
    rows = (
        db.query(WorkspaceMembership, User)
        .join(User, WorkspaceMembership.user_id == User.id)
        .filter(WorkspaceMembership.workspace_id == ctx.workspace.id)
        .order_by(WorkspaceMembership.role, User.email)
        .all()
    )
    return [_member_payload(membership, user) for membership, user in rows]


@router.post(
    "/{slug}/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    data: MemberAddRequest,
    ctx: WorkspaceCtx,
    db: DbSession,
) -> MemberResponse:
    """Add an existing account to the workspace with an explicit role.

    Invitations by email are not implemented (no mail provider is configured),
    so an account must already exist. Creating accounts from a workspace is not
    allowed: that would let an admin mint identities.
    """
    ensure_permission(ctx, Permission.MANAGE_MEMBERS)
    role = parse_role(data.role)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown workspace role"
        )
    if role is Role.OWNER and ctx.role != Role.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an owner can grant the owner role",
        )
    target = get_user_by_email(db, data.email)
    if target is None or not target.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active account exists for that email address",
        )
    existing = (
        db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.workspace_id == ctx.workspace.id,
            WorkspaceMembership.user_id == target.id,
        )
        .first()
    )
    if existing is not None and existing.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That account is already a member of this workspace",
        )
    membership = upsert_membership(db, target, ctx.workspace, role.value)
    return _member_payload(membership, target)


@router.patch("/{slug}/members/{user_id}", response_model=MemberResponse)
def update_member(
    user_id: uuid.UUID,
    data: MemberUpdateRequest,
    ctx: WorkspaceCtx,
    db: DbSession,
) -> MemberResponse:
    """Change a member's role or revoke their access."""
    ensure_permission(ctx, Permission.MANAGE_MEMBERS)
    membership, target = _membership_or_404(db, ctx.workspace.id, user_id)

    if membership.role == Role.OWNER and ctx.role != Role.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an owner can change another owner's membership",
        )

    new_role = membership.role
    if data.role is not None:
        parsed = parse_role(data.role)
        if parsed is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unknown workspace role",
            )
        if parsed is Role.OWNER and ctx.role != Role.OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only an owner can grant the owner role",
            )
        new_role = parsed.value

    new_active = membership.is_active if data.is_active is None else data.is_active
    loses_owner = membership.role == Role.OWNER and (
        new_role != Role.OWNER or not new_active
    )
    if loses_owner and owner_count(db, ctx.workspace.id) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A workspace must keep at least one active owner",
        )

    membership.role = new_role
    membership.is_active = new_active
    db.commit()
    db.refresh(membership)
    return _member_payload(membership, target)


@router.delete(
    "/{slug}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_member(
    user_id: uuid.UUID,
    ctx: WorkspaceCtx,
    db: DbSession,
) -> None:
    """Revoke a member's access (the row is kept for audit)."""
    ensure_permission(ctx, Permission.MANAGE_MEMBERS)
    membership, _ = _membership_or_404(db, ctx.workspace.id, user_id)
    if membership.role == Role.OWNER and ctx.role != Role.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an owner can remove another owner",
        )
    if membership.role == Role.OWNER and owner_count(db, ctx.workspace.id) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A workspace must keep at least one active owner",
        )
    membership.is_active = False
    db.commit()
    return None


@router.patch("/{slug}", response_model=WorkspaceAccessResponse)
def update_workspace_settings(
    data: WorkspaceSettingsUpdate,
    ctx: WorkspaceCtx,
    db: DbSession,
) -> WorkspaceAccessResponse:
    """Rename the workspace (admins and owners only)."""
    ensure_permission(ctx, Permission.MANAGE_SETTINGS)
    if data.name is not None:
        ctx.workspace.name = data.name
        db.commit()
        db.refresh(ctx.workspace)
    return WorkspaceAccessResponse(
        id=ctx.workspace.id,
        slug=ctx.workspace.slug,
        name=ctx.workspace.name,
        role=ctx.role,
    )

