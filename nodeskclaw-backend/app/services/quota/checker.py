"""QuotaChecker 抽象接口 — CE/EE 配额策略差异。

CE (NoopQuotaChecker):
  不做配额检查，部署请求直接通过。

EE (PlanBasedQuotaChecker):
  基于组织套餐（Plan）的配额检查，
  检查实例数 + CPU + 内存 + 存储是否超限。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


class QuotaChecker(ABC):

    @abstractmethod
    async def check_deploy_quota(
        self,
        org: Any,
        db: AsyncSession,
        *,
        cpu_request: str = "0",
        mem_request: str = "0",
        storage_size: str = "0",
    ) -> None:
        """部署前配额检查，超限则抛 BadRequestError。

        CE: 直接 pass
        EE: 基于组织 Plan 的配额检查
        """
