"""SQLAlchemy base model with common fields."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    """Mixin that adds created_at / updated_at columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class BaseModel(Base, TimestampMixin):
    """Abstract base with UUID pk + timestamps + soft delete."""

    __abstract__ = True

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None, index=True
    )

    def soft_delete(self) -> None:
        """标记为已删除（逻辑删除）。"""
        self.deleted_at = func.now()


def not_deleted(model: type[BaseModel]):
    """返回排除已删除记录的 where 条件，用于查询过滤。

    用法: select(Instance).where(not_deleted(Instance))
    """
    return model.deleted_at.is_(None)
