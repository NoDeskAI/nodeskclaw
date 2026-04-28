from types import SimpleNamespace

from app.services import llm_config_service


def test_nodeskclaw_tool_names_are_complete() -> None:
    assert llm_config_service.NODESKCLAW_TOOL_NAMES == (
        "nodeskclaw_blackboard",
        "nodeskclaw_topology",
        "nodeskclaw_performance",
        "nodeskclaw_proposals",
        "nodeskclaw_gene_discovery",
        "nodeskclaw_file_download",
        "nodeskclaw_chat_history",
        "nodeskclaw_shared_files",
    )


async def test_build_hermes_provider_payload_uses_named_custom_provider(monkeypatch) -> None:
    configs = [
        SimpleNamespace(
            provider="test-openai",
            key_source="org",
            selected_models=[{"id": "gpt-4.1", "name": "GPT-4.1"}],
            base_url="https://llm.example.com/v1",
            api_type="openai-completions",
        )
    ]
    org_keys = {
        "test-openai": SimpleNamespace(
            provider="test-openai",
            api_key="secret-key",
            base_url="https://llm.example.com/v1",
            api_type="openai-completions",
        )
    }

    monkeypatch.setattr(llm_config_service.settings, "LLM_PROXY_INTERNAL_URL", "http://llm-proxy.internal:4100")
    monkeypatch.setattr(llm_config_service.settings, "LLM_PROXY_URL", "https://llm-proxy.example.com")
    providers, env_updates, primary = await llm_config_service._build_hermes_provider_payload(
        configs,
        wp_api_key="wp-token",
        user_keys={},
        org_keys=org_keys,
        use_external_proxy=False,
    )

    assert providers == [{
        "name": "nodeskclaw-test-openai",
        "base_url": "http://llm-proxy.internal:4100/test-openai/v1",
        "key_env": "NODESKCLAW_WP_API_KEY",
        "api_mode": "chat_completions",
        "model": "gpt-4.1",
    }]
    assert env_updates == {"NODESKCLAW_WP_API_KEY": "wp-token"}
    assert primary == {
        "provider": "nodeskclaw-test-openai",
        "base_url": "http://llm-proxy.internal:4100/test-openai/v1",
        "model": "gpt-4.1",
    }


async def test_build_hermes_provider_payload_keeps_personal_provider_direct() -> None:
    configs = [
        SimpleNamespace(
            provider="personal-openai",
            key_source="personal",
            selected_models=[{"id": "gpt-4.1-mini", "name": "GPT-4.1 mini"}],
            base_url="https://personal.example.com/v1",
            api_type="openai-completions",
        )
    ]
    user_keys = {
        "personal-openai": SimpleNamespace(
            provider="personal-openai",
            api_key="personal-secret",
            base_url="https://personal.example.com/v1",
            api_type="openai-completions",
        )
    }

    providers, env_updates, primary = await llm_config_service._build_hermes_provider_payload(
        configs,
        wp_api_key="wp-token",
        user_keys=user_keys,
        org_keys={},
        use_external_proxy=False,
    )

    assert providers == [{
        "name": "nodeskclaw-personal-openai",
        "base_url": "https://personal.example.com/v1",
        "key_env": "NODESKCLAW_PERSONAL_OPENAI_API_KEY",
        "api_mode": "chat_completions",
        "model": "gpt-4.1-mini",
    }]
    assert env_updates == {"NODESKCLAW_PERSONAL_OPENAI_API_KEY": "personal-secret"}
    assert primary == {
        "provider": "nodeskclaw-personal-openai",
        "base_url": "https://personal.example.com/v1",
        "model": "gpt-4.1-mini",
    }


def test_dotenv_roundtrip_preserves_values() -> None:
    raw = 'OPENAI_API_KEY="abc123"\nOTHER=value\n'

    parsed = llm_config_service._parse_dotenv(raw)

    assert parsed == {"OPENAI_API_KEY": "abc123", "OTHER": "value"}
    assert llm_config_service._dump_dotenv(parsed) == 'OPENAI_API_KEY="abc123"\nOTHER="value"\n'
