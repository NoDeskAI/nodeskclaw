"""WorkspaceMember — fine-grained permission model for workspace access."""

from enum import Enum

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSON

from app.models.base import BaseModel


WORKSPACE_PERMISSIONS: list[str] = [
    "manage_settings",
    "manage_agents",
    "manage_members",
    "edit_blackboard",
    "send_chat",
    "edit_topology",
    "delete_workspace",
]

PERMISSION_PRESETS: dict[str, list[str]] = {
    "collaborator": ["manage_agents", "edit_blackboard", "send_chat", "edit_topology"],
    "observer": ["send_chat"],
}


class WorkspaceRole(str, Enum):
    owner = "owner"
    editor = "editor"
    viewer = "viewer"


class WorkspaceMember(BaseModel):
    __tablename__ = "workspace_members"
    __table_args__ = (
        Index("uq_workspace_member", "workspace_id", "user_id",
              unique=True, postgresql_where=text("deleted_at IS NULL")),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), default=WorkspaceRole.editor, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    permissions: Mapped[list] = mapped_column(JSON, default=list, server_default="[]", nullable=False)

    hex_q: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hex_r: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    channel_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    display_color: Mapped[str | None] = mapped_column(String(20), nullable=True, default="#f59e0b")

    # relationships
    workspace = relationship("Workspace", back_populates="members")
    user = relationship("User")
