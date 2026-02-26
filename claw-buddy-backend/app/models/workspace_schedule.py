"""WorkspaceSchedule — cron-based timed system messages for workspaces."""

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class WorkspaceSchedule(BaseModel):
    __tablename__ = "workspace_schedules"

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    cron_expr: Mapped[str] = mapped_column(String(32), nullable=False)
    message_template: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    workspace = relationship("Workspace")
