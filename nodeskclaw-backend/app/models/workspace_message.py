"""WorkspaceMessage — a chat message in a workspace group chat."""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class WorkspaceMessage(BaseModel):
    __tablename__ = "workspace_messages"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    sender_type: Mapped[str] = mapped_column(String(16), nullable=False)
    sender_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sender_name: Mapped[str] = mapped_column(String(128), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(
        String(16), default="chat", nullable=False,
    )
    target_instance_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True,
    )
    depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
