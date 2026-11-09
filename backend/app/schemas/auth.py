"""Schemas for authentication, sessions and workspace membership."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Credentials submitted to the login endpoint."""

    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=1, max_length=1024)


class UserSummary(BaseModel):
    """Public identity of the authenticated user."""

    id: uuid.UUID
    email: str
    display_name: str | None = None

    model_config = {"from_attributes": True}


class WorkspaceAccessResponse(BaseModel):
    """One workspace the caller may act in, with the role that grants it."""

    id: uuid.UUID
    slug: str
    name: str
    role: str


class SessionResponse(BaseModel):
    """Current session: identity, reachable workspaces and a CSRF token."""

    user: UserSummary
    workspaces: list[WorkspaceAccessResponse]
    workspace: WorkspaceAccessResponse | None = None
    csrf_token: str | None = None


class AuthStatusResponse(BaseModel):
    """Unauthenticated status so the UI can explain what to do next."""

    authentication_available: bool
    bootstrap_required: bool


class MemberResponse(BaseModel):
    """A workspace member and their role."""

    user_id: uuid.UUID
    email: str
    display_name: str | None = None
    role: str
    is_active: bool
    created_at: datetime | None = None


class MemberAddRequest(BaseModel):
    """Add an existing account to a workspace."""

    email: str = Field(..., min_length=3, max_length=320)
    role: str = Field(default="member", max_length=16)


class MemberUpdateRequest(BaseModel):
    """Change a member's role or revoke their access."""

    role: str | None = Field(default=None, max_length=16)
    is_active: bool | None = None


class WorkspaceSettingsUpdate(BaseModel):
    """Workspace settings a workspace admin may change."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
