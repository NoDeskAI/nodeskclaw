"""RuntimeRegistry — maps runtime identifiers to RuntimeAdapter factories."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimeSpec:
    runtime_id: str
    adapter: Any = None
    gene_install_adapter: Any = None
    description: str | None = None
    requires_companion: bool = False
    config_schema: dict | None = None
    display_name: str = ""
    display_description: str = ""
    display_tags: tuple[str, ...] = ()
    display_powered_by: str = ""
    gateway_port: int = 18789
    health_probe_path: str | None = "/healthz"
    readiness_probe_path: str | None = None
    order: int = 0
    image_registry_key: str = "image_registry"
    config_rel_path: str = ".openclaw/openclaw.json"
    config_format: str = "json"
    channels_section_key: str = "channels"
    field_naming: str = "camelCase"
    supports_channel_plugins: bool = True
    data_dir_container_path: str = "/root/.openclaw"
    skills_dir_rel: str = ".openclaw/skills"
    scripts_dir_rel: str = ".deskclaw/tools"
    has_web_ui: bool = True
    has_init_script: bool = True
    docker_command: tuple[str, ...] | None = None


class RuntimeRegistry:
    def __init__(self) -> None:
        self._runtimes: dict[str, RuntimeSpec] = {}

    def register(self, spec: RuntimeSpec) -> None:
        self._runtimes[spec.runtime_id] = spec
        logger.debug("Registered runtime: %s", spec.runtime_id)

    def get(self, runtime_id: str) -> RuntimeSpec | None:
        return self._runtimes.get(runtime_id)

    def all_runtimes(self) -> list[RuntimeSpec]:
        return list(self._runtimes.values())


RUNTIME_REGISTRY = RuntimeRegistry()


def _register_builtins() -> None:
    from app.services.runtime.noop_gene_install_adapter import NoopGeneInstallAdapter
    from app.services.runtime.openclaw_gene_install_adapter import OpenClawGeneInstallAdapter

    _openclaw_gene_adapter = OpenClawGeneInstallAdapter(
        config_rel_path=".openclaw/openclaw.json",
        skills_dir_rel=".openclaw/skills",
        skills_extra_dir="/root/.openclaw/skills",
        scripts_dir_rel=".deskclaw/tools",
    )
    _noop_gene_adapter = NoopGeneInstallAdapter()

    RUNTIME_REGISTRY.register(RuntimeSpec(
        runtime_id="openclaw",
        adapter=None,
        gene_install_adapter=_openclaw_gene_adapter,
        description="OpenClaw runtime -- primary DeskClaw agent kernel.",
        requires_companion=False,
        display_name="全能工作引擎",
        display_description="支持工具调用、基因系统、多技能管理",
        display_tags=("默认",),
        display_powered_by="OpenClaw",
        readiness_probe_path="/readyz",
        order=0,
    ))
    RUNTIME_REGISTRY.register(RuntimeSpec(
        runtime_id="zeroclaw",
        adapter=None,
        gene_install_adapter=_noop_gene_adapter,
        description="ZeroClaw runtime -- high-performance Rust-based agent kernel.",
        requires_companion=False,
        display_name="高性能工作引擎",
        display_description="Rust 构建，极速响应，适合高并发场景",
        display_tags=(),
        display_powered_by="ZeroClaw",
        gateway_port=8080,
        health_probe_path="/health",
        docker_command=("zeroclaw", "gateway", "start", "-p", "8080", "--host", "0.0.0.0"),
        order=1,
        image_registry_key="image_registry_zeroclaw",
        config_rel_path=".zeroclaw/config.toml",
        config_format="toml",
        channels_section_key="channels_config",
        field_naming="snake_case",
        supports_channel_plugins=False,
        data_dir_container_path="/root/.zeroclaw",
        skills_dir_rel=".deskclaw/skills",
        has_web_ui=False,
        has_init_script=False,
    ))
    RUNTIME_REGISTRY.register(RuntimeSpec(
        runtime_id="nanobot",
        adapter=None,
        gene_install_adapter=_noop_gene_adapter,
        description="Nanobot runtime -- ultra-lightweight Python-based agent.",
        requires_companion=False,
        display_name="轻量工作引擎",
        display_description="超轻量，快速部署，适合简单对话场景",
        display_tags=(),
        display_powered_by="Nanobot",
        gateway_port=18790,
        health_probe_path=None,
        order=2,
        image_registry_key="image_registry_nanobot",
        config_rel_path=".nanobot/config.json",
        config_format="json",
        channels_section_key="channels",
        field_naming="camelCase",
        supports_channel_plugins=False,
        data_dir_container_path="/root/.nanobot",
        skills_dir_rel=".deskclaw/skills",
        has_web_ui=False,
        has_init_script=False,
    ))


_register_builtins()
