"""Database initialization helpers."""

from pathlib import Path

from app.core.database import Engine as engine, Base
from app.config import get_settings
# Import all models so they register with Base.metadata
import app.models  # noqa: F401


def init() -> None:
    """Create database tables and ensure directory exists."""
    s = get_settings()
    if "sqlite" in s.database_url:
        db_path = Path(s.database_url.replace("sqlite:///", ""))
        db_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
