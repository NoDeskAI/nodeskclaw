"""Workspace template model — saves reusable workspace configurations."""

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class WorkspaceTemplate(BaseModel):
    __tablename__ = "workspace_templates"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_preset: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    topology_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    blackboard_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    gene_assignments: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
