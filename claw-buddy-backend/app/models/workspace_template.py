"""WorkspaceTemplate — reusable workspace topology + config snapshots."""

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class WorkspaceTemplate(BaseModel):
    __tablename__ = "workspace_templates"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    org_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    topology_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    blackboard_template: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    gene_assignments: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    preview_image: Mapped[str | None] = mapped_column(String(500), nullable=True)
