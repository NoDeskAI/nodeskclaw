"""Instance (OpenClaw deployment) model."""

from enum import Enum

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class InstanceStatus(str, Enum):
    creating = "creating"
    pending = "pending"
    deploying = "deploying"
    running = "running"
    updating = "updating"
    failed = "failed"
    deleting = "deleting"


class ServiceType(str, Enum):
    cluster_ip = "ClusterIP"
    node_port = "NodePort"
    load_balancer = "LoadBalancer"


class Instance(BaseModel):
    __tablename__ = "instances"
    __table_args__ = (
        Index(
            "uq_instances_slug_org_active",
            "slug", "org_id",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    cluster_id: Mapped[str] = mapped_column(String(36), ForeignKey("clusters.id"), nullable=False)
    namespace: Mapped[str] = mapped_column(String(128), nullable=False)
    image_version: Mapped[str] = mapped_column(String(64), nullable=False)
    replicas: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Resource requests/limits
    cpu_request: Mapped[str] = mapped_column(String(16), default="500m", nullable=False)
    cpu_limit: Mapped[str] = mapped_column(String(16), default="2000m", nullable=False)
    mem_request: Mapped[str] = mapped_column(String(16), default="512Mi", nullable=False)
    mem_limit: Mapped[str] = mapped_column(String(16), default="2Gi", nullable=False)

    # Network
    service_type: Mapped[str] = mapped_column(String(16), default=ServiceType.cluster_ip, nullable=False)
    ingress_domain: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # LLM proxy token (same value as OPENCLAW_GATEWAY_TOKEN in env_vars)
    proxy_token: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )

    # Config
    env_vars: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string

    # Namespace quota
    quota_cpu: Mapped[str] = mapped_column(String(16), default="4", nullable=False)
    quota_mem: Mapped[str] = mapped_column(String(16), default="8Gi", nullable=False)
    quota_max_pods: Mapped[int] = mapped_column(Integer, default=20, nullable=False)

    # Storage
    storage_class: Mapped[str] = mapped_column(String(64), default="nas-subpath", nullable=False)
    storage_size: Mapped[str] = mapped_column(String(16), default="80Gi", nullable=False)

    # Advanced config (JSON)
    advanced_config: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Pending config (JSON) -- 两步操作模式: 保存到 DB 但尚未 apply 到 K8s
    pending_config: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Runtime
    available_replicas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Status
    status: Mapped[str] = mapped_column(String(16), default=InstanceStatus.creating, nullable=False)
    current_revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # FK
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    org_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True, index=True
    )

    # Workspace / Agent hex position (nullable for backward compat)
    workspace_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True, index=True
    )
    hex_position_q: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hex_position_r: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    agent_display_name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # relationships
    cluster = relationship("Cluster", back_populates="instances")
    creator = relationship("User", back_populates="instances", foreign_keys=[created_by])
    organization = relationship("Organization", back_populates="instances")
    deploy_records = relationship("DeployRecord", back_populates="instance", cascade="save-update, merge")
    workspace = relationship("Workspace", foreign_keys=[workspace_id])
