"""ContextEntry — a piece of shared context within a workspace."""

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class ContextEntryType(str, Enum):
    activity = "activity"
    result = "result"
    knowledge = "knowledge"
    request = "request"
    status = "status"


DEFAULT_TTL = {
    "activity": 1,
    "result": 24,
    "knowledge": 72,
    "request": 12,
    "status": 1,
}


class ContextEntry(BaseModel):
    __tablename__ = "context_entries"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_instance_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entry_type: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    visibility: Mapped[str] = mapped_column(String(16), default="workspace", nullable=False)
    target_instance_ids: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    ttl_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
