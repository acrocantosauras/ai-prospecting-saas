"""Decision maker model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def new_id():
    return uuid.uuid4()


class DecisionMaker(Base):
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

    company = relationship("Company", backref="decision_makers")

    def __repr__(self) -> str:
        return f"<DecisionMaker id={self.id} name={self.full_name} role={self.job_title}>"
