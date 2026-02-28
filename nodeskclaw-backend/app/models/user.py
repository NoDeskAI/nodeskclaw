"""User model."""

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class UserRole(str, Enum):
    admin = "admin"
    user = "user"


class User(BaseModel):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str | None] = mapped_column(String(256), unique=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    role: Mapped[str] = mapped_column(String(16), default=UserRole.user, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # SaaS 多租户字段
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    current_org_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True
    )

    # relationships
    clusters = relationship("Cluster", back_populates="creator", foreign_keys="Cluster.created_by")
    instances = relationship("Instance", back_populates="creator", foreign_keys="Instance.created_by")
    current_org = relationship("Organization", foreign_keys=[current_org_id])
    memberships = relationship("OrgMembership", back_populates="user", cascade="all, delete-orphan")
    oauth_connections = relationship("UserOAuthConnection", back_populates="user", cascade="all, delete-orphan")
