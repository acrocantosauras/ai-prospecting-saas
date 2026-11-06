"""Enrichment record model - stores enrichment data per prospect."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, Float, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def new_id():
    return uuid.uuid4()


class EnrichmentRecord(Base):
    __tablename__ = "enrichment_records"

    id: Mapped[uuid.UUID] = mapped_column(
        "id", UUID(as_uuid=True), primary_key=True, default=new_id
    )
    prospect_id: Mapped[uuid.UUID] = mapped_column(
        "prospect_id", UUID(as_uuid=True), ForeignKey("prospects.id"), nullable=False, index=True
    )
    provider: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_record_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    email: Mapped[str | None] = mapped_column(String(512), nullable=True)
    email_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    instagram_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    other_profiles: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    prospect = relationship("Prospect", backref="enrichment_records")

    def __repr__(self) -> str:
        return f"<EnrichmentRecord id={self.id} email={self.email} status={self.email_status}>"
