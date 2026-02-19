"""User LLM Config model -- per (user, org, provider) key source selection."""

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class UserLlmConfig(BaseModel):
    __tablename__ = "user_llm_configs"
    __table_args__ = (
        Index(
            "uq_user_llm_configs_user_org_provider",
            "user_id", "org_id", "provider",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    key_source: Mapped[str] = mapped_column(String(16), nullable=False)
    org_llm_key_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("org_llm_keys.id"), nullable=True
    )
