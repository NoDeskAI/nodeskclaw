"""User personal LLM Key model -- one key per provider per user."""

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class UserLlmKey(BaseModel):
    __tablename__ = "user_llm_keys"
    __table_args__ = (
        Index(
            "uq_user_llm_keys_user_provider",
            "user_id", "provider",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    api_key: Mapped[str] = mapped_column(Text, nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
