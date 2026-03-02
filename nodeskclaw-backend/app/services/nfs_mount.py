"""Remote file operations on OpenClaw Pods via kubectl exec.

Replaces the previous NFS mount approach. Each file read/write/delete
is a single exec call to the target Pod — no temp dirs, no tar, no bulk sync.
"""

import base64
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.cluster import Cluster
from app.models.instance import Instance
from app.services.k8s.client_manager import k8s_manager
from app.services.k8s.k8s_client import K8sClient

logger = logging.getLogger(__name__)

CHUNK_SIZE = 98_000


class NFSMountError(AppException):
    def __init__(self, message: str = "远程文件操作失败"):
        super().__init__(code=50300, message=message, status_code=503)


class PodFS:
    """Remote filesystem proxy — each method is one kubectl exec call."""

    def __init__(self, k8s: K8sClient, ns: str, pod: str, container: str):
        self._k8s = k8s
        self._ns = ns
        self._pod = pod
        self._container = container

    async def read_text(self, path: str) -> str | None:
        """Read a file from the Pod. Returns None if the file does not exist."""
        try:
            result = await self._k8s.exec_in_pod(
                self._ns, self._pod,
                ["bash", "-c", f"cat '/root/{path}' 2>/dev/null || true"],
                container=self._container,
            )
            return result if result else None
        except Exception:
            return None

    async def write_text(self, path: str, content: str) -> None:
        """Write content to a file in the Pod (creates parent dirs)."""
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        if len(encoded) < CHUNK_SIZE:
            await self._k8s.exec_in_pod(
                self._ns, self._pod,
                ["bash", "-c",
                 f"mkdir -p \"$(dirname '/root/{path}')\" && "
                 f"printf '%s' '{encoded}' | base64 -d > '/root/{path}'"],
                container=self._container,
            )
        else:
            await self._chunked_write(path, encoded)

    async def _chunked_write(self, path: str, encoded: str) -> None:
        tmp = "/tmp/_ndk_upload.b64"
        await self._k8s.exec_in_pod(
            self._ns, self._pod, ["rm", "-f", tmp],
            container=self._container,
        )
        for i in range(0, len(encoded), CHUNK_SIZE):
            chunk = encoded[i:i + CHUNK_SIZE]
            await self._k8s.exec_in_pod(
                self._ns, self._pod,
                ["bash", "-c", f"printf '%s' '{chunk}' >> {tmp}"],
                container=self._container,
            )
        await self._k8s.exec_in_pod(
            self._ns, self._pod,
            ["bash", "-c",
             f"mkdir -p \"$(dirname '/root/{path}')\" && "
             f"base64 -d {tmp} > '/root/{path}' && rm -f {tmp}"],
            container=self._container,
        )

    async def remove(self, path: str) -> None:
        """Remove a file or directory from the Pod."""
        await self._k8s.exec_in_pod(
            self._ns, self._pod,
            ["rm", "-rf", f"/root/{path}"],
            container=self._container,
        )

    async def exists(self, path: str) -> bool:
        try:
            result = await self._k8s.exec_in_pod(
                self._ns, self._pod,
                ["test", "-e", f"/root/{path}"],
                container=self._container,
            )
            return True
        except Exception:
            return False

    async def mkdir(self, path: str) -> None:
        await self._k8s.exec_in_pod(
            self._ns, self._pod,
            ["mkdir", "-p", f"/root/{path}"],
            container=self._container,
        )

    async def append_text(self, path: str, content: str) -> None:
        """Append content to a file in the Pod."""
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        await self._k8s.exec_in_pod(
            self._ns, self._pod,
            ["bash", "-c",
             f"printf '%s' '{encoded}' | base64 -d >> '/root/{path}'"],
            container=self._container,
        )

    async def read_last_line(self, path: str) -> str | None:
        """Read the last line of a file from the Pod."""
        try:
            result = await self._k8s.exec_in_pod(
                self._ns, self._pod,
                ["bash", "-c", f"tail -1 '/root/{path}' 2>/dev/null || true"],
                container=self._container,
            )
            return result if result else None
        except Exception:
            return None

    async def list_dir(self, path: str) -> list[dict] | None:
        """List directory contents with metadata via a single exec call.

        Returns a list of dicts ``{name, is_dir, size, modified_at}`` or
        *None* when the path does not exist.
        """
        try:
            result = await self._k8s.exec_in_pod(
                self._ns, self._pod,
                ["bash", "-c",
                 f"find '/root/{path}' -maxdepth 1 -mindepth 1 "
                 f"-printf '%y\\t%s\\t%T@\\t%f\\n' 2>/dev/null || echo '__NOT_FOUND__'"],
                container=self._container,
            )
        except Exception:
            return None

        if not result or "__NOT_FOUND__" in result:
            return None

        items: list[dict] = []
        for line in result.strip().splitlines():
            parts = line.split("\t", 3)
            if len(parts) < 4:
                continue
            ftype, size_str, mtime_str, name = parts
            items.append({
                "name": name,
                "is_dir": ftype == "d",
                "size": int(size_str) if size_str.isdigit() else 0,
                "modified_at": float(mtime_str) if mtime_str.replace(".", "", 1).isdigit() else 0.0,
            })
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return items

    async def file_stat(self, path: str) -> dict | None:
        """Get file metadata: size, modified_at, mime_type."""
        try:
            result = await self._k8s.exec_in_pod(
                self._ns, self._pod,
                ["bash", "-c",
                 f"if stat -c '%s|%Y' '/root/{path}' 2>/dev/null; then "
                 f"file -bi '/root/{path}' 2>/dev/null || echo 'application/octet-stream'; "
                 f"else echo '__NOT_FOUND__'; fi"],
                container=self._container,
            )
        except Exception:
            return None

        if not result or "__NOT_FOUND__" in result:
            return None

        lines = result.strip().splitlines()
        if len(lines) < 1:
            return None
        stat_parts = lines[0].split("|")
        if len(stat_parts) < 2:
            return None
        mime = lines[1].strip().split(";")[0] if len(lines) > 1 else "application/octet-stream"
        return {
            "size": int(stat_parts[0]) if stat_parts[0].isdigit() else 0,
            "modified_at": float(stat_parts[1]) if stat_parts[1].isdigit() else 0.0,
            "mime_type": mime,
        }


async def _get_k8s_client(instance: Instance, db: AsyncSession) -> K8sClient:
    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id)
    )
    cluster = cluster_result.scalar_one_or_none()
    if not cluster or not cluster.kubeconfig_encrypted:
        raise NFSMountError("实例所属集群不可用")
    api_client = await k8s_manager.get_or_create(cluster.id, cluster.kubeconfig_encrypted)
    return K8sClient(api_client)


def _k8s_name(instance: Instance) -> str:
    return instance.slug or instance.name


async def _find_running_pod(
    k8s: K8sClient, instance: Instance,
) -> tuple[str, str]:
    """Return (pod_name, container_name) for the first Running pod."""
    container = _k8s_name(instance)
    label_selector = f"app.kubernetes.io/name={container}"
    pods = await k8s.list_pods(instance.namespace, label_selector)
    running = [p for p in pods if p["phase"] == "Running"]
    if not running:
        raise NFSMountError("实例无运行中的 Pod，无法同步文件")
    return running[0]["name"], container


@asynccontextmanager
async def remote_fs(instance: Instance, db: AsyncSession) -> AsyncIterator[PodFS]:
    """Yield a PodFS connected to the instance's running Pod."""
    k8s = await _get_k8s_client(instance, db)
    pod_name, container = await _find_running_pod(k8s, instance)
    logger.debug("remote_fs: pod=%s container=%s ns=%s", pod_name, container, instance.namespace)
    yield PodFS(k8s, instance.namespace, pod_name, container)
