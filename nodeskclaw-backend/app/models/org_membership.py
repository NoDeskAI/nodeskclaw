"""Organization membership (user <-> org many-to-many with role)."""

from enum import Enum

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class OrgRole(str, Enum):
    member = "member"
    operator = "operator"
    admin = "admin"


ADMIN_ROLE_LEVEL: dict[str, int] = {
    "member": 10,
    "operator": 20,
    "admin": 30,
}


class OrgMembership(BaseModel):
    __tablename__ = "org_memberships"
    __table_args__ = (
        Index("uq_org_membership", "user_id", "org_id",
              unique=True, postgresql_where=text("deleted_at IS NULL")),
    )

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default=OrgRole.member, nullable=False)
    job_title: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # relationships
    user = relationship("User", back_populates="memberships")
    organization = relationship("Organization", back_populates="memberships")
