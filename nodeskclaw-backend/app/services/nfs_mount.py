"""Remote file operations on OpenClaw Pods via kubectl exec.

Replaces the previous NFS mount approach. Each file read/write/delete
is a single exec call to the target Pod — no temp dirs, no tar, no bulk sync.
"""

import base64
import json
import logging
import pathlib
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
    def __init__(self, message: str = "远程文件操作失败", message_key: str | None = None):
        super().__init__(code=50300, message=message, status_code=503, message_key=message_key)


class SkillScanError(Exception):
    """scan_skills 执行失败（区别于"Pod 内没有 skill"的正常空结果）。

    不继承 AppException，由调用方捕获后走降级路径，不应被 API 全局异常处理器拦截。
    """


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

    async def read_binary(self, path: str) -> bytes | None:
        """Read a file as raw bytes via base64 encoding (exec channel cannot transmit raw binary)."""
        try:
            result = await self._k8s.exec_in_pod(
                self._ns, self._pod,
                ["bash", "-c", f"base64 '/root/{path}' 2>/dev/null"],
                container=self._container,
            )
            if not result:
                return None
            return base64.b64decode(result)
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
            await self._k8s.exec_in_pod(
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

        Returns a list of dicts ``{name, is_dir, size, modified_at}`` (may be
        empty for an existing but empty directory) or *None* when the path
        does not exist.
        """
        try:
            result = await self._k8s.exec_in_pod(
                self._ns, self._pod,
                ["bash", "-c",
                 f"if [ -d '/root/{path}' ]; then "
                 f"find '/root/{path}' -maxdepth 1 -mindepth 1 "
                 f"-printf '%y\\t%s\\t%T@\\t%f\\n' 2>/dev/null; "
                 f"echo '__DIR_OK__'; "
                 f"else echo '__NOT_FOUND__'; fi"],
                container=self._container,
            )
        except Exception:
            return None

        if not result or "__NOT_FOUND__" in result:
            return None

        items: list[dict] = []
        for line in result.strip().splitlines():
            if line == "__DIR_OK__":
                continue
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


    async def scan_skills(self, skills_dir_rel: str) -> list[dict]:
        """Batch-scan all skill directories under *skills_dir_rel*.

        Uses a single ``bash -c`` exec with a base64-encoded Node.js script
        to list every sub-directory, read its ``SKILL.md`` content, and count
        the files it contains.  The script outputs base64-encoded JSON to
        avoid UTF-8 multi-byte splitting in the WebSocket transport layer.

        Returns ``[{name, content, file_count}]``.
        Raises ``SkillScanError`` on failure (never returns ``[]`` as a
        silent fallback — the caller must distinguish "empty" from "failed").
        """
        abs_dir = f"/root/{skills_dir_rel}"
        js = (
            'const fs=require("fs"),path=require("path");'
            f'const dir="{abs_dir}";'
            'const r=[];'
            'if(fs.existsSync(dir)){'
            'for(const n of fs.readdirSync(dir).sort()){'
            'const d=path.join(dir,n);'
            'if(!fs.statSync(d).isDirectory())continue;'
            'const md=path.join(d,"SKILL.md");'
            'let c="";'
            'if(fs.existsSync(md))c=fs.readFileSync(md,"utf8");'
            'const fc=fs.readdirSync(d).filter(f=>fs.statSync(path.join(d,f)).isFile()).length;'
            'r.push({name:n,content:c,file_count:fc});'
            '}}'
            'process.stdout.write(Buffer.from(JSON.stringify(r)).toString("base64"));'
        )
        encoded = base64.b64encode(js.encode()).decode("ascii")
        try:
            raw = await self._k8s.exec_in_pod(
                self._ns, self._pod,
                ["bash", "-c", f"printf '%s' '{encoded}' | base64 -d | node"],
                container=self._container,
            )
            if not raw:
                return []
            decoded = base64.b64decode(raw).decode("utf-8")
            return json.loads(decoded)
        except Exception as exc:
            logger.warning("scan_skills failed for %s/%s", self._ns, self._pod, exc_info=True)
            raise SkillScanError(f"scan_skills failed: {exc}") from exc


async def _get_k8s_client(instance: Instance, db: AsyncSession) -> K8sClient:
    cluster_result = await db.execute(
        select(Cluster).where(
            Cluster.id == instance.cluster_id,
            Cluster.deleted_at.is_(None),
        )
    )
    cluster = cluster_result.scalar_one_or_none()
    if not cluster or not cluster.is_k8s or not cluster.credentials_encrypted:
        raise NFSMountError("实例所属集群不可用")
    api_client = await k8s_manager.get_or_create(cluster.id, cluster.credentials_encrypted)
    return K8sClient(api_client)


def _k8s_name(instance: Instance) -> str:
    return instance.slug or instance.name


async def _find_running_pod(
    k8s: K8sClient, instance: Instance,
) -> tuple[str, str]:
    """Return (pod_name, container_name) for the first pod with a running container.

    For kubectl exec file operations we only need the container process to be
    alive (state == "running").  The readiness probe is irrelevant here — it
    controls Service routing, not exec availability.
    """
    container = _k8s_name(instance)
    label_selector = f"app.kubernetes.io/name={container}"
    pods = await k8s.list_pods(instance.namespace, label_selector)
    running = [p for p in pods if p["phase"] == "Running"]
    if not running:
        raise NFSMountError("实例无运行中的 Pod，无法同步文件")
    usable = [
        p for p in running
        if any(c.get("state") == "running" for c in p.get("containers", []))
    ]
    if not usable:
        raise NFSMountError(
            "实例正在启动中，请稍后重试",
            message_key="errors.instance.pod_not_ready",
        )
    return usable[0]["name"], container


class DockerFS:
    """Host filesystem proxy for Docker instances — files at DOCKER_DATA_DIR/{slug}/data/."""

    def __init__(self, slug: str, home_prefix: str = ".openclaw"):
        from app.services.docker_constants import DOCKER_DATA_DIR
        self._slug = slug
        self._base = DOCKER_DATA_DIR / slug / "data"
        self._home_prefix = home_prefix.strip("/")
        self._abs_prefix = f"/root/{self._home_prefix}"
        import os
        os.makedirs(str(self._base), exist_ok=True)

    def _resolve(self, remote_path: str) -> pathlib.Path:
        abs_slash = self._abs_prefix + "/"
        if remote_path.startswith(abs_slash):
            rel = remote_path[len(abs_slash):]
        elif remote_path.startswith(self._abs_prefix):
            rel = remote_path[len(self._abs_prefix):]
        elif remote_path.startswith(self._home_prefix + "/"):
            rel = remote_path[len(self._home_prefix) + 1:]
        elif remote_path == self._home_prefix:
            rel = ""
        else:
            rel = remote_path.lstrip("/")
        return self._base / rel

    async def read_text(self, remote_path: str) -> str | None:
        """Read a file from local Docker data dir. Returns None if file does not exist."""
        p = self._resolve(remote_path)
        if not p.exists():
            return None
        return p.read_text(encoding="utf-8")

    async def write_text(self, remote_path: str, content: str) -> None:
        p = self._resolve(remote_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    async def read_binary(self, remote_path: str) -> bytes | None:
        """Read a file as raw bytes. Returns None if file does not exist."""
        p = self._resolve(remote_path)
        if not p.exists():
            return None
        return p.read_bytes()

    async def write_binary(self, remote_path: str, data: bytes) -> None:
        p = self._resolve(remote_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    async def remove(self, remote_path: str) -> None:
        p = self._resolve(remote_path)
        if p.exists():
            p.unlink()

    async def exists(self, remote_path: str) -> bool:
        return self._resolve(remote_path).exists()

    async def mkdir(self, remote_path: str) -> None:
        p = self._resolve(remote_path)
        p.mkdir(parents=True, exist_ok=True)

    async def list_dir(self, remote_path: str) -> list[dict] | None:
        p = self._resolve(remote_path)
        if not p.exists():
            return None
        items = []
        for f in p.iterdir():
            st = f.stat()
            items.append({
                "name": f.name,
                "is_dir": f.is_dir(),
                "size": st.st_size,
                "modified_at": st.st_mtime,
            })
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return items

    async def scan_skills(self, skills_dir_rel: str) -> list[dict]:
        """Scan skills directory — returns [{name, content, file_count}]."""
        skills_dir = self._resolve(skills_dir_rel)
        if not skills_dir.exists():
            return []
        results = []
        for skill_path in sorted(skills_dir.iterdir()):
            if not skill_path.is_dir():
                continue
            skill_md = skill_path / "SKILL.md"
            content = skill_md.read_text(encoding="utf-8") if skill_md.exists() else ""
            file_count = sum(1 for f in skill_path.iterdir() if f.is_file())
            results.append({"name": skill_path.name, "content": content, "file_count": file_count})
        return results

    async def file_stat(self, path: str) -> dict | None:
        import mimetypes
        p = self._resolve(path)
        if not p.exists():
            return None
        st = p.stat()
        mime, _ = mimetypes.guess_type(p.name)
        return {
            "size": st.st_size,
            "modified_at": st.st_mtime,
            "mime_type": mime or "application/octet-stream",
        }

    async def append_text(self, remote_path: str, content: str) -> None:
        p = self._resolve(remote_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(content)

    async def read_last_line(self, remote_path: str) -> str | None:
        p = self._resolve(remote_path)
        if not p.exists():
            return None
        lines = p.read_text(encoding="utf-8").strip().splitlines()
        return lines[-1] if lines else None

    async def exec_command(self, cmd: list[str]) -> str:
        """Run a command inside the Docker container via docker exec."""
        import asyncio
        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", self._slug, *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            raise NFSMountError(f"docker exec 失败 (rc={proc.returncode}): {stdout.decode()[:500]}")
        return stdout.decode() if stdout else ""


RemoteFS = PodFS | DockerFS


def _home_prefix_for_runtime(runtime: str) -> str:
    from app.services.runtime.registries.runtime_registry import RUNTIME_REGISTRY
    spec = RUNTIME_REGISTRY.get(runtime)
    if spec:
        return spec.data_dir_container_path.removeprefix("/root/").strip("/")
    return ".openclaw"


@asynccontextmanager
async def remote_fs(instance: Instance, db: AsyncSession) -> AsyncIterator[RemoteFS]:
    """Yield a filesystem proxy connected to the instance.

    Docker instances use DockerFS (direct host path access).
    K8s instances use PodFS (kubectl exec).
    """
    if instance.compute_provider == "docker":
        prefix = _home_prefix_for_runtime(instance.runtime)
        yield DockerFS(instance.slug, home_prefix=prefix)
    else:
        k8s = await _get_k8s_client(instance, db)
        pod_name, container = await _find_running_pod(k8s, instance)
        logger.debug("remote_fs: pod=%s container=%s ns=%s", pod_name, container, instance.namespace)
        yield PodFS(k8s, instance.namespace, pod_name, container)
