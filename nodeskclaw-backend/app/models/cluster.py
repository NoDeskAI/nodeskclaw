"""Cluster model."""

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class ClusterProvider(str, Enum):
    vke = "vke"
    ack = "ack"
    tke = "tke"
    custom = "custom"
    docker = "docker"


class ClusterStatus(str, Enum):
    connected = "connected"
    disconnected = "disconnected"
    connecting = "connecting"


class Cluster(BaseModel):
    __tablename__ = "clusters"
    __table_args__ = (
        Index(
            "uq_clusters_name_org", "name", "org_id",
            unique=True, postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    compute_provider: Mapped[str] = mapped_column(String(32), default="k8s", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=ClusterStatus.disconnected, nullable=False)
    health_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_health_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    proxy_endpoint: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)

    provider_config: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False,
    )
    credentials_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    org_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True, index=True,
    )

    # relationships
    creator = relationship("User", back_populates="clusters", foreign_keys=[created_by])
    owner_org = relationship("Organization", foreign_keys=[org_id])
    instances = relationship("Instance", back_populates="cluster", cascade="save-update, merge")

    # ── provider_config 读写 helpers ──────────────────────

    def get_provider_value(self, key: str, default=None):
        return self.provider_config.get(key, default) if self.provider_config else default

    def set_provider_value(self, key: str, value) -> None:
        pc = dict(self.provider_config or {})
        pc[key] = value
        self.provider_config = pc

    @property
    def is_k8s(self) -> bool:
        return self.compute_provider == "k8s"

    @property
    def provider(self) -> str:
        return self.get_provider_value("cloud_vendor", "unknown")

    @property
    def ingress_class(self) -> str:
        return self.get_provider_value("ingress_class", "nginx") or "nginx"

    @property
    def auth_type(self) -> str:
        return self.get_provider_value("auth_type", "unknown")

    @property
    def k8s_version(self) -> str | None:
        return self.get_provider_value("k8s_version")

    @property
    def api_server_url(self) -> str | None:
        return self.get_provider_value("api_server_url")

    @property
    def token_expires_at(self) -> datetime | None:
        val = self.get_provider_value("token_expires_at")
        if val:
            return datetime.fromisoformat(val)
        return None
