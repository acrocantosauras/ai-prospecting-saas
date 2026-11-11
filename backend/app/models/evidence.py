"""Evidence model - source links and citations for prospecting data."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def new_id():
    """Return a new UUID."""
    return uuid.uuid4()


class Evidence(Base):
    """Stored evidence and source reference."""

    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(
        "id", UUID(as_uuid=True), primary_key=True, default=new_id
    )
    prospect_id: Mapped[uuid.UUID | None] = mapped_column(
        "prospect_id", UUID(as_uuid=True), ForeignKey("prospects.id"), nullable=True, index=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        "company_id", UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True, index=True
    )
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    retrieved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    publication_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verification_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_accessible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    prospect = relationship("Prospect", backref="evidence_items")
    company = relationship("Company", backref="evidence_items")

    def __repr__(self) -> str:
        """Return a debugging representation."""
        return f"<Evidence id={self.id} url={self.url}>"
