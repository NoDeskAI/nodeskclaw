"""Admin platform membership — controls access to the management console."""

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class AdminMembership(BaseModel):
    __tablename__ = "admin_memberships"
    __table_args__ = (
        Index("uq_admin_membership", "user_id", "org_id",
              unique=True, postgresql_where=text("deleted_at IS NULL")),
    )

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)

    user = relationship("User")
    organization = relationship("Organization")
