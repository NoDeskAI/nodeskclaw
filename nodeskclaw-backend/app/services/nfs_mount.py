"""NFS temporary mount: mount PVC storage via NFS for local file I/O, unmount after use."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.cluster import Cluster
from app.models.instance import Instance
from app.services.k8s.client_manager import k8s_manager
from app.services.k8s.k8s_client import K8sClient

logger = logging.getLogger(__name__)

NFS_BASE_DIR = Path("/tmp/nodeskclaw-nfs")

_nfs_info_cache: dict[str, tuple[str, str, list[str]]] = {}


class NFSMountError(AppException):
    def __init__(self, message: str = "NFS 挂载失败"):
        super().__init__(code=50300, message=message, status_code=503)


async def _get_k8s_client(instance: Instance, db: AsyncSession) -> K8sClient:
    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id)
    )
    cluster = cluster_result.scalar_one_or_none()
    if not cluster or not cluster.kubeconfig_encrypted:
        raise NFSMountError("实例所属集群不可用，无法查询 NFS 信息")
    api_client = await k8s_manager.get_or_create(cluster.id, cluster.kubeconfig_encrypted)
    return K8sClient(api_client)


def _k8s_name(instance: Instance) -> str:
    return instance.slug or instance.name


async def _resolve_nfs_info(instance: Instance, db: AsyncSession) -> tuple[str, str, list[str]]:
    """Resolve NFS server + path from PVC -> PV spec. Results are cached by instance ID.

    Supports both native NFS PVs (spec.nfs) and CSI-based NAS PVs
    (spec.csi with volumeAttributes containing server/path, e.g. VKE nas-subpath).
    """
    cached = _nfs_info_cache.get(instance.id)
    if cached:
        return cached

    k8s = await _get_k8s_client(instance, db)
    pvc_name = f"{_k8s_name(instance)}-root-data"

    try:
        pvc = await k8s.read_pvc(instance.namespace, pvc_name)
    except Exception as e:
        raise NFSMountError(f"读取 PVC {pvc_name} 失败: {e}") from e

    pv_name = pvc.spec.volume_name
    if not pv_name:
        raise NFSMountError(f"PVC {pvc_name} 尚未绑定 PV")

    try:
        pv = await k8s.read_pv(pv_name)
    except Exception as e:
        raise NFSMountError(f"读取 PV {pv_name} 失败: {e}") from e

    server: str | None = None
    path: str | None = None
    mount_options: list[str] = []

    if pv.spec.nfs:
        server = pv.spec.nfs.server
        path = pv.spec.nfs.path
    elif pv.spec.csi and pv.spec.csi.volume_attributes:
        attrs = pv.spec.csi.volume_attributes
        server = attrs.get("server")
        path = attrs.get("path")
    else:
        raise NFSMountError(f"PV {pv_name} 既非 NFS 类型也非 CSI NAS 类型，无法提取存储地址")

    if not server or not path:
        raise NFSMountError(f"PV {pv_name} 缺少 NFS server 或 path")

    if pv.spec.mount_options:
        mount_options = list(pv.spec.mount_options)

    _nfs_info_cache[instance.id] = (server, path, mount_options)
    logger.info(
        "解析 NFS 信息: instance=%s server=%s path=%s mount_options=%s",
        instance.name, server, path, mount_options,
    )
    return server, path, mount_options


async def _run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode or 0, stdout.decode(), stderr.decode()


@asynccontextmanager
async def nfs_mount(instance: Instance, db: AsyncSession) -> AsyncIterator[Path]:
    """Temporarily mount instance PVC via NFS, yield local path, unmount on exit."""
    server, nfs_path, mount_options = await _resolve_nfs_info(instance, db)

    mount_point = NFS_BASE_DIR / instance.namespace
    mount_point.mkdir(parents=True, exist_ok=True)

    already_mounted = False
    if mount_point.is_mount():
        already_mounted = True
        logger.debug("挂载点 %s 已存在，复用", mount_point)

    if not already_mounted:
        nfs_source = f"{server}:{nfs_path}"
        cmd = ["sudo", "-n", "mount", "-t", "nfs"]
        if mount_options:
            cmd += ["-o", ",".join(mount_options)]
        cmd += [nfs_source, str(mount_point)]
        rc, _out, err = await _run_cmd(cmd)
        if rc != 0:
            try:
                mount_point.rmdir()
            except OSError:
                pass
            if "a password is required" in err.lower():
                raise NFSMountError(
                    "NFS 挂载需要 sudo 权限。请运行以下命令配置免密:\n"
                    "sudo sh -c 'echo \"$(whoami) ALL=(ALL) NOPASSWD: "
                    "/sbin/mount, /sbin/umount, /bin/chmod, /bin/mkdir\" "
                    "> /etc/sudoers.d/nodeskclaw-nfs && chmod 440 /etc/sudoers.d/nodeskclaw-nfs'"
                )
            if "permission denied" in err.lower() or "not permitted" in err.lower():
                raise NFSMountError(f"NFS 挂载失败（权限不足）: {err.strip()}")
            raise NFSMountError(f"NFS 挂载失败: {err.strip()}")
        logger.info("已挂载 NFS: %s -> %s (options=%s)", nfs_source, mount_point, mount_options)

        rc, _out, err = await _run_cmd(
            ["sudo", "-n", "chmod", "-R", "a+rwX", str(mount_point)]
        )
        if rc != 0:
            logger.warning("NFS 挂载后修复权限失败: %s", err.strip())
        else:
            logger.debug("已修复 NFS 挂载点权限: %s", mount_point)

    try:
        yield mount_point
    finally:
        if not already_mounted:
            rc, _out, err = await _run_cmd(["sudo", "-n", "umount", str(mount_point)])
            if rc != 0:
                logger.warning("NFS 卸载失败: %s (err=%s)", mount_point, err.strip())
            else:
                logger.info("已卸载 NFS: %s", mount_point)
            try:
                mount_point.rmdir()
            except OSError:
                pass
