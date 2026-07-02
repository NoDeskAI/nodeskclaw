"""ComputeRegistry — maps compute provider identifiers to ComputeProvider instances."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.k8s.k8s_client import K8sClient

logger = logging.getLogger(__name__)


class ComputeCapability:
    K8S_EVENTS = "k8s_events"
    POD_LOGS = "pod_logs"
    STORAGE_CLASSES = "storage_classes"
    K8S_OVERVIEW = "k8s_overview"
    CONFIGMAP = "configmap"
    EXEC = "exec"


@dataclass(frozen=True)
class ComputeSpec:
    compute_id: str
    provider: Any = None
    description: str | None = None
    supports_sidecar: bool = True
    capabilities: frozenset[str] = field(default_factory=frozenset)
    config_schema: dict | None = None


class ComputeRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ComputeSpec] = {}

    def register(self, spec: ComputeSpec) -> None:
        self._providers[spec.compute_id] = spec
        logger.debug("Registered compute provider: %s", spec.compute_id)

    def get(self, compute_id: str) -> ComputeSpec | None:
        return self._providers.get(compute_id)

    def all_providers(self) -> list[ComputeSpec]:
        return list(self._providers.values())


COMPUTE_REGISTRY = ComputeRegistry()


async def require_k8s_client(cluster) -> K8sClient:
    """检查集群类型并获取 K8s 客户端。非 K8s 集群直接抛出 BadRequestError。"""
    from app.core.exceptions import BadRequestError

    spec = COMPUTE_REGISTRY.get(cluster.compute_provider)
    if not spec or not hasattr(spec.provider, "get_k8s_client"):
        raise BadRequestError(
            message=f"集群类型 {cluster.compute_provider} 不支持此操作",
            message_key="errors.cluster.unsupported_operation",
        )
    return await spec.provider.get_k8s_client(cluster)


def _register_builtins() -> None:
    from app.services.runtime.compute.k8s_provider import K8sComputeProvider
    from app.services.runtime.compute.process_provider import ProcessComputeProvider

    COMPUTE_REGISTRY.register(ComputeSpec(
        compute_id="k8s",
        provider=K8sComputeProvider(),
        description="Kubernetes compute -- Deployment + Service + NetworkPolicy.",
        supports_sidecar=True,
        capabilities=frozenset({
            ComputeCapability.K8S_EVENTS, ComputeCapability.POD_LOGS,
            ComputeCapability.STORAGE_CLASSES, ComputeCapability.K8S_OVERVIEW,
            ComputeCapability.CONFIGMAP, ComputeCapability.EXEC,
        }),
    ))
    COMPUTE_REGISTRY.register(ComputeSpec(
        compute_id="process",
        provider=ProcessComputeProvider(),
        description="Local process compute -- subprocess management for dev/testing.",
        supports_sidecar=False,
        capabilities=frozenset(),
    ))


_register_builtins()
