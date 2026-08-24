import json
from types import SimpleNamespace

import pytest

from app.core.exceptions import BadRequestError
from app.models.deploy_record import DeployStatus
from app.models.instance import InstanceStatus
from app.schemas.deploy import DeployRequest
from app.services import deploy_service
from app.services import instance_service
from app.services.deploy_service import (
    DEPLOY_STEPS_BASE,
    PROGRESS_STEP_NAMES_KEY,
    REBUILD_STEPS,
    _DeployContext,
    _ensure_agent_bundle_secret_refs,
    _reject_secret_ref_env_var_collisions,
    _reject_unsupported_secret_refs_for_provider,
    _require_supported_runtime,
    _restore_agent_bundle_with_retry,
    _should_sync_runtime_llm_config,
)


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDb:
    def __init__(self, value):
        self.value = value

    async def execute(self, *_args, **_kwargs):
        return _ScalarResult(self.value)


class _SequenceResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _SequenceSession:
    def __init__(self, values):
        self.values = list(values)
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, *_args, **_kwargs):
        return _SequenceResult(self.values.pop(0))

    async def commit(self):
        self.commits += 1


def test_should_sync_runtime_llm_config_uses_openclaw_org_defaults() -> None:
    assert _should_sync_runtime_llm_config("openclaw", True, []) is True
    assert _should_sync_runtime_llm_config("openclaw", False, ["openai"]) is True
    assert _should_sync_runtime_llm_config("openclaw", False, []) is False


def test_should_sync_runtime_llm_config_uses_hermes_org_defaults() -> None:
    assert _should_sync_runtime_llm_config("hermes", True, []) is True
    assert _should_sync_runtime_llm_config("hermes", False, ["openai"]) is True
    assert _should_sync_runtime_llm_config("hermes", False, []) is False


def test_should_sync_runtime_llm_config_skips_unsupported_runtime() -> None:
    assert _should_sync_runtime_llm_config("unknown_runtime", True, ["openai"]) is False


def test_require_supported_runtime_allows_registered_runtime() -> None:
    _require_supported_runtime("openclaw")
    _require_supported_runtime("hermes")


def test_require_supported_runtime_rejects_removed_nanobot_runtime() -> None:
    with pytest.raises(BadRequestError) as exc_info:
        _require_supported_runtime("nanobot")

    assert exc_info.value.status_code == 400
    assert exc_info.value.message_key == "errors.validation.invalid_runtime"
    assert "nanobot" in exc_info.value.message


@pytest.mark.asyncio
async def test_deploy_instance_rejects_user_supplied_secret_env_refs_before_db_access() -> None:
    class FailingDb:
        async def execute(self, *_args, **_kwargs):
            raise AssertionError("db should not be used before rejecting reserved advanced_config")

    req = DeployRequest(
        cluster_id="cluster-1",
        name="demo",
        image_version="latest",
        advanced_config={
            "secret_env_refs": [{
                "env": "OAUTH_ACCESS_TOKEN",
                "secret_name": "platform-oauth-token",
                "key": "access_token",
                "required": True,
            }],
        },
    )

    with pytest.raises(BadRequestError) as exc_info:
        await deploy_service.deploy_instance(
            req,
            SimpleNamespace(id="user-1"),
            FailingDb(),
            org_id="org-1",
        )

    assert exc_info.value.message_key == "errors.template.secret_env_refs_reserved"
    assert "系统保留字段" in exc_info.value.message


@pytest.mark.asyncio
async def test_deploy_instance_rejects_reserved_secret_env_refs_on_non_k8s_clone_before_create(monkeypatch) -> None:
    class FakeAdapter:
        async def resolve_cluster(self, *_args, **_kwargs):
            return "cluster-1", SimpleNamespace(id="org-1")

        def build_namespace(self, slug, _org):
            return f"ns-{slug}"

    class ClusterResult:
        def scalar_one_or_none(self):
            return SimpleNamespace(
                id="cluster-1",
                compute_provider="process",
                proxy_endpoint=None,
                api_server_url=None,
            )

    class EmptyRowsResult:
        def all(self):
            return []

    class FakeDb:
        def __init__(self):
            self.results = [ClusterResult(), EmptyRowsResult()]
            self.added = []

        async def execute(self, *_args, **_kwargs):
            return self.results.pop(0)

        def add(self, value):
            self.added.append(value)
            raise AssertionError("instance/deploy records should not be created")

    async def fake_get_config(_key, _db):
        return "apps.example.com"

    monkeypatch.setattr(deploy_service, "get_deploy_adapter", lambda: FakeAdapter())
    monkeypatch.setattr(deploy_service.settings, "AGENT_API_BASE_URL", "http://backend.example.com/api/v1")
    monkeypatch.setattr("app.services.config_service.get_config", fake_get_config)

    req = DeployRequest(
        cluster_id="cluster-1",
        name="clone-demo",
        image_version="latest",
        advanced_config={
            "secret_env_refs": [{
                "env": "OAUTH_ACCESS_TOKEN",
                "secret_name": "platform-oauth-token",
                "key": "access_token",
                "required": True,
                "source_namespace": "nodeskclaw-system",
            }],
        },
    )
    db = FakeDb()

    with pytest.raises(BadRequestError) as exc_info:
        await deploy_service.deploy_instance(
            req,
            SimpleNamespace(id="user-1"),
            db,
            org_id="org-1",
            allow_reserved_secret_env_refs=True,
        )

    assert exc_info.value.message_key == "errors.template.secret_refs_require_k8s"
    assert "仅支持 K8s" in exc_info.value.message
    assert db.added == []


def test_instance_config_preserves_internal_secret_env_refs() -> None:
    secret_refs = [{
        "env": "OAUTH_ACCESS_TOKEN",
        "secret_name": "platform-oauth-token",
        "key": "access_token",
        "required": True,
        "source_namespace": "nodeskclaw-system",
    }]
    merged = instance_service._merge_reserved_advanced_config(
        {"network": {"peers": ["peer-1"]}},
        json.dumps({"secret_env_refs": secret_refs, "network": {"peers": ["old-peer"]}}),
    )

    assert merged == {
        "network": {"peers": ["peer-1"]},
        "secret_env_refs": secret_refs,
    }


def test_instance_config_allows_round_trip_internal_secret_env_refs() -> None:
    secret_refs = [{
        "env": "OAUTH_ACCESS_TOKEN",
        "secret_name": "platform-oauth-token",
        "key": "access_token",
        "required": True,
    }]
    merged = instance_service._merge_reserved_advanced_config(
        {"debug": True, "secret_env_refs": secret_refs},
        json.dumps({"secret_env_refs": secret_refs}),
    )

    assert merged == {"debug": True, "secret_env_refs": secret_refs}


def test_instance_config_rejects_modified_internal_secret_env_refs() -> None:
    with pytest.raises(BadRequestError) as exc_info:
        instance_service._merge_reserved_advanced_config(
            {
                "secret_env_refs": [{
                    "env": "OAUTH_ACCESS_TOKEN",
                    "secret_name": "attacker-guessed-secret",
                    "key": "access_token",
                    "required": True,
                }],
            },
            json.dumps({
                "secret_env_refs": [{
                    "env": "OAUTH_ACCESS_TOKEN",
                    "secret_name": "platform-oauth-token",
                    "key": "access_token",
                    "required": True,
                }],
            }),
        )

    assert exc_info.value.message_key == "errors.template.secret_env_refs_reserved"
    assert "系统保留字段" in exc_info.value.message


def test_set_progress_step_names_preserves_existing_config_snapshot() -> None:
    record = SimpleNamespace(config_snapshot=json.dumps({"rollback": {"env": "old"}}))

    deploy_service._set_progress_step_names(record, ["环境预检查", "部署完成"])

    snapshot = json.loads(record.config_snapshot)
    assert snapshot["rollback"] == {"env": "old"}
    assert snapshot[PROGRESS_STEP_NAMES_KEY] == ["环境预检查", "部署完成"]


@pytest.mark.asyncio
async def test_deploy_progress_snapshot_replays_saved_k8s_post_ready_steps() -> None:
    step_names = [*DEPLOY_STEPS_BASE, "应用实例配置"]
    snapshot = await deploy_service.get_deploy_progress_snapshot(
        "deploy-1",
        _FakeDb(SimpleNamespace(
            status=DeployStatus.success,
            message="部署成功",
            config_snapshot=json.dumps({PROGRESS_STEP_NAMES_KEY: step_names}),
        )),
    )

    assert snapshot is not None
    assert snapshot.status == "success"
    assert snapshot.percent == 100
    assert snapshot.step == len(step_names)
    assert snapshot.total_steps == len(step_names)
    assert snapshot.step_names == step_names


@pytest.mark.asyncio
async def test_deploy_progress_snapshot_falls_back_for_invalid_snapshot() -> None:
    snapshot = await deploy_service.get_deploy_progress_snapshot(
        "deploy-1",
        _FakeDb(SimpleNamespace(
            status=DeployStatus.failed,
            action=deploy_service.DeployAction.deploy,
            message="部署失败",
            config_snapshot="{broken",
        )),
    )

    assert snapshot is not None
    assert snapshot.status == "failed"
    assert snapshot.step_names == DEPLOY_STEPS_BASE


@pytest.mark.asyncio
async def test_deploy_progress_snapshot_falls_back_to_rebuild_steps() -> None:
    snapshot = await deploy_service.get_deploy_progress_snapshot(
        "deploy-1",
        _FakeDb(SimpleNamespace(
            status=DeployStatus.success,
            action=deploy_service.DeployAction.restore,
            message="恢复成功",
        )),
    )

    assert snapshot is not None
    assert snapshot.step_names == REBUILD_STEPS


@pytest.mark.asyncio
async def test_deploy_progress_snapshot_skips_running_record() -> None:
    snapshot = await deploy_service.get_deploy_progress_snapshot(
        "deploy-1",
        _FakeDb(SimpleNamespace(status=DeployStatus.running, message=None)),
    )

    assert snapshot is None


@pytest.mark.asyncio
async def test_cancel_deploy_uses_saved_progress_step_names(monkeypatch) -> None:
    step_names = [*DEPLOY_STEPS_BASE, "应用实例配置"]
    record = SimpleNamespace(
        id="deploy-1",
        instance_id="instance-1",
        status=DeployStatus.running,
        message=None,
        finished_at=None,
        config_snapshot=json.dumps({PROGRESS_STEP_NAMES_KEY: step_names}),
    )
    instance = SimpleNamespace(
        id="instance-1",
        name="demo",
        status=InstanceStatus.deploying,
    )
    session = _SequenceSession([record, instance])
    published: list[dict] = []
    finalizers: list[str] = []

    monkeypatch.setattr("app.core.deps.async_session_factory", lambda: session)
    monkeypatch.setattr(
        "app.services.instance_service.schedule_instance_deletion_finalizer",
        lambda instance_id: finalizers.append(instance_id),
    )
    monkeypatch.setattr(
        deploy_service.event_bus,
        "publish",
        lambda _topic, payload: published.append(payload),
    )

    result = await deploy_service.cancel_deploy("deploy-1")

    assert result == "已取消，资源清理已开始"
    assert record.status == DeployStatus.failed
    assert record.finished_at is not None
    assert instance.status == InstanceStatus.deleting
    assert finalizers == ["instance-1"]
    assert session.commits == 1
    assert published[-1]["status"] == "failed"
    assert published[-1]["step"] == len(step_names)
    assert published[-1]["total_steps"] == len(step_names)
    assert published[-1]["step_names"] == step_names


@pytest.mark.asyncio
async def test_cancel_deploy_falls_back_to_legacy_deploy_steps(monkeypatch) -> None:
    record = SimpleNamespace(
        id="deploy-1",
        instance_id="instance-1",
        status=DeployStatus.running,
        message=None,
        finished_at=None,
        config_snapshot=None,
    )
    instance = SimpleNamespace(
        id="instance-1",
        name="demo",
        status=InstanceStatus.deploying,
    )
    session = _SequenceSession([record, instance])
    published: list[dict] = []
    finalizers: list[str] = []

    monkeypatch.setattr("app.core.deps.async_session_factory", lambda: session)
    monkeypatch.setattr(
        "app.services.instance_service.schedule_instance_deletion_finalizer",
        lambda instance_id: finalizers.append(instance_id),
    )
    monkeypatch.setattr(
        deploy_service.event_bus,
        "publish",
        lambda _topic, payload: published.append(payload),
    )

    result = await deploy_service.cancel_deploy("deploy-1")

    assert result == "已取消，资源清理已开始"
    assert session.values == []
    assert finalizers == ["instance-1"]
    assert published[-1]["step_names"] == DEPLOY_STEPS_BASE
    assert published[-1]["step"] == len(DEPLOY_STEPS_BASE)
    assert published[-1]["total_steps"] == len(DEPLOY_STEPS_BASE)


@pytest.mark.asyncio
async def test_agent_bundle_secret_refs_ignore_backend_source_env(monkeypatch) -> None:
    applied = []

    class MissingSecret(Exception):
        status = 404

    class FakeCore:
        async def read_namespaced_secret(self, *_args, **_kwargs):
            raise MissingSecret()

    class FakeK8s:
        core = FakeCore()

        async def apply(self, *_args, **_kwargs):
            applied.append((_args, _kwargs))

    monkeypatch.setenv("NODESKCLAW_TEST_OAUTH_ACCESS_TOKEN", "mock-access-token")

    with pytest.raises(BadRequestError) as exc_info:
        await _ensure_agent_bundle_secret_refs(
            FakeK8s(),
            "agent-ns",
            [{
                "env": "OAUTH_ACCESS_TOKEN",
                "secret_name": "mock-oauth-token",
                "key": "access_token",
                "source_env": "NODESKCLAW_TEST_OAUTH_ACCESS_TOKEN",
                "required": True,
            }],
            {"app.kubernetes.io/managed-by": "nodeskclaw"},
        )

    assert applied == []
    assert "缺少鉴权 Secret" in exc_info.value.message
    assert "平台环境变量" not in exc_info.value.message


@pytest.mark.asyncio
async def test_agent_bundle_secret_refs_fail_fast_when_missing() -> None:
    class MissingSecret(Exception):
        status = 404

    class FakeCore:
        async def read_namespaced_secret(self, *_args, **_kwargs):
            raise MissingSecret()

    class FakeK8s:
        core = FakeCore()

        async def apply(self, *_args, **_kwargs):
            raise AssertionError("should not create a secret without source env value")

    with pytest.raises(BadRequestError) as exc_info:
        await _ensure_agent_bundle_secret_refs(
            FakeK8s(),
            "agent-ns",
            [{
                "env": "OAUTH_ACCESS_TOKEN",
                "secret_name": "mock-oauth-token",
                "key": "access_token",
                "required": True,
            }],
            {},
        )
    assert "缺少鉴权 Secret" in exc_info.value.message


@pytest.mark.asyncio
async def test_agent_bundle_secret_refs_do_not_read_platform_without_trusted_source() -> None:
    reads = []

    class MissingSecret(Exception):
        status = 404

    class FakeCore:
        async def read_namespaced_secret(self, secret_name, namespace):
            reads.append((namespace, secret_name))
            if namespace == "nodeskclaw-system":
                return SimpleNamespace(data={"access_token": "encoded"})
            raise MissingSecret()

    class FakeK8s:
        core = FakeCore()

    with pytest.raises(BadRequestError):
        await _ensure_agent_bundle_secret_refs(
            FakeK8s(),
            "agent-ns",
            [{
                "env": "OAUTH_ACCESS_TOKEN",
                "secret_name": "mock-oauth-token",
                "key": "access_token",
                "required": True,
            }],
            {},
        )

    assert reads == [("agent-ns", "mock-oauth-token")]


@pytest.mark.asyncio
async def test_agent_bundle_secret_refs_accept_existing_secret_key() -> None:
    class FakeCore:
        async def read_namespaced_secret(self, *_args, **_kwargs):
            return SimpleNamespace(data={"access_token": "encoded"})

    class FakeK8s:
        core = FakeCore()

        async def apply(self, *_args, **_kwargs):
            raise AssertionError("existing secret should be reused")

    await _ensure_agent_bundle_secret_refs(
        FakeK8s(),
        "agent-ns",
        [{
            "env": "OAUTH_ACCESS_TOKEN",
            "secret_name": "mock-oauth-token",
            "key": "access_token",
            "required": True,
        }],
        {},
    )


@pytest.mark.asyncio
async def test_agent_bundle_secret_refs_accept_platform_secret_before_namespace_created() -> None:
    reads = []

    class MissingSecret(Exception):
        status = 404

    class FakeCore:
        async def read_namespaced_secret(self, secret_name, namespace):
            reads.append((namespace, secret_name))
            if namespace == "nodeskclaw-system":
                return SimpleNamespace(data={"access_token": "encoded"})
            raise MissingSecret()

        async def create_namespaced_secret(self, *_args, **_kwargs):
            raise AssertionError("preflight should not create target namespace secret")

    class FakeK8s:
        core = FakeCore()

        async def create_or_skip(self, *_args, **_kwargs):
            raise AssertionError("preflight should not create target namespace secret")

    await _ensure_agent_bundle_secret_refs(
        FakeK8s(),
        "agent-ns",
        [{
            "env": "OAUTH_ACCESS_TOKEN",
            "secret_name": "mock-oauth-token",
            "key": "access_token",
            "required": True,
            "source_namespace": "nodeskclaw-system",
        }],
        {},
    )

    assert reads == [
        ("agent-ns", "mock-oauth-token"),
        ("nodeskclaw-system", "mock-oauth-token"),
    ]


@pytest.mark.asyncio
async def test_agent_bundle_secret_refs_copy_platform_secret_after_namespace_created() -> None:
    created = []

    class MissingSecret(Exception):
        status = 404

    class FakeCore:
        async def read_namespaced_secret(self, secret_name, namespace):
            if namespace == "nodeskclaw-system":
                return SimpleNamespace(data={
                    "access_token": "encoded-token",
                    "refresh_token": "do-not-copy",
                })
            raise MissingSecret()

        async def create_namespaced_secret(self, namespace, body):
            created.append((namespace, body))

        async def patch_namespaced_secret(self, *_args, **_kwargs):
            raise AssertionError("target secret is missing and should be created")

    class FakeK8s:
        core = FakeCore()

        async def apply(self, create_fn, _patch_fn, namespace, name, body):
            assert name == "mock-oauth-token"
            return await create_fn(namespace, body)

        async def create_or_skip(self, create_fn, *args, **kwargs):
            return await create_fn(*args, **kwargs)

    await _ensure_agent_bundle_secret_refs(
        FakeK8s(),
        "agent-ns",
        [{
            "env": "OAUTH_ACCESS_TOKEN",
            "secret_name": "mock-oauth-token",
            "key": "access_token",
            "required": True,
            "source_namespace": "nodeskclaw-system",
        }],
        {"app.kubernetes.io/managed-by": "nodeskclaw"},
        copy_missing=True,
    )

    assert len(created) == 1
    namespace, body = created[0]
    assert namespace == "agent-ns"
    assert body.metadata.name == "mock-oauth-token"
    assert body.metadata.namespace == "agent-ns"
    assert body.metadata.labels == {"app.kubernetes.io/managed-by": "nodeskclaw"}
    assert body.data == {"access_token": "encoded-token"}
    assert body.string_data is None


@pytest.mark.asyncio
async def test_agent_bundle_secret_refs_skip_optional_missing_secret() -> None:
    class FakeCore:
        async def read_namespaced_secret(self, *_args, **_kwargs):
            raise AssertionError("optional secret refs should not be preflighted")

    class FakeK8s:
        core = FakeCore()

    await _ensure_agent_bundle_secret_refs(
        FakeK8s(),
        "agent-ns",
        [{
            "env": "OPTIONAL_ACCESS_TOKEN",
            "secret_name": "mock-oauth-token",
            "key": "access_token",
            "required": False,
        }],
        {},
    )


def test_secret_refs_reject_required_refs_on_non_k8s_provider() -> None:
    with pytest.raises(BadRequestError) as exc_info:
        _reject_unsupported_secret_refs_for_provider(
            "process",
            [{
                "env": "OAUTH_ACCESS_TOKEN",
                "secret_name": "mock-oauth-token",
                "key": "access_token",
                "required": True,
            }],
        )

    assert "仅支持 K8s" in exc_info.value.message


def test_secret_refs_allow_optional_refs_on_non_k8s_provider() -> None:
    _reject_unsupported_secret_refs_for_provider(
        "process",
        [{
            "env": "OPTIONAL_ACCESS_TOKEN",
            "secret_name": "mock-oauth-token",
            "key": "access_token",
            "required": False,
        }],
    )


def test_secret_refs_reject_plain_env_var_collision() -> None:
    with pytest.raises(BadRequestError) as exc_info:
        _reject_secret_ref_env_var_collisions(
            {"OAUTH_ACCESS_TOKEN": "plain-token"},
            [{
                "env": "OAUTH_ACCESS_TOKEN",
                "secret_name": "mock-oauth-token",
                "key": "access_token",
                "required": True,
            }],
        )

    assert "不能同时写入普通 env_vars" in exc_info.value.message


@pytest.mark.asyncio
async def test_precheck_rejects_removed_nanobot_runtime_before_db_access() -> None:
    class FailingDb:
        async def execute(self, *_args, **_kwargs):
            raise AssertionError("db should not be used")

    req = DeployRequest(
        cluster_id="cluster-1",
        name="demo",
        runtime="nanobot",
        image_version="v0.1.4",
    )

    with pytest.raises(BadRequestError) as exc_info:
        await deploy_service.precheck(req, FailingDb())

    assert exc_info.value.message_key == "errors.validation.invalid_runtime"


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

    async def fake_persist(_db, deploy_id, steps):
        captured["persisted_deploy_id"] = deploy_id
        captured["persisted_steps"] = steps

    monkeypatch.setattr(deploy_service, "_execute_deploy_inner", fake_execute_inner)
    monkeypatch.setattr(deploy_service, "_persist_deploy_progress_step_names", fake_persist)

    await deploy_service.execute_deploy_pipeline(
        _deploy_context(should_sync_runtime_llm_config=True)
    )

    assert captured["total"] == len(DEPLOY_STEPS_BASE) + 1
    assert captured["steps"] == [*DEPLOY_STEPS_BASE, "应用实例配置"]
    assert captured["persisted_deploy_id"] == "deploy-1"
    assert captured["persisted_steps"] == [*DEPLOY_STEPS_BASE, "应用实例配置"]


@pytest.mark.asyncio
async def test_execute_deploy_pipeline_skips_config_step_without_runtime_sync(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_execute_inner(ctx, async_session_factory, get_config, total, steps):
        captured["ctx"] = ctx
        captured["total"] = total
        captured["steps"] = steps

    monkeypatch.setattr(deploy_service, "_execute_deploy_inner", fake_execute_inner)
    monkeypatch.setattr(
        deploy_service,
        "_persist_deploy_progress_step_names",
        lambda *_args, **_kwargs: deploy_service.asyncio.sleep(0),
    )

    await deploy_service.execute_deploy_pipeline(
        _deploy_context(should_sync_runtime_llm_config=False)
    )

    assert captured["total"] == len(DEPLOY_STEPS_BASE)
    assert captured["steps"] == DEPLOY_STEPS_BASE


@pytest.mark.asyncio
async def test_execute_deploy_pipeline_adds_agent_bundle_restore_step(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_execute_inner(ctx, async_session_factory, get_config, total, steps):
        captured["ctx"] = ctx
        captured["total"] = total
        captured["steps"] = steps

    ctx = _deploy_context(should_sync_runtime_llm_config=False)
    ctx.template_agent_bundle_manifest = {"slug": "p0-echo-agent", "files": {}, "skills": []}
    monkeypatch.setattr(deploy_service, "_execute_deploy_inner", fake_execute_inner)
    monkeypatch.setattr(
        deploy_service,
        "_persist_deploy_progress_step_names",
        lambda *_args, **_kwargs: deploy_service.asyncio.sleep(0),
    )

    await deploy_service.execute_deploy_pipeline(ctx)

    assert captured["total"] == len(DEPLOY_STEPS_BASE) + 1
    assert captured["steps"] == [*DEPLOY_STEPS_BASE, "恢复 AI 员工模板包"]


@pytest.mark.asyncio
async def test_execute_deploy_pipeline_rejects_non_k8s_provider(monkeypatch) -> None:
    published: list[dict] = []
    failed: list[str] = []

    async def fake_mark_failed(_ctx, message):
        failed.append(message)

    async def fake_execute_inner(*_args, **_kwargs):
        raise AssertionError("k8s pipeline should not run for non-k8s provider")

    monkeypatch.setattr(deploy_service, "_mark_deploy_failed", fake_mark_failed)
    monkeypatch.setattr(deploy_service, "_execute_deploy_inner", fake_execute_inner)
    monkeypatch.setattr(
        deploy_service.event_bus,
        "publish",
        lambda _topic, payload: published.append(payload),
    )

    ctx = _deploy_context(should_sync_runtime_llm_config=False)
    ctx.compute_provider = "process"

    await deploy_service.execute_deploy_pipeline(ctx)

    assert failed and "仅支持 K8s" in failed[0]
    assert published[-1]["status"] == "failed"
    assert published[-1]["percent"] == 100


@pytest.mark.asyncio
async def test_k8s_deploy_marks_success_after_post_ready_steps(monkeypatch) -> None:
    record = SimpleNamespace(status=DeployStatus.running, finished_at=None, message="")
    instance = SimpleNamespace(id="instance-1", status=None, available_replicas=0)
    cluster = SimpleNamespace(id="cluster-1", ingress_class=None)
    published: list[dict] = []

    class FakeResult:
        def __init__(self, value):
            self.value = value

        def scalar_one(self):
            return self.value

    class FakeSession:
        def __init__(self):
            self.results = [cluster, record, instance]
            self.commits = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, *_args, **_kwargs):
            return FakeResult(self.results.pop(0))

        async def commit(self):
            self.commits += 1

    class FakeCore:
        async def create_namespaced_resource_quota(self, *_args, **_kwargs):
            return None

        async def create_namespaced_config_map(self, *_args, **_kwargs):
            return None

        async def create_namespaced_persistent_volume_claim(self, *_args, **_kwargs):
            return None

        async def create_namespaced_service(self, *_args, **_kwargs):
            return None

    class FakeApps:
        async def create_namespaced_deployment(self, *_args, **_kwargs):
            return None

        async def patch_namespaced_deployment(self, *_args, **_kwargs):
            return None

    class FakeNetworking:
        async def create_namespaced_network_policy(self, *_args, **_kwargs):
            return None

        async def patch_namespaced_network_policy(self, *_args, **_kwargs):
            return None

    class FakeK8s:
        core = FakeCore()
        apps = FakeApps()
        networking = FakeNetworking()

        async def ensure_namespace(self, *_args, **_kwargs):
            return None

        async def create_or_skip(self, *_args, **_kwargs):
            return None

        async def apply(self, *_args, **_kwargs):
            return None

        async def get_deployment_status(self, *_args, **_kwargs):
            return {"ready_replicas": 1, "available_replicas": 1, "conditions": []}

    class FakeAdapter:
        def get_namespace_labels(self, _org_id):
            return {}

        def get_network_policy_org_id(self, org_id):
            return org_id

    async def fake_sleep(_delay):
        return None

    async def fake_get_config(_key, _db):
        return None

    async def fake_require_k8s_client(_cluster):
        return FakeK8s()

    async def fake_resolve_registry_config(_db, _runtime):
        from app.services.registry_service import ResolvedRegistryConfig

        return ResolvedRegistryConfig(
            mode="custom",
            image_registry="example/openclaw",
            username=None,
            password=None,
        )

    async def fake_post_ready(_ctx, _instance, _db, **_kwargs):
        assert record.status == DeployStatus.running
        assert record.finished_at is None
        return "部署成功"

    monkeypatch.setattr(deploy_service.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(deploy_service, "get_deploy_adapter", lambda: FakeAdapter())
    monkeypatch.setattr("app.services.runtime.registries.compute_registry.require_k8s_client", fake_require_k8s_client)
    monkeypatch.setattr(
        "app.services.registry_service.resolve_registry_config",
        fake_resolve_registry_config,
    )
    monkeypatch.setattr(deploy_service, "_run_post_ready_instance_steps", fake_post_ready)
    monkeypatch.setattr(
        deploy_service.event_bus,
        "publish",
        lambda _topic, payload: published.append(payload),
    )

    await deploy_service._execute_deploy_inner(
        _deploy_context(should_sync_runtime_llm_config=False),
        lambda: FakeSession(),
        fake_get_config,
        len(DEPLOY_STEPS_BASE),
        DEPLOY_STEPS_BASE,
    )

    assert record.status == DeployStatus.success
    assert record.message == "部署成功"
    assert record.finished_at is not None
    assert instance.status == deploy_service.InstanceStatus.running
    assert published[-1]["status"] == "success"
    assert all(item["step_names"] == DEPLOY_STEPS_BASE for item in published)


@pytest.mark.asyncio
async def test_restore_agent_bundle_retries_transient_exec_failure(monkeypatch) -> None:
    calls = 0
    sleeps: list[float] = []

    async def fake_restore(instance, manifest, db):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("exec not ready")

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr("app.services.agent_bundle_service.restore_agent_bundle", fake_restore)
    monkeypatch.setattr(deploy_service.asyncio, "sleep", fake_sleep)

    await _restore_agent_bundle_with_retry(
        SimpleNamespace(id="instance-1"),
        {"slug": "bundle-1"},
        None,
        max_retries=2,
        retry_delay=0.5,
    )

    assert calls == 2
    assert sleeps == [0.5]


@pytest.mark.asyncio
async def test_restore_agent_bundle_raises_after_retries(monkeypatch) -> None:
    calls = 0

    async def fake_restore(instance, manifest, db):
        nonlocal calls
        calls += 1
        raise RuntimeError("exec still unavailable")

    async def fake_sleep(delay):
        return None

    monkeypatch.setattr("app.services.agent_bundle_service.restore_agent_bundle", fake_restore)
    monkeypatch.setattr(deploy_service.asyncio, "sleep", fake_sleep)

    with pytest.raises(RuntimeError, match="exec still unavailable"):
        await _restore_agent_bundle_with_retry(
            SimpleNamespace(id="instance-1"),
            {"slug": "bundle-1"},
            None,
            max_retries=2,
            retry_delay=0.5,
        )

    assert calls == 3
