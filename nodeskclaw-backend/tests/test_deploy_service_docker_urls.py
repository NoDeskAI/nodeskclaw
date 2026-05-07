import pytest

from app.services import deploy_service
from app.services.deploy_service import (
    DEPLOY_STEPS_BASE,
    _DeployContext,
    _rewrite_docker_callback_url,
    _should_sync_runtime_llm_config,
)


def test_rewrite_docker_callback_url_rewrites_docker_desktop_host() -> None:
    assert _rewrite_docker_callback_url("http://172.17.0.1:4510/api/v1") == "http://host.docker.internal:4510/api/v1"
    assert _rewrite_docker_callback_url("ws://172.17.0.1:4510/api/v1/tunnel/connect") == "ws://host.docker.internal:4510/api/v1/tunnel/connect"


def test_rewrite_docker_callback_url_leaves_remote_host_untouched() -> None:
    assert _rewrite_docker_callback_url("https://nodeskclaw.example.com/api/v1") == "https://nodeskclaw.example.com/api/v1"


def test_should_sync_runtime_llm_config_keeps_openclaw_request_scoped() -> None:
    assert _should_sync_runtime_llm_config("openclaw", True, []) is True
    assert _should_sync_runtime_llm_config("openclaw", False, ["openai"]) is False


def test_should_sync_runtime_llm_config_uses_hermes_org_defaults() -> None:
    assert _should_sync_runtime_llm_config("hermes", True, []) is True
    assert _should_sync_runtime_llm_config("hermes", False, ["openai"]) is True
    assert _should_sync_runtime_llm_config("hermes", False, []) is False


def test_should_sync_runtime_llm_config_skips_unsupported_runtime() -> None:
    assert _should_sync_runtime_llm_config("nanobot", True, ["openai"]) is False


def _deploy_context(*, should_sync_runtime_llm_config: bool) -> _DeployContext:
    return _DeployContext(
        record_id="deploy-1",
        instance_id="instance-1",
        cluster_id="cluster-1",
        name="hermes-1",
        namespace="ns-hermes",
        image_version="latest",
        replicas=1,
        cpu_request="100m",
        cpu_limit="500m",
        mem_request="256Mi",
        mem_limit="1Gi",
        storage_class=None,
        storage_size="1Gi",
        quota_cpu="1",
        quota_mem="1Gi",
        env_vars={},
        advanced_config={},
        runtime="hermes",
        should_sync_runtime_llm_config=should_sync_runtime_llm_config,
    )


@pytest.mark.asyncio
async def test_execute_deploy_pipeline_adds_config_step_when_runtime_sync_requested(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_execute_inner(ctx, async_session_factory, get_config, total, steps):
        captured["ctx"] = ctx
        captured["total"] = total
        captured["steps"] = steps

    monkeypatch.setattr(deploy_service, "_execute_deploy_inner", fake_execute_inner)

    await deploy_service.execute_deploy_pipeline(
        _deploy_context(should_sync_runtime_llm_config=True)
    )

    assert captured["total"] == len(DEPLOY_STEPS_BASE) + 1
    assert captured["steps"] == [*DEPLOY_STEPS_BASE, "应用实例配置"]


@pytest.mark.asyncio
async def test_execute_deploy_pipeline_skips_config_step_without_runtime_sync(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_execute_inner(ctx, async_session_factory, get_config, total, steps):
        captured["ctx"] = ctx
        captured["total"] = total
        captured["steps"] = steps

    monkeypatch.setattr(deploy_service, "_execute_deploy_inner", fake_execute_inner)

    await deploy_service.execute_deploy_pipeline(
        _deploy_context(should_sync_runtime_llm_config=False)
    )

    assert captured["total"] == len(DEPLOY_STEPS_BASE)
    assert captured["steps"] == DEPLOY_STEPS_BASE
