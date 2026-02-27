"""Cluster model."""

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class ClusterProvider(str, Enum):
    vke = "vke"
    ack = "ack"
    tke = "tke"
    custom = "custom"


class ClusterStatus(str, Enum):
    connected = "connected"
    disconnected = "disconnected"
    connecting = "connecting"


class Cluster(BaseModel):
    __tablename__ = "clusters"

    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(16), default=ClusterProvider.vke, nullable=False)
    kubeconfig_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    auth_type: Mapped[str] = mapped_column(String(32), default="token", nullable=False)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    api_server_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    k8s_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=ClusterStatus.disconnected, nullable=False)
    health_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_health_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)

    ingress_class: Mapped[str] = mapped_column(String(32), default="nginx", nullable=False)
    proxy_endpoint: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # SaaS：组织专属集群绑定（null = 共享集群）
    org_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True, index=True
    )

    # relationships
    creator = relationship("User", back_populates="clusters", foreign_keys=[created_by])
    owner_org = relationship("Organization", foreign_keys=[org_id])
    instances = relationship("Instance", back_populates="cluster", cascade="save-update, merge")
