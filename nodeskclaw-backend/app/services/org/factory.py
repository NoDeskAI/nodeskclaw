"""OrgProvider 工厂 — 根据 edition 返回对应组织模式。"""

from __future__ import annotations

from functools import lru_cache

from app.services.org.provider import OrgProvider


@lru_cache(maxsize=1)
def get_org_provider() -> OrgProvider:
    from app.core.feature_gate import feature_gate

    if feature_gate.is_ee:
        try:
            from ee.backend.services.org.multi_org import MultiOrgProvider
            return MultiOrgProvider()
        except ImportError:
            pass

    from app.services.org.single_org import SingleOrgProvider
    return SingleOrgProvider()
