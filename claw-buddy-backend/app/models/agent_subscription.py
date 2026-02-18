"""AgentSubscription — controls what context an Agent listens to."""

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class AgentSubscription(BaseModel):
    __tablename__ = "agent_subscriptions"
    __table_args__ = (
        UniqueConstraint("instance_id", "workspace_id", name="uq_subscription"),
    )

    instance_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("instances.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    subscribe_tags: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    subscribe_types: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    subscribe_agents: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    max_entries: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
