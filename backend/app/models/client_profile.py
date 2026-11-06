"""Client/business profile model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def new_id():
    return uuid.uuid4()


class ClientProfile(Base):
    __tablename__ = "client_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        "id", UUID(as_uuid=True), primary_key=True, default=new_id
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        "workspace_id", UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    products_services: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_proposition: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    problems_solved: Mapped[str | None] = mapped_column(Text, nullable=True)
    usp: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    workspace = relationship("Workspace", backref="client_profiles")

    def __repr__(self) -> str:
        return f"<ClientProfile id={self.id} name={self.name}>"
