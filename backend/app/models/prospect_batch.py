"""Prospect batch model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Integer, DateTime, Float, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, SessionLocal


def new_id():
    return uuid.uuid4()


class ProspectBatch(Base):
    __tablename__ = "prospect_batches"

    id: Mapped[uuid.UUID] = mapped_column(
        "id", UUID(as_uuid=True), primary_key=True, default=new_id
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        "workspace_id", UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False, index=True
    )
    icp_profile_id: Mapped[uuid.UUID] = mapped_column(
        "icp_profile_id", UUID(as_uuid=True), ForeignKey("icp_profiles.id"), nullable=False, index=True
    )
    client_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        "client_profile_id", UUID(as_uuid=True), ForeignKey("client_profiles.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    current_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    total_discovered: Mapped[int] = mapped_column(default=0, nullable=False)
    total_researched: Mapped[int] = mapped_column(default=0, nullable=False)
    total_enriched: Mapped[int] = mapped_column(default=0, nullable=False)
    total_qualified: Mapped[int] = mapped_column(default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_mode: Mapped[str] = mapped_column(String(32), default="demo", nullable=False)
    requested_prospect_count: Mapped[int] = mapped_column(default=20, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    workspace = relationship("Workspace", backref="prospect_batches")
    icp_profile = relationship("ICPProfile", backref="prospect_batches")
    client_profile = relationship("ClientProfile", backref="prospect_batches")
    prospects = relationship("Prospect", back_populates="batch", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ProspectBatch id={self.id} name={self.name} status={self.status}>"
