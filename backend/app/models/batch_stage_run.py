"""Per-stage execution status for an engine batch."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def new_id() -> uuid.UUID:
    """Return a new UUID primary key."""
    return uuid.uuid4()


class BatchStageRun(Base):
    """One execution attempt of a pipeline stage.

    Multiple rows per stage are possible because a batch can be resumed or a
    stage can be retried. Consumers read the latest row per stage for status.
    """

    __tablename__ = "batch_stage_runs"

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
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    batch = relationship("ProspectBatch", backref="stage_runs")

    def __repr__(self) -> str:
        """Return a debugging representation."""
        return f"<BatchStageRun batch_id={self.batch_id} stage={self.stage} status={self.status}>"
