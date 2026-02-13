"""K8s client manager: connection pool with health check and token detection."""

import logging
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone

from kubernetes_asyncio import client as k8s_client
from kubernetes_asyncio.config import load_kube_config

from app.core.security import decrypt_kubeconfig

logger = logging.getLogger(__name__)


@dataclass
class ClientEntry:
    """Cached K8s client entry."""

    api_client: k8s_client.ApiClient
    auth_type: str = "unknown"
    server: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_health_check: datetime | None = None
    healthy: bool = True


async def _load_client_from_str(kubeconfig_yaml: str) -> k8s_client.ApiClient:
    """Load ApiClient from kubeconfig YAML string (tempfile approach)."""
    cfg = k8s_client.Configuration()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=True) as f:
        f.write(kubeconfig_yaml)
        f.flush()
        await load_kube_config(config_file=f.name, client_configuration=cfg)
    return k8s_client.ApiClient(configuration=cfg)


@asynccontextmanager
async def create_temp_client(kubeconfig_plain: str):
    """Create a temporary ApiClient from kubeconfig YAML string."""
    api = await _load_client_from_str(kubeconfig_plain)
    try:
        yield api
    finally:
        await api.close()


class K8sClientManager:
    """Manages cached ApiClient instances keyed by cluster_id."""

    def __init__(self):
        self._entries: dict[str, ClientEntry] = {}

    async def get_or_create(
        self,
        cluster_id: str,
        kubeconfig_encrypted: str,
        *,
        check_health: bool = False,
    ) -> k8s_client.ApiClient:
        """Get existing client or create from encrypted kubeconfig."""
        entry = self._entries.get(cluster_id)

        if entry is not None:
            if check_health:
                ok = await self._health_check(entry)
                if not ok:
                    logger.warning("Cluster %s unhealthy, rebuilding", cluster_id)
                    await self.remove(cluster_id)
                    return await self._create(cluster_id, kubeconfig_encrypted)
            return entry.api_client

        return await self._create(cluster_id, kubeconfig_encrypted)

    async def _create(self, cluster_id: str, kubeconfig_encrypted: str) -> k8s_client.ApiClient:
        kubeconfig_plain = decrypt_kubeconfig(kubeconfig_encrypted)
        api = await _load_client_from_str(kubeconfig_plain)
        self._entries[cluster_id] = ClientEntry(api_client=api)
        return api

    async def _health_check(self, entry: ClientEntry) -> bool:
        try:
            version_api = k8s_client.VersionApi(entry.api_client)
            await version_api.get_code()
            entry.healthy = True
            entry.last_health_check = datetime.now(timezone.utc)
            return True
        except Exception as e:
            logger.warning("Health check failed: %s", e)
            entry.healthy = False
            return False

    async def rebuild(self, cluster_id: str, kubeconfig_encrypted: str) -> k8s_client.ApiClient:
        await self.remove(cluster_id)
        return await self._create(cluster_id, kubeconfig_encrypted)

    async def remove(self, cluster_id: str):
        entry = self._entries.pop(cluster_id, None)
        if entry:
            await entry.api_client.close()

    async def close_all(self):
        for entry in self._entries.values():
            await entry.api_client.close()
        self._entries.clear()

    def get_status(self) -> dict[str, dict]:
        return {
            cid: {
                "healthy": e.healthy,
                "server": e.server,
                "created_at": e.created_at.isoformat(),
            }
            for cid, e in self._entries.items()
        }


# Singleton
k8s_manager = K8sClientManager()
