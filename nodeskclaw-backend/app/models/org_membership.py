"""Organization membership (user <-> org many-to-many with role)."""

from enum import Enum

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class OrgRole(str, Enum):
    viewer = "viewer"
    member = "member"
    operator = "operator"
    admin = "admin"


ROLE_LEVEL: dict["OrgRole", int] = {
    OrgRole.viewer: 10,
    OrgRole.member: 20,
    OrgRole.operator: 30,
    OrgRole.admin: 40,
}


class OrgMembership(BaseModel):
    __tablename__ = "org_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "org_id", name="uq_org_membership"),
    )

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default=OrgRole.member, nullable=False)
    job_title: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # relationships
    user = relationship("User", back_populates="memberships")
    organization = relationship("Organization", back_populates="memberships")
