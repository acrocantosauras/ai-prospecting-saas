"""Shared test configuration and authentication fixtures.

The suite must never touch the developer database. ``app.config.settings``
caches ``Settings`` (including ``DATABASE_URL``) at import time and
``app.core.database`` binds its engine at import time, so the URL has to be set
before the first test module imports the application. Pytest imports
``conftest.py`` before collection, which makes this the only reliable place:
without it, ``tests/test_auth.py`` (collected first) imports ``app.main`` and
freezes every later module onto ``backend/data/prospecting.db``, where the
engine/hardening fixtures then collide with existing workspace slugs.

Every test session therefore uses a brand-new SQLite file in a temporary
directory. Test modules may still assign ``DATABASE_URL`` before importing the
app when run individually; either way the database is disposable.
"""

import os
import tempfile
import uuid
from pathlib import Path

import pytest

DEFAULT_PASSWORD = "CorrectHorseBattery1"

TEST_DATABASE_DIR = Path(tempfile.mkdtemp(prefix="abc-tests-"))
TEST_DATABASE_URL = f"sqlite:///{(TEST_DATABASE_DIR / 'test.db').as_posix()}"

# Always override rather than setdefault: an inherited DATABASE_URL is exactly
# how a test run would end up writing to a developer or production database.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL


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
