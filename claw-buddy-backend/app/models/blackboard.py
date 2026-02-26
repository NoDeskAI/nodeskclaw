"""Blackboard model — structured task/performance management for a workspace."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON
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

    objectives: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tasks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    member_status: Mapped[list | None] = mapped_column(JSON, nullable=True)
    performance: Mapped[list | None] = mapped_column(JSON, nullable=True)

    workspace = relationship("Workspace", back_populates="blackboard")
