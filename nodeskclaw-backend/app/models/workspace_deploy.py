"""WorkspaceDeploy — batch deploy from workspace template (internal)."""

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class WorkspaceDeploy(BaseModel):
    __tablename__ = "workspace_deploys"

    workspace_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True
    )
    template_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspace_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    total_agents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_agents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_agents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_detail: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    config_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
