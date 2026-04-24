from types import SimpleNamespace

from app.core.config import settings
from app.services.codex_provider import normalize_selected_models
from app.services.llm_config_service import (
    _build_providers_config,
    _docker_rewrite_urls,
    _ensure_gateway_config,
)


def test_normalize_selected_models_sets_codex_default():
    selected_models = normalize_selected_models("codex", None)

    assert selected_models == [{"id": "gpt-5.4", "name": "gpt-5.4"}]


def test_build_providers_config_sets_codex_models(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROXY_INTERNAL_URL", "http://llm-proxy:18080")
    monkeypatch.setattr(settings, "LLM_PROXY_URL", "http://llm-proxy:18080")

    providers = _build_providers_config(
        [SimpleNamespace(provider="codex", key_source="personal", selected_models=None)],
        "proxy-token",
        {},
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


def test_docker_rewrite_urls_uses_external_proxy_url(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROXY_INTERNAL_URL", "http://llm-proxy:8080")
    monkeypatch.setattr(settings, "LLM_PROXY_URL", "http://localhost:18080")

    providers = {
        "codex": {
            "baseUrl": "http://llm-proxy:8080/codex/v1",
            "apiKey": "proxy-token",
        }
    }

    rewritten = _docker_rewrite_urls(providers)

    assert rewritten["codex"]["baseUrl"] == "http://host.docker.internal:18080/codex/v1"


def test_docker_rewrite_urls_custom_provider(monkeypatch):
    """Custom providers (e.g. Ollama) routed through proxy should also be
    rewritten to host.docker.internal so standalone instance containers can
    reach the proxy. Regression test for #228."""
    monkeypatch.setattr(settings, "LLM_PROXY_INTERNAL_URL", "http://llm-proxy:8080")
    monkeypatch.setattr(settings, "LLM_PROXY_URL", "http://localhost:4511")

    providers = {
        "ollama": {
            "baseUrl": "http://llm-proxy:8080/ollama/v1",
            "apiKey": "wp-token",
            "api": "openai-completions",
            "models": [{"id": "qwen3.6:35b", "name": "qwen3.6:35b"}],
        }
    }

    rewritten = _docker_rewrite_urls(providers)

    assert rewritten["ollama"]["baseUrl"] == "http://host.docker.internal:4511/ollama/v1"
