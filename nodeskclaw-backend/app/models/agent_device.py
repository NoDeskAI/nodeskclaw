"""Agent Device models — governable Agent Devices placed on workspace topology."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class AgentDevicePresetEnablement(BaseModel):
    __tablename__ = "agent_device_preset_enablements"
    __table_args__ = (
        Index(
            "uq_agent_device_preset_enablement",
            "workspace_id",
            "preset_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    preset_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    workspace = relationship("Workspace")


class AgentDeviceInstance(BaseModel):
    __tablename__ = "agent_device_instances"
    __table_args__ = (
        Index(
            "uq_agent_device_instance_hex",
            "workspace_id",
            "hex_q",
            "hex_r",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    preset_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    provider_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    hex_q: Mapped[int] = mapped_column(Integer, nullable=False)
    hex_r: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="available", server_default="available", nullable=False)
    status_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    workspace = relationship("Workspace")


class AgentDeviceGrant(BaseModel):
    __tablename__ = "agent_device_grants"
    __table_args__ = (
        Index("ix_agent_device_grants_subject", "workspace_id", "subject_type", "subject_id"),
        Index("ix_agent_device_grants_parent", "parent_grant_id"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_device_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    scopes: Mapped[list] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
        nullable=False,
    )
    can_delegate: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    parent_grant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_device_grants.id"), nullable=True
    )
    granted_by_type: Mapped[str] = mapped_column(String(16), nullable=False)
    granted_by_id: Mapped[str] = mapped_column(String(36), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    device = relationship("AgentDeviceInstance")


class AgentDeviceLease(BaseModel):
    __tablename__ = "agent_device_leases"
    __table_args__ = (
        Index(
            "uq_agent_device_active_lease",
            "device_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND status = 'active'"),
        ),
        Index("ix_agent_device_leases_holder", "workspace_id", "holder_agent_id"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_device_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    holder_agent_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    grant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_device_grants.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    renewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    device = relationship("AgentDeviceInstance")
    grant = relationship("AgentDeviceGrant")


class AgentDeviceGeneBinding(BaseModel):
    __tablename__ = "agent_device_gene_bindings"
    __table_args__ = (
        Index(
            "uq_agent_device_gene_binding",
            "workspace_id",
            "device_id",
            "instance_id",
            "gene_slug",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_device_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instance_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    gene_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("genes.id"), nullable=True)
    gene_slug: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    instance_gene_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("instance_genes.id"), nullable=True)
    was_preexisting: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    sync_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    device = relationship("AgentDeviceInstance")
