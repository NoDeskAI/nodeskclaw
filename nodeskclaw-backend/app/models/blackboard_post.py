"""BlackboardPost — BBS-style discussion post within a workspace blackboard."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class BlackboardPost(BaseModel):
    __tablename__ = "blackboard_posts"
    __table_args__ = (
        Index(
            "ix_blackboard_posts_ws_active",
            "workspace_id",
            "is_pinned",
            "last_reply_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    author_type: Mapped[str] = mapped_column(String(10), nullable=False)
    author_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    author_name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reply_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_reply_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    workspace = relationship("Workspace", foreign_keys=[workspace_id])
    replies = relationship(
        "BlackboardReply",
        back_populates="post",
        order_by="BlackboardReply.created_at",
        lazy="selectin",
    )
