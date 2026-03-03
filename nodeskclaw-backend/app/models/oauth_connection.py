"""User OAuth connection (links a user to an external OAuth provider)."""

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class UserOAuthConnection(BaseModel):
    __tablename__ = "user_oauth_connections"
    __table_args__ = (
        Index("uq_oauth_provider_user", "provider", "provider_user_id",
              unique=True, postgresql_where=text("deleted_at IS NULL")),
    )

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    provider_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_tenant_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    user = relationship("User", back_populates="oauth_connections")
