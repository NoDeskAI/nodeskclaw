"""AgentShareConfig — controls how an Agent shares context within a workspace."""

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class AgentShareConfig(BaseModel):
    __tablename__ = "agent_share_configs"
    __table_args__ = (
        UniqueConstraint("instance_id", "workspace_id", name="uq_share_config"),
    )

    instance_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("instances.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    share_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    share_frequency: Mapped[str] = mapped_column(String(16), default="proactive", nullable=False)
    share_types: Mapped[list] = mapped_column(
        JSONB, default=lambda: ["result", "knowledge", "request", "activity"], nullable=False
    )
    custom_instruction: Mapped[str] = mapped_column(Text, default="", nullable=False)
    publish_tags: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
