"""BasicK8sAdapter — CE 基础单集群 K8s 部署适配器。

不做组织配额检查、不做专属集群覆盖、不创建跨集群代理。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.deploy.adapter import DeploymentAdapter

logger = logging.getLogger(__name__)


class BasicK8sAdapter(DeploymentAdapter):

    async def resolve_cluster(
        self,
        cluster_id: str,
        db: AsyncSession,
        org_id: str | None,
        *,
        cpu_limit: str = "0",
        mem_limit: str = "0",
        storage_size: str = "0",
    ) -> tuple[str, Any]:
        return cluster_id, None

    def build_namespace(self, slug: str, org: Any) -> str:
        return f"nodeskclaw-default-{slug}"

    def get_namespace_labels(self, org_id: str | None) -> dict[str, str] | None:
        return None

    async def setup_proxy(self, ctx: Any, ingress_host: str) -> None:
        pass

    async def cleanup_proxy(self, ctx: Any) -> None:
        pass

    def get_network_policy_org_id(self, org_id: str | None) -> str | None:
        return None

    def get_tls_secret(
        self, tls_secret_name: str | None, has_proxy: bool,
    ) -> str | None:
        return tls_secret_name
