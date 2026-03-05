"""DeploymentAdapter 抽象接口 — CE/EE 部署行为差异点。

deploy_service.py 在关键分叉点调用 adapter 方法，
CE/EE 通过不同实现提供不同行为。

CE (BasicK8sAdapter):
  - 单集群，不做组织配额检查
  - namespace 不含 org_slug
  - 不创建跨集群网关代理
  - NetworkPolicy 不传 org_id

EE (FullK8sAdapter):
  - 组织配额检查 + 专属集群覆盖
  - namespace 含 org_slug（多租户隔离）
  - 跨集群网关代理（ExternalName Service + Proxy Ingress）
  - NetworkPolicy 含 org_id（组织级隔离）
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


class DeploymentAdapter(ABC):

    @abstractmethod
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
        """解析最终部署集群。

        Returns:
            (effective_cluster_id, org_or_none)
            CE: 直接返回 (cluster_id, None)
            EE: 检查组织配额 + 专属集群覆盖
        """

    @abstractmethod
    def build_namespace(self, slug: str, org: Any) -> str:
        """构建 namespace 名称。

        CE: nodeskclaw-default-{slug}
        EE: nodeskclaw-{org_slug}-{slug}
        """

    @abstractmethod
    def get_namespace_labels(self, org_id: str | None) -> dict[str, str] | None:
        """namespace 额外标签。

        CE: None
        EE: {"nodeskclaw.io/org-id": org_id}
        """

    @abstractmethod
    async def setup_proxy(
        self,
        ctx: Any,
        ingress_host: str,
    ) -> None:
        """Ingress 创建后的跨集群代理设置。

        CE: no-op
        EE: 在网关集群创建 ExternalName Service + Proxy Ingress
        """

    @abstractmethod
    async def cleanup_proxy(self, ctx: Any) -> None:
        """清理跨集群代理资源。

        CE: no-op
        EE: 删除网关集群上的 Proxy Ingress
        """

    @abstractmethod
    def get_network_policy_org_id(self, org_id: str | None) -> str | None:
        """NetworkPolicy 的 org_id 参数。

        CE: None（不做组织级隔离）
        EE: org_id
        """

    @abstractmethod
    def get_tls_secret(
        self, tls_secret_name: str | None, has_proxy: bool,
    ) -> str | None:
        """Ingress TLS secret 名称。

        CE: 直接返回 tls_secret_name
        EE: 有 proxy 时返回 None（TLS 由网关集群处理）
        """
