"""WorkspaceMember — RBAC for workspace access (owner/editor/viewer) + Human Hex."""

from enum import Enum

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSON

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

    hex_q: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hex_r: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    channel_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    display_color: Mapped[str | None] = mapped_column(String(20), nullable=True, default="#f59e0b")

    # relationships
    workspace = relationship("Workspace", back_populates="members")
    user = relationship("User")
