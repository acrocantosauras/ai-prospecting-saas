"""Regression guard: the test suite must never write to the developer database.

``tests/conftest.py`` pins the suite to a temporary SQLite file. This test
proves the isolation holds in practice: a row written during the run lands in
the test database and never in ``backend/data/prospecting.db`` or
``data/prospecting.db``.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from sqlalchemy.engine import make_url

from app.config import get_settings
from app.core.database import Base, Engine, SessionLocal
from app.models import Workspace

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEVELOPER_DATABASES = (
    BACKEND_DIR / "data" / "prospecting.db",
    BACKEND_DIR.parent / "data" / "prospecting.db",
)


def _configured_database_path() -> Path:
    """Return the resolved SQLite file backing the test session."""
    url = make_url(get_settings().database_url)
    assert url.drivername.startswith("sqlite"), (
        f"the test suite expects an isolated SQLite database, got {url.drivername!r}"
    )
    assert url.database, "the test database must be a file, not in-memory SQLite"
    return Path(url.database).resolve()


def _sentinel_count(path: Path, slug: str) -> int | None:
    """Return the sentinel row count, or None when that database is unreadable."""
    if not path.exists():
        return None
    try:
        connection = sqlite3.connect(
            f"file:{path.as_posix()}?mode=ro", uri=True, timeout=1
        )
    except sqlite3.Error:
        return None
    try:
        row = connection.execute(
            "SELECT COUNT(*) FROM workspaces WHERE slug = ?", (slug,)
        ).fetchone()
        return int(row[0]) if row is not None else None
    except sqlite3.Error:
        return None
    finally:
        connection.close()


def test_suite_database_is_temporary_and_not_a_developer_database():
    configured = _configured_database_path()
    for developer_database in DEVELOPER_DATABASES:
        assert configured != developer_database.resolve(), (
            "the test suite is bound to a developer database"
        )
    assert configured != (BACKEND_DIR / "prospecting.db").resolve()


def test_test_writes_never_reach_the_developer_database():
    slug = f"isolation-guard-{uuid.uuid4().hex[:12]}"
    before = {path: _sentinel_count(path, slug) for path in DEVELOPER_DATABASES}

    # The guard must work when this file runs alone, before any TestClient has
    # triggered the application's startup schema creation.
    Base.metadata.create_all(bind=Engine)
    db = SessionLocal()
    try:
        db.add(Workspace(slug=slug, name="Isolation Guard"))
        db.commit()
        assert db.query(Workspace).filter(Workspace.slug == slug).count() == 1
    finally:
        db.close()

    after = {path: _sentinel_count(path, slug) for path in DEVELOPER_DATABASES}
    assert after == before
    assert all(count in (None, 0) for count in after.values()), (
        "a test write reached a developer database"
    )
