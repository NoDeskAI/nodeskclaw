"""Plan (subscription tier) model."""

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class Plan(BaseModel):
    __tablename__ = "plans"

    name: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)  # free / pro / enterprise
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)       # 免费版 / 专业版 / 企业版
    max_instances: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_cpu_per_instance: Mapped[str] = mapped_column(String(16), default="2000m", nullable=False)
    max_mem_per_instance: Mapped[str] = mapped_column(String(16), default="4Gi", nullable=False)
    allowed_specs: Mapped[str] = mapped_column(Text, default='["small"]', nullable=False)  # JSON array
    dedicated_cluster: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    price_monthly: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 分，0 = 免费
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
