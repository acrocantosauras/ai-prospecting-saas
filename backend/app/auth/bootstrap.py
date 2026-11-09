"""Bootstrap, startup validation and operator tooling for authentication.

The application never creates accounts implicitly. Two explicit paths exist:

1. ``AUTH_BOOTSTRAP_EMAIL`` + ``AUTH_BOOTSTRAP_PASSWORD`` (and optionally
   ``AUTH_BOOTSTRAP_WORKSPACE_SLUG``) seed one account at startup. Both values
   must come from the environment; there is no default credential.
2. ``python -m app.auth.bootstrap --email ... --workspace-slug demo`` runs the
   same operation interactively, prompting for the password.

Existing workspaces (including the pre-authentication ``demo`` workspace) keep
their data. They are simply unreachable until an owner membership is linked,
which the startup log warns about.
"""

from __future__ import annotations

import argparse
import getpass
import logging
import sys
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.permissions import Role
from app.auth.service import (
    bootstrap_owner,
    create_user,
    get_user_by_email,
    upsert_membership,
    workspaces_without_owner,
)
from app.config import get_settings
from app.core.database import SessionLocal
from app.models import User, Workspace

logger = logging.getLogger(__name__)


def validate_auth_configuration() -> None:
    """Fail fast on an insecure authentication configuration.

    Raises:
        RuntimeError: when production settings would ship an insecure cookie.

    """
    settings = get_settings()
    environment = (settings.environment or "development").lower()
    problems: list[str] = []
    samesite = (settings.auth_cookie_samesite or "lax").lower()
    if samesite not in ("lax", "strict", "none"):
        problems.append("AUTH_COOKIE_SAMESITE must be one of lax, strict or none")
    if samesite == "none" and not settings.auth_cookie_secure:
        problems.append("AUTH_COOKIE_SAMESITE=none requires AUTH_COOKIE_SECURE=true")
    if environment == "production" and not settings.auth_cookie_secure:
        problems.append("AUTH_COOKIE_SECURE must be true in production")
    if settings.auth_session_ttl_hours <= 0:
        problems.append("AUTH_SESSION_TTL_HOURS must be positive")
    if settings.auth_session_idle_minutes <= 0:
        problems.append("AUTH_SESSION_IDLE_MINUTES must be positive")
    if problems:
        raise RuntimeError(
            "Insecure authentication configuration: " + "; ".join(problems)
        )


def _ensure_workspace(db: Session, slug: str, name: str) -> Workspace:
    workspace = db.query(Workspace).filter(Workspace.slug == slug).first()
    if workspace is None:
        workspace = Workspace(slug=slug, name=name or slug)
        db.add(workspace)
        db.commit()
        db.refresh(workspace)
    return workspace


def run_environment_bootstrap() -> dict[str, str] | None:
    """Seed the env-configured account when both variables are present."""
    settings = get_settings()
    email = (settings.auth_bootstrap_email or "").strip()
    password = settings.auth_bootstrap_password or ""
    if not email or not password:
        return None
    slug = (settings.auth_bootstrap_workspace_slug or settings.demo_workspace_slug).strip()
    name = settings.auth_bootstrap_workspace_name or "Demo Workspace"
    db = SessionLocal()
    try:
        user, workspace, created = bootstrap_owner(
            db, email, password, slug, name, Role.OWNER
        )
        logger.warning(
            "Authentication bootstrap %s account %s as owner of workspace '%s'. "
            "Unset AUTH_BOOTSTRAP_PASSWORD once the account exists.",
            "created" if created else "reused",
            user.email,
            workspace.slug,
        )
        return {"email": user.email, "workspace": workspace.slug}
    finally:
        db.close()


def run_startup_auth_setup() -> None:
    """Validate configuration, optionally seed, and warn about ownerless data.

    Raises:
        RuntimeError: when production has no account and no bootstrap config.

    """
    validate_auth_configuration()
    settings = get_settings()
    environment = (settings.environment or "development").lower()
    run_environment_bootstrap()

    db = SessionLocal()
    try:
        has_users = db.query(User).count() > 0
        if environment == "production" and not has_users:
            raise RuntimeError(
                "Authentication is not initialized: production has no user accounts. "
                "Create the first account with `python -m app.auth.bootstrap "
                "--email <admin@example.com> --workspace-slug <workspace>` or set "
                "AUTH_BOOTSTRAP_EMAIL and AUTH_BOOTSTRAP_PASSWORD for the first start."
            )
        ownerless = workspaces_without_owner(db)
        if ownerless:
            logger.warning(
                "Workspaces without an active owner are inaccessible until linked: %s. "
                "Run `python -m app.auth.bootstrap --link-workspace <slug> --email <user>`.",
                ", ".join(ownerless),
            )
        if not has_users:
            logger.warning(
                "No user accounts exist yet. Create one with "
                "`python -m app.auth.bootstrap --email <admin@example.com> "
                "--workspace-slug %s`.",
                settings.demo_workspace_slug,
            )
    finally:
        db.close()


def _resolve_workspace(db: Session, selector: str) -> Workspace:
    workspace = db.query(Workspace).filter(Workspace.slug == selector).first()
    if workspace is not None:
        return workspace
    try:
        return db.query(Workspace).filter(Workspace.id == uuid.UUID(selector)).first()
    except ValueError:
        raise SystemExit(f"Workspace not found: {selector}") from None


def _link_existing_workspace(db: Session, email: str, selector: str, role: str) -> None:
    user = get_user_by_email(db, email)
    if user is None:
        raise SystemExit(f"No account exists for {email}")
    workspace = _resolve_workspace(db, selector)
    upsert_membership(db, user, workspace, role)
    print(f"Linked {user.email} to workspace '{workspace.slug}' as {role}.")


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point for creating or linking the first account."""
    parser = argparse.ArgumentParser(
        prog="python -m app.auth.bootstrap",
        description="Create a user account and/or link it to a workspace.",
    )
    parser.add_argument("--email", required=True, help="Account email address")
    parser.add_argument(
        "--password",
        default=None,
        help="Password (omit to be prompted; never pass this on a shared shell)",
    )
    parser.add_argument(
        "--workspace-slug",
        default=None,
        help="Create the workspace when missing and grant a role",
    )
    parser.add_argument("--workspace-name", default=None)
    parser.add_argument(
        "--link-workspace",
        default=None,
        help="Attach the account to an existing workspace (e.g. 'demo')",
    )
    parser.add_argument(
        "--role",
        default=Role.OWNER,
        choices=[role.value for role in Role],
    )
    args = parser.parse_args(argv)

    password = args.password
    if password is None:
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            raise SystemExit("Passwords do not match")

    db = SessionLocal()
    try:
        user = get_user_by_email(db, args.email)
        if user is None:
            try:
                user = create_user(db, args.email, password)
                print(f"Created account {user.email}.")
            except (ValueError, IntegrityError) as exc:
                raise SystemExit(str(exc)) from None
        else:
            print(f"Using existing account {user.email} (password unchanged).")

        if args.link_workspace:
            _link_existing_workspace(db, user.email, args.link_workspace, args.role)

        if args.workspace_slug:
            slug = args.workspace_slug
            name = args.workspace_name or slug
            workspace = _ensure_workspace(db, slug, name)
            upsert_membership(db, user, workspace, args.role)
            print(f"Linked {user.email} to workspace '{workspace.slug}' as {args.role}.")

        ownerless = workspaces_without_owner(db)
        if ownerless:
            print("Workspaces still without an owner: " + ", ".join(ownerless))
        return 0
    finally:
        db.close()


if __name__ == "__main__":  # pragma: no cover - CLI
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())

