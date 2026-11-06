"""Core database setup with SQLAlchemy."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings().database_url,
            connect_args={"check_same_thread": False} if "sqlite" in settings().database_url else {},
        )
    return _engine


def get_engine():
    return _get_engine()


Engine = _get_engine()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=Engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_settings():
    return settings()
