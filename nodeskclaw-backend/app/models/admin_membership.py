"""Admin platform membership — controls access to the management console."""

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class AdminMembership(BaseModel):
    __tablename__ = "admin_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "org_id", name="uq_admin_membership"),
    )

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)

    user = relationship("User")
    organization = relationship("Organization")
