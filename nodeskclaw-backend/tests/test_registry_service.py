from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import registry_service


def _config_reader(values: dict[str, str | None]):
    async def read(key, _db):
        return values.get(key)

    return read


@pytest.mark.asyncio
async def test_resolve_registry_config_uses_hosted_repository_and_credentials(monkeypatch):
    monkeypatch.setattr(
        registry_service,
        "get_config",
        _config_reader({
            "registry_mode": "hosted",
            "hosted_registry_url": "https://registry.example.com/deskclaw/",
            "hosted_registry_username": "registry-admin",
            "hosted_registry_password": "secret",
        }),
    )

    config = await registry_service.resolve_registry_config(object(), "openclaw")

    assert config.mode == "hosted"
    assert config.image_registry == "registry.example.com/deskclaw/deskclaw-openclaw"
    assert config.credentials == ("registry-admin", "secret")


@pytest.mark.asyncio
async def test_resolve_registry_config_keeps_custom_per_runtime_repository(monkeypatch):
    monkeypatch.setattr(
        registry_service,
        "get_config",
        _config_reader({
            "registry_mode": "custom",
            "image_registry": "registry.example.com/team/openclaw",
            "registry_username": "custom-user",
            "registry_password": "custom-secret",
        }),
    )

    config = await registry_service.resolve_registry_config(object(), "openclaw")

    assert config.mode == "custom"
    assert config.image_registry == "registry.example.com/team/openclaw"
    assert config.credentials == ("custom-user", "custom-secret")


@pytest.mark.asyncio
async def test_ensure_registry_pull_secret_uses_resolved_credentials():
    create_secret = AsyncMock()
    k8s = SimpleNamespace(
        core=SimpleNamespace(create_namespaced_secret=create_secret),
        create_or_skip=AsyncMock(),
    )
    config = registry_service.ResolvedRegistryConfig(
        mode="hosted",
        image_registry="registry.example.com/deskclaw/deskclaw-openclaw",
        username="registry-admin",
        password="secret",
    )

    secret_name = await registry_service.ensure_registry_pull_secret(k8s, "workspace-1", config)

    assert secret_name == "nodeskclaw-registry"
    args = k8s.create_or_skip.await_args.args
    assert args[0] is create_secret
    assert args[1] == "workspace-1"
    secret = args[2]
    assert secret.metadata.namespace == "workspace-1"
    assert secret.metadata.name == "nodeskclaw-registry"


def test_normalize_registry_repository_removes_protocol_and_slashes():
    assert (
        registry_service.normalize_registry_repository("https://registry.example.com/team/openclaw/")
        == "registry.example.com/team/openclaw"
    )
