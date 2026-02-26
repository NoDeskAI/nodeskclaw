"""DecisionRecord — captures the full context of significant Agent decisions."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class DecisionRecord(BaseModel):
    __tablename__ = "decision_records"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_instance_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    decision_type: Mapped[str] = mapped_column(String(50), nullable=False)
    context_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    proposal: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    reviewer_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    review_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
