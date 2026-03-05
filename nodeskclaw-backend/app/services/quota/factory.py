"""QuotaChecker 工厂 — 根据 edition 返回对应配额检查器。"""

from __future__ import annotations

from functools import lru_cache

from app.services.quota.checker import QuotaChecker


@lru_cache(maxsize=1)
def get_quota_checker() -> QuotaChecker:
    from app.core.feature_gate import feature_gate

    if feature_gate.is_ee:
        try:
            from ee.backend.services.quota.plan_based import PlanBasedQuotaChecker
            return PlanBasedQuotaChecker()
        except ImportError:
            pass

    from app.services.quota.noop import NoopQuotaChecker
    return NoopQuotaChecker()
