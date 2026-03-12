"""ComputeProvider — protocol for managing agent compute resources (K8s, Docker, etc.)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class InstanceComputeConfig:
    instance_id: str
    name: str
    slug: str
    namespace: str
    image_version: str
    runtime: str = "openclaw"
    replicas: int = 1
    cpu_request: str = "500m"
    cpu_limit: str = "2000m"
    mem_request: str = "2Gi"
    mem_limit: str = "2Gi"
    storage_class: str = "nas-subpath"
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
