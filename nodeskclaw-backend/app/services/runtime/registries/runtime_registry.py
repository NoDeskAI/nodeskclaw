"""RuntimeRegistry — maps runtime identifiers to RuntimeAdapter factories."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimeProductCapabilities:
    """Product-facing runtime capabilities consumed by APIs and frontend UI."""

    genes: bool
    evolution_log: bool
    llm_config: bool
    channel_config: bool
    channel_plugin_discovery: bool
    repo_channel_sync: bool
    npm_channel_install: bool
    upload_channel_plugin: bool
    gateway: bool
    health_endpoint: bool
    config_endpoint: bool
    web_ui: bool
    backup: bool
    runtime_config_patch: bool
    tool_allow: bool

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


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
    capabilities: RuntimeProductCapabilities | None = None
    gateway_port: int | None = None
    health_probe_path: str | None = None
    readiness_probe_path: str | None = None
    order: int = 0
    image_registry_key: str = "image_registry"
    config_rel_path: str = ""
    config_format: str = ""
    channels_section_key: str = ""
    field_naming: str = ""
    supports_channel_plugins: bool = False
    data_dir_container_path: str = ""
    skills_dir_rel: str = ""
    scripts_dir_rel: str = ""
    has_web_ui: bool = False
    has_init_script: bool = False
    available: bool = True
    backup_dirs: tuple[str, ...] = ()
    backup_exclude_patterns: tuple[str, ...] = (
        "node_modules", "dist", "__pycache__", ".git", "cache", "*.pyc",
    )

    def capability_map(self) -> dict[str, bool]:
        if self.capabilities is None:
            raise RuntimeError(f"Runtime {self.runtime_id} missing product capabilities")
        return self.capabilities.to_dict()


class RuntimeRegistry:
    def __init__(self) -> None:
        self._runtimes: dict[str, RuntimeSpec] = {}

    def register(self, spec: RuntimeSpec) -> None:
        _validate_runtime_spec(spec)
        self._runtimes[spec.runtime_id] = spec
        logger.debug("Registered runtime: %s", spec.runtime_id)

    def get(self, runtime_id: str) -> RuntimeSpec | None:
        return self._runtimes.get(runtime_id)

    def all_runtimes(self) -> list[RuntimeSpec]:
        return list(self._runtimes.values())


RUNTIME_REGISTRY = RuntimeRegistry()


def runtime_supports_capability(runtime_id: str | None, capability: str) -> bool:
    runtime = runtime_id or "openclaw"
    spec = RUNTIME_REGISTRY.get(runtime)
    if spec is None:
        return False
    return spec.capability_map().get(capability, False)


def _validate_runtime_spec(spec: RuntimeSpec) -> None:
    required_string_fields = (
        "config_rel_path",
        "config_format",
        "channels_section_key",
        "field_naming",
        "data_dir_container_path",
        "skills_dir_rel",
        "scripts_dir_rel",
    )
    missing = [name for name in required_string_fields if not getattr(spec, name)]
    if spec.gateway_port is None:
        missing.append("gateway_port")
    if spec.capabilities is None:
        missing.append("capabilities")
    if not spec.backup_dirs:
        missing.append("backup_dirs")
    if missing:
        raise RuntimeError(
            f"Runtime {spec.runtime_id} missing required RuntimeSpec fields: {', '.join(missing)}"
        )


def _register_builtins() -> None:
    from app.services.runtime.hermes_gene_install_adapter import HermesGeneInstallAdapter
    from app.services.runtime.openclaw_gene_install_adapter import OpenClawGeneInstallAdapter

    _openclaw_gene_adapter = OpenClawGeneInstallAdapter(
        config_rel_path=".openclaw/openclaw.json",
        skills_dir_rel=".openclaw/skills",
        skills_extra_dir="/root/.openclaw/skills",
        scripts_dir_rel=".deskclaw/tools",
    )
    _hermes_gene_adapter = HermesGeneInstallAdapter()

    RUNTIME_REGISTRY.register(RuntimeSpec(
        runtime_id="openclaw",
        adapter=None,
        gene_install_adapter=_openclaw_gene_adapter,
        description="OpenClaw runtime -- primary DeskClaw agent kernel.",
        requires_companion=False,
        display_name="全能员工引擎",
        display_description="支持工具调用、基因系统、多技能管理",
        display_tags=("默认",),
        display_powered_by="OpenClaw",
        capabilities=RuntimeProductCapabilities(
            genes=True,
            evolution_log=True,
            llm_config=True,
            channel_config=True,
            channel_plugin_discovery=True,
            repo_channel_sync=True,
            npm_channel_install=True,
            upload_channel_plugin=True,
            gateway=True,
            health_endpoint=True,
            config_endpoint=True,
            web_ui=True,
            backup=True,
            runtime_config_patch=True,
            tool_allow=True,
        ),
        gateway_port=18789,
        health_probe_path="/healthz",
        readiness_probe_path="/readyz",
        order=0,
        config_rel_path=".openclaw/openclaw.json",
        config_format="json",
        channels_section_key="channels",
        field_naming="camelCase",
        supports_channel_plugins=True,
        data_dir_container_path="/root/.openclaw",
        skills_dir_rel=".openclaw/skills",
        scripts_dir_rel=".deskclaw/tools",
        has_web_ui=True,
        has_init_script=True,
        backup_dirs=(".openclaw", ".deskclaw/tools"),
    ))
    RUNTIME_REGISTRY.register(RuntimeSpec(
        runtime_id="hermes",
        adapter=None,
        gene_install_adapter=_hermes_gene_adapter,
        description="Hermes runtime -- general-purpose long-running agent.",
        requires_companion=False,
        display_name="自进化员工引擎",
        display_description="面向长期运行 Agent 的通用执行引擎",
        display_tags=("实验",),
        display_powered_by="Hermes Agent",
        capabilities=RuntimeProductCapabilities(
            genes=True,
            evolution_log=False,
            llm_config=True,
            channel_config=True,
            channel_plugin_discovery=False,
            repo_channel_sync=False,
            npm_channel_install=False,
            upload_channel_plugin=False,
            gateway=True,
            health_endpoint=True,
            config_endpoint=True,
            web_ui=False,
            backup=True,
            runtime_config_patch=False,
            tool_allow=False,
        ),
        gateway_port=8642,
        health_probe_path="/health",
        order=1,
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
