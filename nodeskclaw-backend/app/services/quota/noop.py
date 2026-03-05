"""NoopQuotaChecker — CE 不做配额限制。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.quota.checker import QuotaChecker


class NoopQuotaChecker(QuotaChecker):

    async def check_deploy_quota(
        self,
        org: Any,
        db: AsyncSession,
        *,
        cpu_request: str = "0",
        mem_request: str = "0",
        storage_size: str = "0",
    ) -> None:
        pass
