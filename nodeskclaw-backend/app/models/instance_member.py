"""Instance-level member (user <-> instance many-to-many with role)."""

from enum import Enum

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class InstanceRole(str, Enum):
    admin = "admin"
    editor = "editor"
    user = "user"
    viewer = "viewer"


INSTANCE_ROLE_LEVEL: dict[str, int] = {
    "admin": 40,
    "editor": 30,
    "user": 20,
    "viewer": 10,
}


class InstanceMember(BaseModel):
    __tablename__ = "instance_members"
    __table_args__ = (
        UniqueConstraint(
            "instance_id", "user_id",
            name="uq_instance_member_active",
        ),
        Index("ix_instance_member_instance", "instance_id"),
        Index("ix_instance_member_user", "user_id"),
    )

    instance_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("instances.id"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(16), default=InstanceRole.viewer, nullable=False
    )

    instance = relationship("Instance", back_populates="members")
    member_user = relationship("User")
