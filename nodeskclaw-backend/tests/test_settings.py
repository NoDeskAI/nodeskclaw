from app.core.config import Settings


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
