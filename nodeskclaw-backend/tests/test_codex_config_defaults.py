from types import SimpleNamespace

from app.services.codex_provider import normalize_selected_models
from app.services.llm_config_service import (
    _build_providers_config,
    _ensure_gateway_config,
)
from app.services.runtime.platform_endpoint_resolver import PlatformEndpoints


def _endpoints(url: str) -> PlatformEndpoints:
    return PlatformEndpoints(
        llm_proxy_base_url=url,
        agent_api_base_url="http://backend:4510/api/v1",
    )


def test_normalize_selected_models_sets_codex_default():
    selected_models = normalize_selected_models("codex", None)

    assert selected_models == [{"id": "gpt-5.4", "name": "gpt-5.4"}]


def test_build_providers_config_sets_codex_models():
    providers = _build_providers_config(
        [SimpleNamespace(provider="codex", key_source="personal", selected_models=None)],
        "proxy-token",
        {},
        platform_endpoints=_endpoints("http://llm-proxy:18080"),
    )

    assert providers["codex"]["models"] == [{"id": "gpt-5.4", "name": "gpt-5.4"}]


def test_ensure_gateway_config_sets_local_mode():
    config = {}

    _ensure_gateway_config(config, SimpleNamespace(proxy_token="test-token"))

    assert config["gateway"]["auth"]["token"] == "test-token"
    assert config["gateway"]["auth"]["rateLimit"] == {
        "maxAttempts": 10,
        "windowMs": 60000,
        "lockoutMs": 300000,
    }
    assert config["gateway"]["controlUi"]["dangerouslyDisableDeviceAuth"] is True

