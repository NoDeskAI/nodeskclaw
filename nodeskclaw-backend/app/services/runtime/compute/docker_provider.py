"""DockerComputeProvider — manages agent instances as Docker Compose services."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import PurePosixPath, PureWindowsPath

from app.services.docker_constants import DOCKER_DATA_DIR, DOCKER_HOST_DATA_DIR
from app.services.runtime.compute.base import (
    ComputeHandle,
    InstanceComputeConfig,
)

logger = logging.getLogger(__name__)

_LOCALHOST_RE = re.compile(r"(https?://)(localhost|127\.0\.0\.1)(:\d+)?")
_WINDOWS_HOST_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _docker_endpoint_host() -> str:
    """Return the hostname for reaching host-mapped ports from the backend process.

    Inside a container: host.docker.internal (host ports are not on localhost).
    On the host directly: localhost.
    """
    if os.path.exists("/.dockerenv") or os.environ.get("DOCKER_DATA_DIR"):
        return "host.docker.internal"
    return "localhost"


def _parse_cpu(cpu_str: str) -> float:
    """Convert K8s-style cpu (e.g. '2000m', '2') to Docker cpus float."""
    s = cpu_str.strip().lower()
    if s.endswith("m"):
        return int(s[:-1]) / 1000
    return float(s)


_K8S_MEM_SUFFIXES: dict[str, str] = {
    "ki": "k", "mi": "m", "gi": "g", "ti": "t", "pi": "p",
}


def _parse_mem(mem_str: str) -> str:
    """Convert K8s-style memory (e.g. '2Gi', '512Mi') to Docker format ('2g', '512m')."""
    s = mem_str.strip()
    lower = s.lower()
    for k8s_suffix, docker_suffix in _K8S_MEM_SUFFIXES.items():
        if lower.endswith(k8s_suffix):
            return s[:-len(k8s_suffix)] + docker_suffix
    if lower[-1:].isdigit() or lower.endswith(("k", "m", "g", "t", "b")):
        return s
    raise ValueError(f"Unsupported memory unit: {mem_str!r}")


def _extract_docker_error(stderr_text: str) -> str:
    """Extract the meaningful error from docker compose stderr, stripping progress noise."""
    marker = "Error response from daemon:"
    idx = stderr_text.find(marker)
    if idx != -1:
        return stderr_text[idx:].strip()[:500]
    idx2 = stderr_text.rfind("Error")
    if idx2 != -1:
        return stderr_text[idx2:].strip()[:500]
    return stderr_text.strip()[:500]


def _join_host_path(base: str, *parts: str) -> str:
    if _WINDOWS_HOST_PATH_RE.match(base) or base.startswith("\\\\"):
        return str(PureWindowsPath(base, *parts))
    return str(PurePosixPath(base, *parts))


def _pure_host_path(path: str) -> PureWindowsPath | PurePosixPath:
    if _WINDOWS_HOST_PATH_RE.match(path) or path.startswith("\\\\"):
        return PureWindowsPath(path)
    return PurePosixPath(path)


def _compose_path_for_slug(slug: str) -> str:
    return str(DOCKER_DATA_DIR / slug / "docker-compose.yml")


def _remap_legacy_compose_path(stored_path: str) -> str:
    if not stored_path:
        return ""

    try:
        rel = _pure_host_path(stored_path).relative_to(_pure_host_path(DOCKER_HOST_DATA_DIR))
    except ValueError:
        return ""

    return str(DOCKER_DATA_DIR.joinpath(*rel.parts))


def _resolve_compose_path(slug: str, stored_path: str) -> str:
    current_path = _compose_path_for_slug(slug)
    if os.path.exists(current_path):
        return current_path

    remapped_path = _remap_legacy_compose_path(stored_path)
    if remapped_path and os.path.exists(remapped_path):
        return remapped_path

    if stored_path and os.path.exists(stored_path):
        return stored_path

    return current_path


def _build_compose_yaml(config: InstanceComputeConfig) -> dict:
    """Generate a docker-compose service definition with full resource config."""
    env = {
        k: _LOCALHOST_RE.sub(r"\1host.docker.internal\3", str(v))
        for k, v in config.env_vars.items()
    }
    host_port = env.get("DOCKER_HOST_PORT", "3000")

    from app.services.runtime.registries.runtime_registry import RUNTIME_REGISTRY
    rt_spec = RUNTIME_REGISTRY.get(config.runtime)
    container_data_dir = rt_spec.data_dir_container_path if rt_spec else "/root/.openclaw"
    host_data_dir = _join_host_path(DOCKER_HOST_DATA_DIR, config.slug, "data")

    main_service: dict = {
        "image": env.get("DOCKER_IMAGE", f"deskclaw:{config.image_version}"),
        "container_name": config.slug,
        "environment": env,
        "ports": [f"{host_port}:{config.gateway_port}"],
        "volumes": [{
            "type": "bind",
            "source": host_data_dir,
            "target": container_data_dir,
        }],
        "restart": "unless-stopped",
        "platform": "linux/amd64",
        "networks": [f"{config.slug}-net"],
        "extra_hosts": ["host.docker.internal:host-gateway"],
    }

    if config.mem_limit:
        main_service["mem_limit"] = _parse_mem(config.mem_limit)
    if config.cpu_limit:
        try:
            parsed = _parse_cpu(config.cpu_limit)
            available = os.cpu_count() or 1
            if parsed <= available:
                main_service["cpus"] = parsed
            else:
                logger.warning(
                    "requested cpus %.2f exceeds available %d, skipping cpu limit",
                    parsed, available,
                )
        except (ValueError, TypeError):
            pass

    if config.companion and config.companion.enabled:
        companion = {
            "image": config.companion.image or "deskclaw-companion:latest",
            "container_name": f"{config.slug}-companion",
            "environment": config.companion.env_vars,
            "ports": [str(config.companion.port)],
            "restart": "unless-stopped",
            "platform": "linux/amd64",
            "depends_on": ["agent"],
            "networks": [f"{config.slug}-net"],
            "extra_hosts": ["host.docker.internal:host-gateway"],
        }
        return {
            "services": {"agent": main_service, "companion": companion},
            "networks": {f"{config.slug}-net": {"driver": "bridge"}},
        }

    return {
        "services": {"agent": main_service},
        "networks": {f"{config.slug}-net": {"driver": "bridge"}},
    }


class DockerComputeProvider:
    """Docker compose-based compute provider for local/dev agent instances."""

    provider_id = "docker"

    async def create_instance(
        self, config: InstanceComputeConfig, **kwargs,
    ) -> ComputeHandle:
        logger.info("DockerComputeProvider.create_instance: %s (slug=%s)", config.instance_id, config.slug)

        project_dir = str(DOCKER_DATA_DIR / config.slug)
        os.makedirs(project_dir, exist_ok=True)
        data_dir = DOCKER_DATA_DIR / config.slug / "data"
        os.makedirs(str(data_dir), exist_ok=True)

        compose = _build_compose_yaml(config)
        compose_path = _compose_path_for_slug(config.slug)

        try:
            import yaml
            with open(compose_path, "w") as f:
                yaml.dump(compose, f, default_flow_style=False)
        except ImportError:
            with open(compose_path, "w") as f:
                json.dump(compose, f, indent=2)

        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "compose", "-f", compose_path, "up", "-d",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raw = stderr.decode()
                logger.error("docker compose up failed: %s", raw)
                raise RuntimeError(f"docker compose up 失败: {_extract_docker_error(raw)}")
        except FileNotFoundError:
            raise RuntimeError("docker compose 未安装")

        host_port = config.env_vars.get("DOCKER_HOST_PORT", "3000")
        host = _docker_endpoint_host()
        return ComputeHandle(
            provider=self.provider_id,
            instance_id=config.instance_id,
            namespace=config.namespace,
            endpoint=f"http://{host}:{host_port}",
            status="running",
            extra={"compose_path": compose_path, "slug": config.slug, "runtime": config.runtime},
        )

    async def destroy_instance(self, handle: ComputeHandle, **kwargs) -> None:
        logger.info("DockerComputeProvider.destroy_instance: %s", handle.instance_id)
        slug = handle.extra.get("slug", handle.instance_id)
        compose_path = _resolve_compose_path(slug, handle.extra.get("compose_path", ""))
        if compose_path and os.path.exists(compose_path):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "docker", "compose", "-f", compose_path, "down", "-v",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await proc.communicate()
                if proc.returncode == 0:
                    return
                logger.warning("docker compose down failed: %s", stderr.decode().strip()[:300])
            except Exception as e:
                logger.warning("docker compose down failed: %s", e)

        for container_name in (f"{slug}-companion", slug):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "docker", "rm", "-f", container_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await proc.communicate()
                if proc.returncode != 0 and "No such container" not in stderr.decode():
                    logger.warning("docker rm failed for %s: %s", container_name, stderr.decode().strip()[:300])
            except Exception as e:
                logger.warning("docker rm failed for %s: %s", container_name, e)

        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "network", "rm", f"{slug}-net",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0 and "No such network" not in stderr.decode():
                logger.warning("docker network rm failed for %s-net: %s", slug, stderr.decode().strip()[:300])
        except Exception as e:
            logger.warning("docker network rm failed for %s-net: %s", slug, e)

    async def get_status(self, handle: ComputeHandle) -> str:
        slug = handle.extra.get("slug", handle.instance_id)
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "inspect", "--format", "{{.State.Status}}", slug,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                status = stdout.decode().strip()
                status_map = {"running": "running", "exited": "stopped", "paused": "stopped"}
                return status_map.get(status, status)
        except Exception:
            pass
        return "unknown"

    async def get_endpoint(self, handle: ComputeHandle) -> str:
        return handle.endpoint

    async def get_logs(self, handle: ComputeHandle, *, tail: int = 50) -> str:
        slug = handle.extra.get("slug", handle.instance_id)
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "logs", "--tail", str(tail), slug,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await proc.communicate()
            return stdout.decode() if stdout else ""
        except Exception:
            return ""

    async def update_instance(
        self, handle: ComputeHandle, config: InstanceComputeConfig,
    ) -> ComputeHandle:
        logger.info("DockerComputeProvider.update_instance: %s", handle.instance_id)
        await self.destroy_instance(handle)
        return await self.create_instance(config)

    async def restart_instance(self, handle: ComputeHandle) -> None:
        slug = handle.extra.get("slug", handle.instance_id)
        compose_path = _resolve_compose_path(slug, handle.extra.get("compose_path", ""))
        if compose_path and os.path.exists(compose_path):
            proc = await asyncio.create_subprocess_exec(
                "docker", "compose", "-f", compose_path, "restart",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"docker compose restart 失败: {_extract_docker_error(stderr.decode())}")
        else:
            proc = await asyncio.create_subprocess_exec(
                "docker", "restart", slug,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"docker restart 失败: {_extract_docker_error(stderr.decode())}")

    async def scale_instance(self, handle: ComputeHandle, replicas: int) -> ComputeHandle:
        slug = handle.extra.get("slug", handle.instance_id)
        compose_path = _resolve_compose_path(slug, handle.extra.get("compose_path", ""))
        if compose_path and os.path.exists(compose_path):
            proc = await asyncio.create_subprocess_exec(
                "docker", "compose", "-f", compose_path, "up", "-d",
                "--scale", f"agent={replicas}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"docker compose scale 失败: {_extract_docker_error(stderr.decode())}")
        handle.extra["replicas"] = replicas
        return handle

    async def health_check(self, handle: ComputeHandle) -> dict:
        try:
            status = await self.get_status(handle)
        except Exception as e:
            return {"healthy": False, "detail": f"docker inspect failed: {e}"}
        if status != "running":
            return {"healthy": False, "detail": f"container {status}"}

        runtime = (handle.extra or {}).get("runtime", "openclaw")
        from app.services.runtime.registries.runtime_registry import RUNTIME_REGISTRY
        rt_spec = RUNTIME_REGISTRY.get(runtime)
        probe_path = rt_spec.health_probe_path if rt_spec else "/"

        if probe_path is None:
            return {"healthy": True, "detail": "container running (no http probe)"}

        from app.services.runtime.compute.base import http_probe
        endpoint = handle.endpoint
        if endpoint:
            host = _docker_endpoint_host()
            if host != "localhost":
                endpoint = endpoint.replace("localhost", host).replace("127.0.0.1", host)
        return await http_probe(endpoint, path=probe_path)
