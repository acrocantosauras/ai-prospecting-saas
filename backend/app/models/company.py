"""Company model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def new_id():
    return uuid.uuid4()


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(
        "id", UUID(as_uuid=True), primary_key=True, default=new_id
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        "batch_id", UUID(as_uuid=True), ForeignKey("prospect_batches.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(512), nullable=True)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    products_services: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(128), nullable=True)
    employee_count: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revenue: Mapped[str | None] = mapped_column(String(128), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    instagram_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    batch = relationship("ProspectBatch", backref="companies")
    duplicate_of = relationship("Company", remote_side=[id], backref="duplicates")

    def __repr__(self) -> str:
        return f"<Company id={self.id} name={self.name}>"
