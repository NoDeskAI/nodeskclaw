"""Workspace model — a collaborative space containing multiple Agents."""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Workspace(BaseModel):
    __tablename__ = "workspaces"

    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    color: Mapped[str] = mapped_column(String(16), default="#a78bfa", nullable=False)
    icon: Mapped[str] = mapped_column(String(32), default="bot", nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    cluster_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("clusters.id"), nullable=True, index=True,
    )
    decoration_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_template_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # relationships
    organization = relationship("Organization", foreign_keys=[org_id])
    cluster = relationship("Cluster", foreign_keys=[cluster_id])
    creator = relationship("User", foreign_keys=[created_by])
    blackboard = relationship("Blackboard", back_populates="workspace", uselist=False, cascade="all, delete-orphan")
    members = relationship("WorkspaceMember", back_populates="workspace", cascade="all, delete-orphan")
