"""Provider adapters for Agent Device invocation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.core.config import settings
from app.core.exceptions import BadRequestError
from app.models.agent_device import AgentDeviceInstance, AgentDeviceLease


@dataclass(frozen=True)
class AgentDevicePreset:
    preset_id: str
    provider_id: str
    display_name: str
    description: str
    gene_slug: str
    capability_schema: dict[str, Any] = field(default_factory=dict)
    default_config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderStatus:
    status: str
    reason: str | None = None


class AgentDeviceProvider(Protocol):
    provider_id: str

    def status(self) -> ProviderStatus:
        ...

    async def invoke(
        self,
        *,
        device: AgentDeviceInstance,
        actor_agent_id: str,
        lease: AgentDeviceLease,
        action: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class BpilotProvider:
    provider_id = "browser.bpilot"

    def status(self) -> ProviderStatus:
        if not settings.BPILOT_BASE_URL:
            return ProviderStatus(status="provider_unconfigured", reason="bpilot_base_url_missing")
        return ProviderStatus(status="available")

    async def invoke(
        self,
        *,
        device: AgentDeviceInstance,
        actor_agent_id: str,
        lease: AgentDeviceLease,
        action: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        provider_status = self.status()
        if provider_status.status != "available":
            raise BadRequestError(
                "Browser Pilot provider 未配置，请先设置 BPILOT_BASE_URL",
                "errors.agent_device.provider_unconfigured",
            )

        headers: dict[str, str] = {}
        if settings.BPILOT_API_KEY:
            headers["Authorization"] = f"Bearer {settings.BPILOT_API_KEY}"

        body = {
            "device_id": device.id,
            "workspace_id": device.workspace_id,
            "actor_agent_id": actor_agent_id,
            "lease_id": lease.id,
            "action": action,
            "payload": payload,
            "config": device.config or {},
        }
        url = f"{settings.BPILOT_BASE_URL.rstrip('/')}/agent-devices/invoke"
        timeout = httpx.Timeout(settings.BPILOT_TIMEOUT_SECONDS, connect=10)
        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            response = await client.post(url, json=body)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {"result": data}


BUILTIN_AGENT_DEVICE_PRESETS: dict[str, AgentDevicePreset] = {
    "browser.bpilot.session": AgentDevicePreset(
        preset_id="browser.bpilot.session",
        provider_id="browser.bpilot",
        display_name="Browser Pilot",
        description="Browser Pilot controlled browser session exposed as an Agent Device.",
        gene_slug="agent-device-browser-bpilot",
        capability_schema={
            "actions": ["session.create", "session.use", "page.goto", "page.observe", "page.click", "page.type"],
            "lease_mode": "exclusive",
        },
        default_config={},
    ),
}


PROVIDERS: dict[str, AgentDeviceProvider] = {
    BpilotProvider.provider_id: BpilotProvider(),
}


def get_agent_device_preset(preset_id: str) -> AgentDevicePreset | None:
    return BUILTIN_AGENT_DEVICE_PRESETS.get(preset_id)


def list_agent_device_presets() -> list[AgentDevicePreset]:
    return list(BUILTIN_AGENT_DEVICE_PRESETS.values())


def get_agent_device_provider(provider_id: str) -> AgentDeviceProvider | None:
    return PROVIDERS.get(provider_id)
