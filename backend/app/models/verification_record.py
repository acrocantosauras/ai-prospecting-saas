"""Email verification record model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def new_id():
    return uuid.uuid4()


class VerificationRecord(Base):
    __tablename__ = "verification_records"

    id: Mapped[uuid.UUID] = mapped_column(
        "id", UUID(as_uuid=True), primary_key=True, default=new_id
    )
    prospect_id: Mapped[uuid.UUID] = mapped_column(
        "prospect_id", UUID(as_uuid=True), ForeignKey("prospects.id"), nullable=False, index=True
    )
    email: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(128), nullable=True)
    details: Mapped[str | None] = mapped_column(String(512), nullable=True)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    prospect = relationship("Prospect", backref="verification_records")

    def __repr__(self) -> str:
        return f"<VerificationRecord id={self.id} email={self.email} status={self.status}>"
