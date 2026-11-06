"""Ideal Customer Profile (ICP) model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def new_id():
    return uuid.uuid4()


class ICPProfile(Base):
    __tablename__ = "icp_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        "id", UUID(as_uuid=True), primary_key=True, default=new_id
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        "workspace_id", UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False, index=True
    )
    client_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        "client_profile_id", UUID(as_uuid=True), ForeignKey("client_profiles.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_industries: Mapped[str | None] = mapped_column(Text, nullable=True)
    sub_industries: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_countries: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_regions: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(64), nullable=True)
    employee_count_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    employee_count_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revenue_min: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revenue_max: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preferred_company_types: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_maker_roles: Mapped[str | None] = mapped_column(Text, nullable=True)
    additional_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_prospects: Mapped[int] = mapped_column(default=20, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    workspace = relationship("Workspace", backref="icp_profiles")
    client_profile = relationship("ClientProfile", backref="icp_profiles")

    def __repr__(self) -> str:
        return f"<ICPProfile id={self.id} name={self.name}>"
