"""Blackboard model — structured workspace context (v2: objectives, tasks, status, performance)."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Blackboard(BaseModel):
    __tablename__ = "blackboards"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    auto_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    manual_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    summary_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    objectives: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    tasks: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    member_status: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    performance: Mapped[str] = mapped_column(Text, default="[]", nullable=False)

    workspace = relationship("Workspace", back_populates="blackboard")
