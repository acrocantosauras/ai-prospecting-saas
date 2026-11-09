"""Database initialization helpers."""

from pathlib import Path

# Import all models so they register with Base.metadata
import app.models  # noqa: F401
from app.config import get_settings
from app.core.database import Base
from app.core.database import Engine as engine
from app.core.migrations import apply_additive_migrations


def init() -> None:
    """Create database tables, apply additive migrations and validate auth.

    New authentication tables (``users``, ``workspace_memberships``,
    ``auth_sessions``) are created by ``create_all`` on existing databases too;
    no table is dropped or rewritten, so existing workspace, batch, prospect and
    qualification data is preserved.
    """
    s = get_settings()
    if "sqlite" in s.database_url:
        db_path = Path(s.database_url.replace("sqlite:///", ""))
        db_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    apply_additive_migrations(engine)
    # Imported lazily: app.auth imports app.models, which would otherwise form a
    # cycle while the model package is still initializing.
    from app.auth.bootstrap import run_startup_auth_setup

    run_startup_auth_setup()
