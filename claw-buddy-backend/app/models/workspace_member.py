"""WorkspaceMember — RBAC for workspace access (owner/editor/viewer)."""

from enum import Enum

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class WorkspaceRole(str, Enum):
    owner = "owner"
    editor = "editor"
    viewer = "viewer"


class WorkspaceMember(BaseModel):
    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), default=WorkspaceRole.editor, nullable=False)

    # relationships
    workspace = relationship("Workspace", back_populates="members")
    user = relationship("User")
