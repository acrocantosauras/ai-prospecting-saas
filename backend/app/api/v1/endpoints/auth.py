"""Authentication endpoints: status, login, logout and the current session.

Login issues an opaque session token in an HttpOnly cookie plus a CSRF token in
a readable cookie. The CSRF token must be echoed in the configured header on
state-changing requests. Clients that cannot use cookies (scripts, tests) may
send the same token as ``Authorization: Bearer <token>``; that flow is exempt
from CSRF because browsers never attach it automatically.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.auth.dependencies import Authenticated, CurrentUser
from app.auth.service import (
    authenticate,
    create_session,
    login_throttle,
    memberships_for_user,
    revoke_session,
)
from app.config import get_settings
from app.core.database import get_db
from app.models import User
from app.schemas.auth import (
    AuthStatusResponse,
    LoginRequest,
    SessionResponse,
    UserSummary,
    WorkspaceAccessResponse,
)

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]


def _workspace_payload(db: Session, user: User) -> tuple[list[WorkspaceAccessResponse], WorkspaceAccessResponse | None]:
    accesses = memberships_for_user(db, user)
    workspaces = [
        WorkspaceAccessResponse(
            id=access.workspace.id,
            slug=access.workspace.slug,
            name=access.workspace.name,
            role=access.role,
        )
        for access in accesses
    ]
    return workspaces, (workspaces[0] if workspaces else None)


def _set_auth_cookies(response: Response, token: str, csrf_token: str) -> None:
    settings = get_settings()
    max_age = settings.auth_session_ttl_hours * 3600
    common = {
        "max_age": max_age,
        "secure": settings.auth_cookie_secure,
        "samesite": (settings.auth_cookie_samesite or "lax").lower(),
        "path": "/",
    }
    if settings.auth_cookie_domain:
        common["domain"] = settings.auth_cookie_domain
    response.set_cookie(
        key=settings.auth_session_cookie, value=token, httponly=True, **common
    )
    # Readable by the app so it can echo the value in the CSRF header.
    response.set_cookie(
        key=settings.auth_csrf_cookie, value=csrf_token, httponly=False, **common
    )


def _clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    extra = {"path": "/"}
    if settings.auth_cookie_domain:
        extra["domain"] = settings.auth_cookie_domain
    response.delete_cookie(settings.auth_session_cookie, **extra)
    response.delete_cookie(settings.auth_csrf_cookie, **extra)


@router.get("/status", response_model=AuthStatusResponse)
def auth_status(db: DbSession) -> AuthStatusResponse:
    """Report whether authentication works and whether any account exists."""
    return AuthStatusResponse(
        authentication_available=True,
        bootstrap_required=db.query(User).count() == 0,
    )


@router.post("/login", response_model=SessionResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> SessionResponse:
    """Authenticate with email and password and start a session."""
    client = request.client.host if request.client else "unknown"
    retry_after = login_throttle.retry_after(payload.email, client)
    if retry_after > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed sign-in attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )
    user = authenticate(db, payload.email, payload.password)
    if user is None:
        login_throttle.record_failure(payload.email, client)
        # One message for unknown email and wrong password: no enumeration.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    login_throttle.reset(payload.email, client)
    _, token, csrf_token = create_session(db, user)
    _set_auth_cookies(response, token, csrf_token)
    workspaces, active = _workspace_payload(db, user)
    return SessionResponse(
        user=UserSummary.model_validate(user),
        workspaces=workspaces,
        workspace=active,
        csrf_token=csrf_token,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    db: DbSession,
    auth: Authenticated,
) -> Response:
    """Revoke the current session and clear its cookies."""
    revoke_session(db, auth.session)
    _clear_auth_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=SessionResponse)
def me(
    user: CurrentUser,
    db: DbSession,
    workspace_slug: str | None = Query(default=None, max_length=100),
) -> SessionResponse:
    """Return the caller's identity and reachable workspaces."""
    workspaces, active = _workspace_payload(db, user)
    if workspace_slug:
        wanted = workspace_slug.strip()
        match = next(
            (
                item
                for item in workspaces
                if item.slug == wanted or str(item.id) == wanted
            ),
            None,
        )
        if match is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
            )
        active = match
    return SessionResponse(
        user=UserSummary.model_validate(user),
        workspaces=workspaces,
        workspace=active,
        csrf_token=None,
    )

