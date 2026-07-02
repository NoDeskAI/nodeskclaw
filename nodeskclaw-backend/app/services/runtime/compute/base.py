"""ComputeProvider — protocol for managing agent compute resources (K8s, process, etc.)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


@dataclass
class InstanceComputeConfig:
    instance_id: str
    name: str
    slug: str
    namespace: str
    image_version: str
    runtime: str = "openclaw"
    gateway_port: int = 18789
    replicas: int = 1
    cpu_request: str = "500m"
    cpu_limit: str = "2000m"
    mem_request: str = "2Gi"
    mem_limit: str = "2Gi"
    storage_class: str | None = None
    storage_size: str = "80Gi"
    env_vars: dict = field(default_factory=dict)
    advanced_config: dict = field(default_factory=dict)
    companion: CompanionSpec | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class CompanionSpec:
    enabled: bool = False
    image: str = ""
    port: int = 8080
    env_vars: dict = field(default_factory=dict)


@dataclass
class ComputeHandle:
    provider: str
    instance_id: str
    namespace: str
    endpoint: str = ""
    status: str = "pending"
    extra: dict = field(default_factory=dict)


class ComputeProvider(Protocol):
    async def create_instance(
        self, config: InstanceComputeConfig, **kwargs,
    ) -> ComputeHandle:
        """Create compute resources for an agent instance."""
        ...

    async def destroy_instance(
        self, handle: ComputeHandle,
    ) -> None:
        """Destroy compute resources for an agent instance."""
        ...

    async def get_status(
        self, handle: ComputeHandle,
    ) -> str:
        """Get the current status of compute resources."""
        ...

    async def get_endpoint(
        self, handle: ComputeHandle,
    ) -> str:
        """Get the network endpoint for the agent instance."""
        ...

    async def get_logs(
        self, handle: ComputeHandle, *, tail: int = 50,
    ) -> str:
        """Get recent logs from the agent instance."""
        ...

    async def update_instance(
        self, handle: ComputeHandle, config: InstanceComputeConfig,
    ) -> ComputeHandle:
        """Update compute resources (e.g., image version, resources, runtime)."""
        ...

    async def restart_instance(
        self, handle: ComputeHandle,
    ) -> None:
        """Restart compute resources."""
        ...

    async def scale_instance(
        self, handle: ComputeHandle, replicas: int,
    ) -> ComputeHandle:
        """Scale compute resources."""
        ...

    async def health_check(
        self, handle: ComputeHandle,
    ) -> dict:
        """Check if the service is actually accessible.
        Returns {"healthy": bool | None, "detail": str}.
        healthy=True  -> service responding
        healthy=False -> service unreachable
        healthy=None  -> cannot determine (no endpoint / no credentials)
        """
        ...


async def http_probe(endpoint: str, timeout: float = 5.0, path: str = "/") -> dict:
    """HTTP GET probe against an endpoint.
    Any HTTP response (incl. 401/403/500) = healthy.
    Connection error / timeout = unhealthy.
    Empty endpoint = unknown.
    """
    if not endpoint:
        logger.debug("http_probe skipped: no endpoint")
        return {"healthy": None, "detail": "no endpoint configured"}
    url = endpoint if endpoint.startswith(("http://", "https://")) else f"http://{endpoint}"
    if path and path != "/":
        url = url.rstrip("/") + path
    try:
        async with httpx.AsyncClient(timeout=timeout, verify=False, trust_env=False) as client:
            resp = await client.get(url)
            logger.debug("http_probe %s -> HTTP %d", url, resp.status_code)
            return {"healthy": True, "detail": f"HTTP {resp.status_code}"}
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        detail = "connection refused or timeout"
        logger.warning("http_probe %s -> %s (%s)", url, detail, type(e).__name__)
        return {"healthy": False, "detail": detail}
    except Exception as e:
        detail = str(e)[:200] or type(e).__name__
        logger.warning("http_probe %s -> %s (%s)", url, detail, type(e).__name__)
        return {"healthy": False, "detail": detail}
