from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest

from app.api import settings as settings_api
from app.core.exceptions import BadRequestError


def _user():
    return SimpleNamespace(id="user-1", current_org_id="org-1")


@pytest.mark.asyncio
async def test_registry_mode_rejects_unknown_value():
    with pytest.raises(BadRequestError) as exc_info:
        await settings_api.update_setting(
            "registry_mode",
            settings_api.ConfigUpdateBody(value="docker"),
            object(),
            _user(),
        )

    assert exc_info.value.message_key == "errors.settings.invalid_registry_mode"


@pytest.mark.asyncio
async def test_hosted_registry_mode_requires_complete_configuration(monkeypatch):
    monkeypatch.setattr(
        settings_api.config_service,
        "get_config",
        AsyncMock(side_effect=["registry.example.com/deskclaw", "registry-admin", None]),
    )

    with pytest.raises(BadRequestError) as exc_info:
        await settings_api.update_setting(
            "registry_mode",
            settings_api.ConfigUpdateBody(value="hosted"),
            object(),
            _user(),
        )

    assert exc_info.value.message_key == "errors.settings.hosted_registry_incomplete"


@pytest.mark.asyncio
async def test_hosted_registry_mode_saves_when_configuration_is_complete(monkeypatch):
    monkeypatch.setattr(
        settings_api.config_service,
        "get_config",
        AsyncMock(side_effect=["registry.example.com/deskclaw", "registry-admin", "secret"]),
    )
    set_config = AsyncMock(
        return_value=SimpleNamespace(key="registry_mode", value="hosted"),
    )
    monkeypatch.setattr(settings_api.config_service, "set_config", set_config)
    monkeypatch.setattr(settings_api.hooks, "emit", AsyncMock())

    response = await settings_api.update_setting(
        "registry_mode",
        settings_api.ConfigUpdateBody(value="HOSTED"),
        object(),
        _user(),
    )

    set_config.assert_awaited_once_with("registry_mode", "hosted", ANY)
    assert response.data == {"key": "registry_mode", "value": "hosted"}


@pytest.mark.asyncio
async def test_registry_url_is_normalized_before_saving(monkeypatch):
    set_config = AsyncMock(
        return_value=SimpleNamespace(
            key="image_registry",
            value="registry.example.com/team/openclaw",
        ),
    )
    monkeypatch.setattr(settings_api.config_service, "set_config", set_config)
    monkeypatch.setattr(settings_api.hooks, "emit", AsyncMock())

    response = await settings_api.update_setting(
        "image_registry",
        settings_api.ConfigUpdateBody(
            value="https://registry.example.com/team/openclaw/",
        ),
        object(),
        _user(),
    )

    set_config.assert_awaited_once_with(
        "image_registry",
        "registry.example.com/team/openclaw",
        ANY,
    )
    assert response.data["value"] == "registry.example.com/team/openclaw"
