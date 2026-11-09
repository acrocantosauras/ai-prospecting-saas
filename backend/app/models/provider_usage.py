"""Provider usage and cost accounting records."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def new_id() -> uuid.UUID:
    """Return a new UUID primary key."""
    return uuid.uuid4()


class ProviderUsage(Base):
    """One metered provider call (successful or failed).

    Every provider invocation performed by the prospecting engine is recorded
    here so cost per company, decision-maker, verified email and batch can be
    computed from measured calls instead of estimates.
    """

    __tablename__ = "provider_usage"

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
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str | None] = mapped_column(String(128), nullable=True)
    units: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        """Return a debugging representation."""
        return (
            f"<ProviderUsage provider={self.provider} capability={self.capability} "
            f"cost={self.cost_usd}>"
        )
