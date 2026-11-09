"""Workspace membership model.

The membership row - not the presence of a workspace slug - is what authorizes
a user for a tenant. Roles are ``owner``, ``admin``, ``member`` and ``viewer``;
the permission mapping lives in :mod:`app.auth.permissions`.

Revocation deactivates the row instead of deleting it so that the history of
who had access is retained.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def new_id():
    """Return a new UUID primary key."""
    return uuid.uuid4()


class WorkspaceMembership(Base):
    """A user's role-based access to one workspace."""

    __tablename__ = "workspace_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "workspace_id", name="uq_membership_user_workspace"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        "id", UUID(as_uuid=True), primary_key=True, default=new_id
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        "user_id",
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        "workspace_id",
        UUID(as_uuid=True),
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(16), default="viewer", nullable=False, server_default="viewer"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default="1"
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

    user = relationship("User", backref="memberships")
    workspace = relationship("Workspace", backref="memberships")

    def __repr__(self) -> str:
        """Return a compact debug representation."""
        return (
            f"<WorkspaceMembership user={self.user_id} workspace={self.workspace_id} "
            f"role={self.role} active={self.is_active}>"
        )
