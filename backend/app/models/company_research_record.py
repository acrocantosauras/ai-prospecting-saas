"""Stored company research output with its supporting evidence."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def new_id() -> uuid.UUID:
    """Return a new UUID primary key."""
    return uuid.uuid4()


class CompanyResearchRecord(Base):
    """A single research snapshot for a company within a batch.

    ``evidence_json`` holds the normalized source references returned by the
    research provider. ``confidence`` is 0..1 and is derived from how much
    evidence was actually retrieved, never from model self-assessment alone.
    """

    __tablename__ = "company_research_records"

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
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    what_it_does: Mapped[str | None] = mapped_column(Text, nullable=True)
    what_it_sells: Mapped[str | None] = mapped_column(Text, nullable=True)
    who_it_serves: Mapped[str | None] = mapped_column(Text, nullable=True)
    positioning: Mapped[str | None] = mapped_column(Text, nullable=True)
    public_developments: Mapped[str | None] = mapped_column(Text, nullable=True)
    observable_signals_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_information_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    research_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_attempted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_successful_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    research_status: Mapped[str] = mapped_column(String(32), default="success", nullable=False)
    research_version: Mapped[int] = mapped_column(default=1, nullable=False)
    content_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_maker_extracted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    company = relationship("Company", backref="research_records")

    def __repr__(self) -> str:
        """Return a debugging representation."""
        return f"<CompanyResearchRecord company_id={self.company_id} provider={self.provider}>"
