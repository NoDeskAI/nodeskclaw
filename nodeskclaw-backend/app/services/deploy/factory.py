"""DeploymentAdapter 工厂 — 根据 edition 返回对应适配器。"""

from __future__ import annotations

from functools import lru_cache

from app.services.deploy.adapter import DeploymentAdapter


@lru_cache(maxsize=1)
def get_deploy_adapter() -> DeploymentAdapter:
    from app.core.feature_gate import feature_gate

    if feature_gate.is_ee:
        try:
            from ee.backend.services.deploy.full_k8s import FullK8sAdapter
            return FullK8sAdapter()
        except ImportError:
            pass

    from app.services.deploy.basic_k8s import BasicK8sAdapter
    return BasicK8sAdapter()
