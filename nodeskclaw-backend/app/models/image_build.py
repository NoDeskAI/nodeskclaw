"""Kubernetes image build tasks for runtime images."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class ImageBuild(BaseModel):
    __tablename__ = "image_builds"
    __table_args__ = (
        Index(
            "uq_image_builds_active_reference",
            "image_repository",
            "image_tag",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND status IN ('pending', 'running')"),
        ),
        Index(
            "ix_image_builds_org_created_at",
            "org_id",
            "created_at",
        ),
    )

    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    cluster_id: Mapped[str] = mapped_column(String(36), ForeignKey("clusters.id"), nullable=False, index=True)
    requested_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    engine_version_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("engine_versions.id"), nullable=True)
    runtime: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    image_repository: Mapped[str] = mapped_column(String(512), nullable=False)
    image_tag: Mapped[str] = mapped_column(String(128), nullable=False)
    source_repository: Mapped[str] = mapped_column(String(512), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    namespace: Mapped[str] = mapped_column(String(63), nullable=False)
    job_name: Mapped[str] = mapped_column(String(63), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    log_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    release_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization = relationship("Organization", foreign_keys=[org_id])
    cluster = relationship("Cluster", foreign_keys=[cluster_id])
    requester = relationship("User", foreign_keys=[requested_by])
    engine_version = relationship("EngineVersion", foreign_keys=[engine_version_id])

    @property
    def image_reference(self) -> str:
        return f"{self.image_repository}:{self.image_tag}"
