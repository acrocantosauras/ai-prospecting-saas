"""Qualification decision history (including rejections)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def new_id() -> uuid.UUID:
    """Return a new UUID primary key."""
    return uuid.uuid4()


class QualificationRecord(Base):
    """An immutable record of one qualification decision.

    Records are written for qualified companies, rejected companies and
    companies flagged for re-checking, so rejected leads remain auditable
    instead of disappearing from the system.
    """

    __tablename__ = "qualification_records"

    id: Mapped[uuid.UUID] = mapped_column(
        "id", UUID(as_uuid=True), primary_key=True, default=new_id
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        "workspace_id",
        UUID(as_uuid=True),
        ForeignKey("workspaces.id"),
        nullable=True,
        index=True,
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        "batch_id",
        UUID(as_uuid=True),
        ForeignKey("prospect_batches.id"),
        nullable=True,
        index=True,
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        "company_id",
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=True,
        index=True,
    )
    prospect_id: Mapped[uuid.UUID | None] = mapped_column(
        "prospect_id",
        UUID(as_uuid=True),
        ForeignKey("prospects.id"),
        nullable=True,
        index=True,
    )
    scope: Mapped[str] = mapped_column(String(32), default="company", nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    gates_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_requirements_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_urls_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    company = relationship("Company", backref="qualification_records")
    prospect = relationship("Prospect", backref="qualification_records")

    def __repr__(self) -> str:
        """Return a debugging representation."""
        return f"<QualificationRecord company_id={self.company_id} status={self.status}>"
