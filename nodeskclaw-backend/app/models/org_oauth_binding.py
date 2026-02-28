"""Organization OAuth binding (links an org to an external OAuth tenant)."""

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class OrgOAuthBinding(BaseModel):
    __tablename__ = "org_oauth_bindings"
    __table_args__ = (
        UniqueConstraint("provider", "provider_tenant_id", name="uq_oauth_provider_tenant"),
    )

    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    provider_tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)

    organization = relationship("Organization", back_populates="oauth_bindings")
