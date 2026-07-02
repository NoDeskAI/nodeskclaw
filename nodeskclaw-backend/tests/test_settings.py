from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services.runtime.platform_endpoint_resolver import (
    PlatformEndpointConfigError,
    resolve_platform_endpoints,
)


def _settings(
    *,
    llm_proxy_url: str = "",
    llm_proxy_internal_url: str = "",
    agent_api_base_url: str = "https://nodeskclaw.example.com/api/v1",
    tunnel_base_url: str = "",
) -> SimpleNamespace:
    return SimpleNamespace(
        LLM_PROXY_URL=llm_proxy_url,
        LLM_PROXY_INTERNAL_URL=llm_proxy_internal_url,
        AGENT_API_BASE_URL=agent_api_base_url,
        TUNNEL_BASE_URL=tunnel_base_url,
    )


def test_settings_qualifies_k8s_llm_proxy_service_url() -> None:
    settings = Settings(
        DEBUG=True,
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/nodeskclaw_test",
        LLM_PROXY_INTERNAL_URL="http://nodeskclaw-llm-proxy:80",
        PLATFORM_NAMESPACE="nodeskclaw-system",
    )

    assert (
        settings.LLM_PROXY_INTERNAL_URL
        == "http://nodeskclaw-llm-proxy.nodeskclaw-system.svc.cluster.local:80"
    )


def test_settings_keeps_non_k8s_llm_proxy_service_url() -> None:
    settings = Settings(
        DEBUG=True,
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/nodeskclaw_test",
        LLM_PROXY_INTERNAL_URL="http://llm-proxy:8080",
        PLATFORM_NAMESPACE="nodeskclaw-system",
    )

    assert settings.LLM_PROXY_INTERNAL_URL == "http://llm-proxy:8080"


def test_resolve_process_keeps_localhost() -> None:
    endpoints = resolve_platform_endpoints(
        compute_provider="process",
        runtime="openclaw",
        instance_namespace=None,
        cluster_proxy_endpoint=None,
        platform_namespace="nodeskclaw-system",
        settings=_settings(
            llm_proxy_url="http://localhost:4511",
            agent_api_base_url="http://localhost:4510/api/v1",
        ),
    )

    assert endpoints.llm_proxy_base_url == "http://localhost:4511"
    assert endpoints.agent_api_base_url == "http://localhost:4510/api/v1"


def test_resolve_same_cluster_k8s_service_to_fqdn() -> None:
    endpoints = resolve_platform_endpoints(
        compute_provider="k8s",
        runtime="openclaw",
        instance_namespace="agent-ns",
        cluster_proxy_endpoint=None,
        platform_namespace="nodeskclaw-system",
        settings=_settings(llm_proxy_internal_url="http://nodeskclaw-llm-proxy:80"),
    )

    assert (
        endpoints.llm_proxy_base_url
        == "http://nodeskclaw-llm-proxy.nodeskclaw-system.svc.cluster.local:80"
    )


def test_resolve_same_cluster_k8s_keeps_fqdn() -> None:
    endpoints = resolve_platform_endpoints(
        compute_provider="k8s",
        runtime="openclaw",
        instance_namespace="agent-ns",
        cluster_proxy_endpoint=None,
        platform_namespace="nodeskclaw-system",
        settings=_settings(
            llm_proxy_internal_url=(
                "http://nodeskclaw-llm-proxy.nodeskclaw-system.svc.cluster.local:80"
            )
        ),
    )

    assert (
        endpoints.llm_proxy_base_url
        == "http://nodeskclaw-llm-proxy.nodeskclaw-system.svc.cluster.local:80"
    )


def test_resolve_remote_k8s_uses_external_llm_proxy_url() -> None:
    endpoints = resolve_platform_endpoints(
        compute_provider="k8s",
        runtime="hermes",
        instance_namespace="agent-ns",
        cluster_proxy_endpoint="https://proxy-gateway.example.com",
        platform_namespace="nodeskclaw-system",
        settings=_settings(
            llm_proxy_url="https://llm-proxy.example.com",
            llm_proxy_internal_url="http://nodeskclaw-llm-proxy:80",
        ),
    )

    assert endpoints.llm_proxy_base_url == "https://llm-proxy.example.com"


def test_resolve_k8s_without_proxy_address_raises_actionable_error() -> None:
    with pytest.raises(PlatformEndpointConfigError, match="LLM Proxy 地址未配置"):
        resolve_platform_endpoints(
            compute_provider="k8s",
            runtime="openclaw",
            instance_namespace="agent-ns",
            cluster_proxy_endpoint=None,
            platform_namespace="nodeskclaw-system",
            settings=_settings(),
        )
