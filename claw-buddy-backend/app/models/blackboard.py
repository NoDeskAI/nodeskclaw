"""Blackboard model — shared Markdown document for a workspace."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Blackboard(BaseModel):
    __tablename__ = "blackboards"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)

    auto_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    manual_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    summary_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workspace = relationship("Workspace", back_populates="blackboard")
