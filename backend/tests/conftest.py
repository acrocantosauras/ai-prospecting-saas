"""Shared authentication fixtures for the API test suite.

Fixtures import the application lazily: each test module configures its
``DATABASE_URL`` before importing ``app``, so importing ``app`` at conftest
import time would freeze the wrong settings.
"""

import uuid

import pytest

DEFAULT_PASSWORD = "CorrectHorseBattery1"


def _unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}@example.test"


@pytest.fixture(scope="module")
def auth_factory():
    """Return a factory that creates an account, membership and signed-in client.

    The client is logged in through the real login endpoint, so cookies and the
    CSRF header behave exactly as they do for the browser.
    """

    def _authenticate(
        client,
        workspace_slug: str,
        role: str = "owner",
        email: str | None = None,
        password: str = DEFAULT_PASSWORD,
        workspace_name: str | None = None,
    ) -> dict[str, str]:
        from app.auth.service import create_user, upsert_membership
        from app.core.database import SessionLocal
        from app.models import User, Workspace

        db = SessionLocal()
        try:
            workspace = (
                db.query(Workspace).filter(Workspace.slug == workspace_slug).first()
            )
            if workspace is None:
                workspace = Workspace(
                    slug=workspace_slug, name=workspace_name or workspace_slug
                )
                db.add(workspace)
                db.commit()
                db.refresh(workspace)
            resolved_email = email or _unique_email(workspace_slug)
            user = (
                db.query(User).filter(User.email == resolved_email.lower()).first()
            )
            if user is None:
                user = create_user(db, resolved_email, password)
            upsert_membership(db, user, workspace, role)
            user_id = str(user.id)
            account_email = user.email
        finally:
            db.close()

        response = client.post(
            "/api/v1/auth/login",
            json={"email": account_email, "password": password},
        )
        assert response.status_code == 200, response.text
        csrf_token = response.json()["csrf_token"]
        client.headers["X-CSRF-Token"] = csrf_token
        return {
            "email": account_email,
            "password": password,
            "user_id": user_id,
            "workspace_slug": workspace_slug,
            "csrf_token": csrf_token,
        }

    return _authenticate
