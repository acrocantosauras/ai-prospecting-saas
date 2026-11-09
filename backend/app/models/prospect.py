"""Prospect model - the primary prospecting result entity."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, Float, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def new_id():
    return uuid.uuid4()


class Prospect(Base):
    __tablename__ = "prospects"

    id: Mapped[uuid.UUID] = mapped_column(
        "id", UUID(as_uuid=True), primary_key=True, default=new_id
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        "batch_id", UUID(as_uuid=True), ForeignKey("prospect_batches.id"), nullable=False, index=True
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        "company_id", UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True, index=True
    )
    decision_maker_id: Mapped[uuid.UUID | None] = mapped_column(
        "decision_maker_id", UUID(as_uuid=True), ForeignKey("decision_makers.id"), nullable=True, index=True
    )
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    email: Mapped[str | None] = mapped_column(String(512), nullable=True)
    role: Mapped[str | None] = mapped_column(String(256), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    instagram_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    company_website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(256), nullable=True)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    research_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_problem: Mapped[str | None] = mapped_column(Text, nullable=True)
    problem_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    solution_match: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualification_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    qualification_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    research_confidence: Mapped[str | None] = mapped_column(String(64), nullable=True)
    missing_information: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_links: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualification_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    qualification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_urls: Mapped[str | None] = mapped_column(Text, nullable=True)
    synthetic: Mapped[bool] = mapped_column(default=False, nullable=True)
    is_ready_for_outreach: Mapped[bool] = mapped_column(default=False, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    batch = relationship("ProspectBatch", back_populates="prospects")
    company = relationship("Company", backref="prospects")
    decision_maker = relationship("DecisionMaker", backref="prospects")

    def __repr__(self) -> str:
        return f"<Prospect id={self.id} company={self.company_name} score={self.qualification_score}>"
