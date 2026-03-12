"""RuntimeRegistry — maps runtime identifiers to RuntimeAdapter factories."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimeSpec:
    runtime_id: str
    adapter: Any = None
    description: str | None = None
    requires_companion: bool = False
    config_schema: dict | None = None
    display_name: str = ""
    display_description: str = ""
    display_tags: tuple[str, ...] = ()
    display_powered_by: str = ""
    order: int = 0


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
    from app.services.runtime.adapters.nanobot import NanobotRuntimeAdapter
    from app.services.runtime.adapters.openclaw import OpenClawRuntimeAdapter
    from app.services.runtime.adapters.zeroclaw import ZeroClawRuntimeAdapter

    RUNTIME_REGISTRY.register(RuntimeSpec(
        runtime_id="openclaw",
        adapter=OpenClawRuntimeAdapter(),
        description="OpenClaw runtime -- primary DeskClaw agent kernel.",
        requires_companion=False,
        display_name="全能工作引擎",
        display_description="支持工具调用、基因系统、多技能管理",
        display_tags=("默认",),
        display_powered_by="OpenClaw",
        order=0,
    ))
    RUNTIME_REGISTRY.register(RuntimeSpec(
        runtime_id="zeroclaw",
        adapter=ZeroClawRuntimeAdapter(),
        description="ZeroClaw runtime -- high-performance Rust-based agent kernel.",
        requires_companion=False,
        display_name="高性能工作引擎",
        display_description="Rust 构建，极速响应，适合高并发场景",
        display_tags=(),
        display_powered_by="ZeroClaw",
        order=1,
    ))
    RUNTIME_REGISTRY.register(RuntimeSpec(
        runtime_id="nanobot",
        adapter=NanobotRuntimeAdapter(),
        description="Nanobot runtime -- ultra-lightweight Python-based agent.",
        requires_companion=False,
        display_name="轻量工作引擎",
        display_description="超轻量，快速部署，适合简单对话场景",
        display_tags=(),
        display_powered_by="Nanobot",
        order=2,
    ))


_register_builtins()
