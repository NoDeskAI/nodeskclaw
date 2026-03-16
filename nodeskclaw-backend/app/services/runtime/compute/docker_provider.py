"""DockerComputeProvider — manages agent instances as Docker Compose services."""

from __future__ import annotations

import asyncio
import json
import logging
import os

from app.services.docker_constants import DOCKER_DATA_DIR
from app.services.runtime.compute.base import (
    ComputeHandle,
    InstanceComputeConfig,
)

logger = logging.getLogger(__name__)


def _parse_cpu(cpu_str: str) -> float:
    """Convert K8s-style cpu (e.g. '2000m', '2') to Docker cpus float."""
    s = cpu_str.strip().lower()
    if s.endswith("m"):
        return int(s[:-1]) / 1000
    return float(s)


def _parse_mem(mem_str: str) -> str:
    """Convert K8s-style memory (e.g. '2Gi', '512Mi') to Docker format ('2g', '512m')."""
    s = mem_str.strip()
    lower = s.lower()
    if lower.endswith("gi"):
        return s[:-2] + "g"
    if lower.endswith("mi"):
        return s[:-2] + "m"
    if lower.endswith("ki"):
        return s[:-2] + "k"
    return s


def _build_compose_yaml(config: InstanceComputeConfig) -> dict:
    """Generate a docker-compose service definition with full resource config."""
    host_port = config.env_vars.get("DOCKER_HOST_PORT", "3000")

    main_service: dict = {
        "image": config.env_vars.get("DOCKER_IMAGE", f"deskclaw:{config.image_version}"),
        "container_name": config.slug,
        "environment": {k: str(v) for k, v in config.env_vars.items()},
        "ports": [f"{host_port}:3000"],
        "volumes": [f"{DOCKER_DATA_DIR / config.slug / 'data'}:/root/.openclaw"],
        "restart": "unless-stopped",
        "platform": "linux/amd64",
        "networks": [f"{config.slug}-net"],
    }

    if config.mem_limit:
        main_service["mem_limit"] = _parse_mem(config.mem_limit)
    if config.cpu_limit:
        try:
            main_service["cpus"] = _parse_cpu(config.cpu_limit)
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
        compose_path = os.path.join(project_dir, "docker-compose.yml")

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
                error_msg = stderr.decode()[:500]
                logger.error("docker compose up failed: %s", error_msg)
                raise RuntimeError(f"docker compose up 失败: {error_msg}")
        except FileNotFoundError:
            raise RuntimeError("docker compose 未安装")

        host_port = config.env_vars.get("DOCKER_HOST_PORT", "3000")
        return ComputeHandle(
            provider=self.provider_id,
            instance_id=config.instance_id,
            namespace=config.namespace,
            endpoint=f"http://localhost:{host_port}",
            status="running",
            extra={"compose_path": compose_path, "slug": config.slug},
        )

    async def destroy_instance(self, handle: ComputeHandle, **kwargs) -> None:
        logger.info("DockerComputeProvider.destroy_instance: %s", handle.instance_id)
        compose_path = handle.extra.get("compose_path", "")
        if compose_path and os.path.exists(compose_path):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "docker", "compose", "-f", compose_path, "down", "-v",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
            except Exception as e:
                logger.warning("docker compose down failed: %s", e)

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
        compose_path = handle.extra.get("compose_path", "")
        if compose_path and os.path.exists(compose_path):
            proc = await asyncio.create_subprocess_exec(
                "docker", "compose", "-f", compose_path, "restart",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"docker compose restart 失败: {stderr.decode()[:300]}")
        else:
            slug = handle.extra.get("slug", handle.instance_id)
            proc = await asyncio.create_subprocess_exec(
                "docker", "restart", slug,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"docker restart 失败: {stderr.decode()[:300]}")

    async def scale_instance(self, handle: ComputeHandle, replicas: int) -> ComputeHandle:
        compose_path = handle.extra.get("compose_path", "")
        if compose_path and os.path.exists(compose_path):
            proc = await asyncio.create_subprocess_exec(
                "docker", "compose", "-f", compose_path, "up", "-d",
                "--scale", f"agent={replicas}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"docker compose scale 失败: {stderr.decode()[:300]}")
        handle.extra["replicas"] = replicas
        return handle
