"""Authentication, session and membership services.

Everything here is synchronous and uses the request-scoped SQLAlchemy session,
so the background worker never depends on a live HTTP session.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.permissions import Role, parse_role
from app.auth.security import (
    dummy_password_hash,
    hash_password,
    new_csrf_token,
    new_session_token,
    token_digest,
    validate_password_strength,
    verify_password,
)
from app.config import get_settings
from app.models import AuthSession, User, Workspace, WorkspaceMembership

logger = logging.getLogger(__name__)

LAST_SEEN_WRITE_INTERVAL_SECONDS = 300


def utcnow() -> datetime:
    """Return the current time as an aware UTC datetime."""
    return datetime.now(UTC)


def as_utc(value: datetime | None) -> datetime | None:
    """Normalise a database datetime to aware UTC.

    SQLite drops tzinfo, so values read back are treated as UTC when naive.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def normalize_email(email: str | None) -> str:
    """Return the canonical form used for storage and lookup."""
    return (email or "").strip().lower()


def get_user_by_email(db: Session, email: str | None) -> User | None:
    """Return the user with this email address, if any."""
    normalized = normalize_email(email)
    if not normalized:
        return None
    return db.query(User).filter(func.lower(User.email) == normalized).first()


def create_user(
    db: Session,
    email: str,
    password: str,
    display_name: str | None = None,
) -> User:
    """Create a user account with a hashed password.

    Raises:
        ValueError: for an invalid/duplicate email or a weak password.

    """
    normalized = normalize_email(email)
    if "@" not in normalized or normalized.startswith("@") or len(normalized) > 320:
        raise ValueError("A valid email address is required")
    validate_password_strength(password)
    if get_user_by_email(db, normalized) is not None:
        raise ValueError("A user with that email already exists")
    user = User(
        email=normalized,
        password_hash=hash_password(password),
        display_name=(display_name or normalized)[:255],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def set_password(db: Session, user: User, password: str) -> None:
    """Replace a user's password and revoke all of their sessions."""
    validate_password_strength(password)
    user.password_hash = hash_password(password)
    db.query(AuthSession).filter(
        AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)
    ).update({"revoked_at": utcnow()}, synchronize_session=False)
    db.commit()


def authenticate(db: Session, email: str, password: str) -> User | None:
    """Return the user when the credentials are valid, else ``None``.

    A dummy verification runs for unknown or inactive accounts so the response
    time does not reveal whether an email is registered.
    """
    user = get_user_by_email(db, email)
    if user is None or not user.is_active:
        verify_password(password or "", dummy_password_hash())
        return None
    if not verify_password(password or "", user.password_hash):
        return None
    return user


@dataclass(frozen=True)
class WorkspaceAccess:
    """One workspace a user can reach, with the role that grants access."""

    workspace: Workspace
    role: str


def memberships_for_user(db: Session, user: User) -> list[WorkspaceAccess]:
    """Return every workspace where the user holds an active membership."""
    rows = (
        db.query(WorkspaceMembership, Workspace)
        .join(Workspace, WorkspaceMembership.workspace_id == Workspace.id)
        .filter(
            WorkspaceMembership.user_id == user.id,
            WorkspaceMembership.is_active.is_(True),
        )
        .order_by(Workspace.name)
        .all()
    )
    return [WorkspaceAccess(workspace=workspace, role=membership.role) for membership, workspace in rows]


def active_membership(
    db: Session, user: User, workspace_id: uuid.UUID
) -> WorkspaceMembership | None:
    """Return the user's active membership for one workspace, if any."""
    return (
        db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.user_id == user.id,
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.is_active.is_(True),
        )
        .first()
    )


def upsert_membership(
    db: Session, user: User, workspace: Workspace, role: str = Role.MEMBER
) -> WorkspaceMembership:
    """Create or reactivate a membership with exactly the requested role.

    Raises:
        ValueError: when ``role`` is not a known role.

    """
    if parse_role(role) is None:
        raise ValueError("Unknown workspace role")
    membership = (
        db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.user_id == user.id,
            WorkspaceMembership.workspace_id == workspace.id,
        )
        .first()
    )
    if membership is None:
        membership = WorkspaceMembership(
            user_id=user.id, workspace_id=workspace.id, role=role, is_active=True
        )
        db.add(membership)
    else:
        membership.role = role
        membership.is_active = True
    db.commit()
    db.refresh(membership)
    return membership


def owner_count(db: Session, workspace_id: uuid.UUID) -> int:
    """Return the number of active owners in a workspace."""
    return (
        db.query(WorkspaceMembership)
        .filter(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.role == Role.OWNER,
            WorkspaceMembership.is_active.is_(True),
        )
        .count()
    )


def workspaces_without_owner(db: Session) -> list[str]:
    """Return slugs of workspaces that have no active owner.

    These are legacy/demo rows created before authentication existed. They stay
    inaccessible to everyone until an operator links an account explicitly.
    """
    owned = db.query(WorkspaceMembership.workspace_id).filter(
        WorkspaceMembership.role == Role.OWNER,
        WorkspaceMembership.is_active.is_(True),
    )
    rows = db.query(Workspace.slug).filter(~Workspace.id.in_(owned)).order_by(Workspace.slug).all()
    return [slug for (slug,) in rows]


def create_session(db: Session, user: User) -> tuple[AuthSession, str, str]:
    """Create a session and return ``(session, token, csrf_token)``.

    Only digests of the token and CSRF secret are persisted. Older sessions
    beyond the configured cap are revoked so a stolen cookie cannot accumulate.
    """
    settings = get_settings()
    now = utcnow()
    token = new_session_token()
    csrf_token = new_csrf_token()
    session = AuthSession(
        user_id=user.id,
        token_hash=token_digest(token),
        csrf_token_hash=token_digest(csrf_token),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=settings.auth_session_ttl_hours),
    )
    db.add(session)
    user.last_login_at = now
    _revoke_excess_sessions(db, user, settings.auth_max_active_sessions)
    db.commit()
    db.refresh(session)
    return session, token, csrf_token


def _revoke_excess_sessions(db: Session, user: User, keep: int) -> None:
    """Revoke the oldest active sessions so at most ``keep`` remain."""
    if keep <= 0:
        return
    active = (
        db.query(AuthSession)
        .filter(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .order_by(AuthSession.created_at.desc())
        .all()
    )
    for stale in active[keep:]:
        stale.revoked_at = utcnow()


def find_session(db: Session, token: str) -> AuthSession | None:
    """Return a live session for an opaque token, or ``None``.

    Expired and idle sessions are revoked on sight. Revoked sessions are never
    returned, so logout and revocation take effect immediately.
    """
    if not token or len(token) > 512:
        return None
    session = (
        db.query(AuthSession)
        .filter(AuthSession.token_hash == token_digest(token))
        .first()
    )
    if session is None:
        return None
    now = utcnow()
    if session.revoked_at is not None:
        return None
    expires_at = as_utc(session.expires_at)
    if expires_at is None or expires_at <= now:
        session.revoked_at = now
        db.commit()
        return None
    idle_timeout = timedelta(minutes=get_settings().auth_session_idle_minutes)
    last_seen = as_utc(session.last_seen_at) or now
    if last_seen + idle_timeout <= now:
        session.revoked_at = now
        db.commit()
        return None
    if not session.user or not session.user.is_active:
        return None
    if (now - last_seen).total_seconds() > LAST_SEEN_WRITE_INTERVAL_SECONDS:
        session.last_seen_at = now
        db.commit()
    return session


def revoke_session(db: Session, session: AuthSession) -> None:
    """Revoke one session immediately."""
    if session.revoked_at is None:
        session.revoked_at = utcnow()
        db.commit()


def revoke_all_sessions(db: Session, user: User) -> None:
    """Revoke every active session for a user."""
    db.query(AuthSession).filter(
        AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)
    ).update({"revoked_at": utcnow()}, synchronize_session=False)
    db.commit()


class LoginThrottle:
    """In-process failed-login limiter keyed by email and client address.

    This is deliberately simple: it slows down online password guessing for the
    single-process deployment this project ships with. A multi-worker deployment
    must move the counters to shared storage (Redis) - documented as a residual
    risk, not silently assumed to work.
    """

    def __init__(self) -> None:
        """Create an empty limiter."""
        self._events: dict[tuple[str, str], list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: tuple[str, str], window: float, now: float) -> list[float]:
        events = [stamp for stamp in self._events.get(key, []) if now - stamp < window]
        if events:
            self._events[key] = events
        else:
            self._events.pop(key, None)
        return events

    def retry_after(self, email: str, client: str) -> int:
        """Return seconds to wait before another attempt (0 when allowed)."""
        settings = get_settings()
        window = float(settings.auth_login_window_seconds)
        now = time.monotonic()
        key = (normalize_email(email), client or "unknown")
        with self._lock:
            events = self._recent(key, window, now)
            if len(events) < settings.auth_login_max_failures:
                return 0
            return max(1, int(window - (now - events[0])))

    def record_failure(self, email: str, client: str) -> None:
        """Record one failed attempt."""
        settings = get_settings()
        window = float(settings.auth_login_window_seconds)
        now = time.monotonic()
        key = (normalize_email(email), client or "unknown")
        with self._lock:
            self._recent(key, window, now)
            self._events.setdefault(key, []).append(now)

    def reset(self, email: str, client: str) -> None:
        """Clear failures after a successful login."""
        key = (normalize_email(email), client or "unknown")
        with self._lock:
            self._events.pop(key, None)

    def clear(self) -> None:
        """Drop all counters (used by tests)."""
        with self._lock:
            self._events.clear()


login_throttle = LoginThrottle()


def bootstrap_owner(
    db: Session,
    email: str,
    password: str,
    workspace_slug: str,
    workspace_name: str | None = None,
    role: str = Role.OWNER,
) -> tuple[User, Workspace, bool]:
    """Ensure a user exists and owns/joins a workspace.

    Returns ``(user, workspace, created_user)``. Existing accounts keep their
    current password: the bootstrap path never overwrites a credential.
    """
    created_user = False
    user = get_user_by_email(db, email)
    if user is None:
        user = create_user(db, email, password)
        created_user = True
    workspace = db.query(Workspace).filter(Workspace.slug == workspace_slug).first()
    if workspace is None:
        if parse_role(role) is None:
            raise ValueError("Unknown workspace role")
        workspace = Workspace(
            slug=workspace_slug, name=workspace_name or workspace_slug
        )
        db.add(workspace)
        db.commit()
        db.refresh(workspace)
    upsert_membership(db, user, workspace, role)
    return user, workspace, created_user


def create_workspace_for_user(
    db: Session, user: User, slug: str, name: str
) -> Workspace:
    """Create a workspace and make ``user`` its owner."""
    workspace = Workspace(slug=slug, name=name)
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    upsert_membership(db, user, workspace, Role.OWNER)
    return workspace
