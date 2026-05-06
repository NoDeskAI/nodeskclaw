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
    available: bool = True
    docker_command: tuple[str, ...] | None = None
    docker_seed_template_rel: str | None = None
    backup_dirs: tuple[str, ...] = ()
    backup_exclude_patterns: tuple[str, ...] = (
        "node_modules", "dist", "__pycache__", ".git", "cache", "*.pyc",
    )


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
        docker_seed_template_rel="openclaw.json.template",
        backup_dirs=(".openclaw", ".deskclaw/tools"),
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
        available=False,
        backup_dirs=(".nanobot", ".deskclaw/skills"),
    ))
    RUNTIME_REGISTRY.register(RuntimeSpec(
        runtime_id="hermes",
        adapter=None,
        gene_install_adapter=_noop_gene_adapter,
        description="Hermes runtime -- general-purpose long-running agent.",
        requires_companion=False,
        display_name="Hermes 员工引擎",
        display_description="面向长期运行 Agent 的通用执行引擎",
        display_tags=("实验",),
        display_powered_by="Hermes Agent",
        gateway_port=8642,
        health_probe_path="/health",
        order=3,
        image_registry_key="image_registry_hermes",
        config_rel_path=".hermes/config.yaml",
        config_format="yaml",
        channels_section_key="platforms",
        field_naming="camelCase",
        supports_channel_plugins=False,
        data_dir_container_path="/root/.hermes",
        skills_dir_rel=".hermes/skills",
        scripts_dir_rel=".hermes/scripts",
        has_web_ui=False,
        has_init_script=False,
        available=True,
        backup_dirs=(".hermes",),
    ))


_register_builtins()
