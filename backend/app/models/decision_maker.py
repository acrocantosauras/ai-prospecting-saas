"""Decision maker model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def new_id():
    """Return a new UUID."""
    return uuid.uuid4()


class DecisionMaker(Base):
    """Decision-maker model."""

    __tablename__ = "decision_makers"

    id: Mapped[uuid.UUID] = mapped_column(
        "id", UUID(as_uuid=True), primary_key=True, default=new_id
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        "company_id", UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    professional_profile_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    profile_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(512), nullable=True)
    email_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    profile_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    role_source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    evidence_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    synthetic: Mapped[bool] = mapped_column(default=False, nullable=True)
    is_primary: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), default="SOURCE_SUPPORTED", nullable=False)
    last_observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    observation_confidence: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )

    company = relationship("Company", backref="decision_makers")

    def __repr__(self) -> str:
        """Return a debugging representation."""
        return f"<DecisionMaker id={self.id} name={self.full_name} role={self.job_title}>"
