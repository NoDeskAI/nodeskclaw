"""Deploy record model."""

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class DeployAction(str, Enum):
    deploy = "deploy"
    create = "create"
    upgrade = "upgrade"
    rollback = "rollback"
    scale = "scale"
    restart = "restart"
    delete = "delete"


class DeployStatus(str, Enum):
    pending = "pending"
    running = "running"
    in_progress = "in_progress"
    success = "success"
    failed = "failed"


class DeployRecord(BaseModel):
    __tablename__ = "deploy_records"

    instance_id: Mapped[str] = mapped_column(String(36), ForeignKey("instances.id"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    image_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    replicas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    config_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    status: Mapped[str] = mapped_column(String(16), default=DeployStatus.in_progress, nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # relationships
    instance = relationship("Instance", back_populates="deploy_records")
    user = relationship("User", foreign_keys=[triggered_by])
