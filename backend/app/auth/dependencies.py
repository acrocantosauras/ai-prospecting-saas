"""FastAPI dependencies for authentication, workspace and permission checks.

Every protected route depends on either :data:`CurrentUser` (when the workspace
is selected by the request body) or :data:`WorkspaceContext` (when it is selected
by the ``workspace_slug`` query parameter). No route reads ``workspace_slug`` or
``workspace_id`` on its own, so authorization cannot drift between endpoints.

Error policy:

* 401 - no session, expired session, revoked session, bad credentials.
* 404 - the requested workspace is not one the caller is an active member of,
  and every resource outside the caller's workspace. This avoids confirming
  that another tenant's data exists.
* 403 - the caller is a member but their role lacks the permission.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.auth.permissions import Permission, has_permission
from app.auth.security import digests_match
from app.auth.service import find_session, memberships_for_user
from app.config import get_settings
from app.core.database import get_db
from app.models import AuthSession, User, Workspace, WorkspaceMembership

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True)
class AuthenticatedSession:
    """The authenticated user plus the session that proved the identity."""

    user: User
    session: AuthSession
    method: str  # "cookie" | "bearer"


@dataclass(frozen=True)
class WorkspaceContext:
    """An authenticated user inside one workspace they are authorized for."""

    user: User
    workspace: Workspace
    role: str
    membership: WorkspaceMembership
    session: AuthSession | None = None

    def has(self, permission: Permission) -> bool:
        """Return True when this context's role grants ``permission``."""
        return has_permission(self.role, permission)


def _unauthorized(detail: str = "Authentication required") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _presented_token(request: Request) -> tuple[str | None, str]:
    """Return ``(token, method)`` for a bearer header or the session cookie."""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None, "bearer"
    cookie_name = get_settings().auth_session_cookie
    return request.cookies.get(cookie_name), "cookie"


def _check_csrf(request: Request, session: AuthSession, method: str) -> None:
    """Reject state-changing cookie-authenticated requests without a CSRF token.

    Bearer tokens are not sent automatically by browsers, so they are exempt.
    """
    if method != "cookie" or request.method in SAFE_METHODS:
        return
    settings = get_settings()
    presented = request.headers.get(settings.auth_csrf_header, "")
    if not digests_match(presented, session.csrf_token_hash):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed",
        )


def get_authenticated_session(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> AuthenticatedSession:
    """Resolve the caller's session or raise 401."""
    token, method = _presented_token(request)
    if not token:
        raise _unauthorized()
    session = find_session(db, token)
    if session is None:
        raise _unauthorized("Session is invalid or has expired")
    _check_csrf(request, session, method)
    return AuthenticatedSession(user=session.user, session=session, method=method)


def get_current_user(
    auth: Annotated[AuthenticatedSession, Depends(get_authenticated_session)],
) -> User:
    """Return the authenticated user (401 when unauthenticated)."""
    return auth.user


CurrentUser = Annotated[User, Depends(get_current_user)]
Authenticated = Annotated[AuthenticatedSession, Depends(get_authenticated_session)]


def resolve_workspace_context(
    db: Session, user: User, selector: str | None
) -> WorkspaceContext:
    """Resolve ``selector`` (slug or UUID) to a workspace the user belongs to.

    When ``selector`` is empty the user must have exactly one active membership,
    otherwise the client has to name the workspace explicitly.
    """
    accesses = memberships_for_user(db, user)
    if not accesses:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )
    wanted = (selector or "").strip()
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
            # Same response as a nonexistent workspace: membership is the only
            # thing that makes a workspace visible.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
            )
    else:
        if len(accesses) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="workspace_slug is required when you belong to multiple workspaces",
            )
        match = accesses[0]

    membership = (
        db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.user_id == user.id,
            WorkspaceMembership.workspace_id == match.workspace.id,
            WorkspaceMembership.is_active.is_(True),
        )
        .first()
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )
    # Defensive: refuse a membership whose stored role is not a known role.
    if membership.role not in ("owner", "admin", "member", "viewer"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace membership is not valid",
        )
    return WorkspaceContext(
        user=user,
        workspace=match.workspace,
        role=membership.role,
        membership=membership,
    )


def get_workspace_context(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    auth: Authenticated,
    workspace_slug: str | None = Query(
        default=None,
        max_length=100,
        description="Workspace slug. Must match one of the caller's active memberships.",
    ),
) -> WorkspaceContext:
    """Return the authorized workspace for the ``workspace_slug`` query parameter."""
    context = resolve_workspace_context(db, auth.user, workspace_slug)
    return WorkspaceContext(
        user=context.user,
        workspace=context.workspace,
        role=context.role,
        membership=context.membership,
        session=auth.session,
    )



WorkspaceCtx = Annotated[WorkspaceContext, Depends(get_workspace_context)]


def ensure_permission(context: WorkspaceContext, permission: Permission) -> None:
    """Raise 403 unless the context's role grants ``permission``."""
    if not context.has(permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your workspace role does not allow this action ({permission.value})",
        )

