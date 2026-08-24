import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.deploy_record import DeployStatus
from app.models.instance import InstanceStatus
from app.services import deploy_service
from app.services.deploy_service import _DeployContext


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value


class _SessionFactory:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeDb:
    def __init__(self, results):
        self.results = list(results)
        self.commit = AsyncMock()

    async def execute(self, _stmt):
        return _Result(self.results.pop(0))


class _MissingSecret(Exception):
    status = 404


class _FakeK8s:
    def __init__(self, secrets_by_namespace: dict[tuple[str, str], object] | None = None):
        self.secrets_by_namespace = secrets_by_namespace or {}
        self.secret_reads: list[tuple[str, str]] = []

        async def read_namespaced_secret(secret_name, namespace):
            self.secret_reads.append((namespace, secret_name))
            secret = self.secrets_by_namespace.get((namespace, secret_name))
            if secret is None:
                raise _MissingSecret()
            return secret

        self.core = SimpleNamespace(
            read_namespaced_secret=read_namespaced_secret,
            create_namespaced_resource_quota=AsyncMock(),
            create_namespaced_config_map=AsyncMock(),
            create_namespaced_persistent_volume_claim=AsyncMock(),
            create_namespaced_secret=AsyncMock(),
            create_namespaced_service=AsyncMock(),
        )
        self.apps = SimpleNamespace(
            create_namespaced_deployment=AsyncMock(),
            patch_namespaced_deployment=AsyncMock(),
        )
        self.networking = SimpleNamespace(
            create_namespaced_ingress=AsyncMock(),
            delete_namespaced_network_policy=AsyncMock(),
            create_namespaced_network_policy=AsyncMock(),
            patch_namespaced_network_policy=AsyncMock(),
        )
        self.ensure_namespace = AsyncMock()
        self.created = []
        self.applied = []

    async def create_or_skip(self, create_fn, *args, **kwargs):
        assert callable(create_fn)
        self.created.append((create_fn, args, kwargs))

    async def apply(self, create_fn, patch_fn, namespace, name, body):
        assert callable(create_fn)
        assert callable(patch_fn)
        self.applied.append((namespace, name, body))

    async def get_deployment_status(self, namespace, name):
        return {"ready": True, "available_replicas": 1}


def _ctx() -> _DeployContext:
    return _DeployContext(
        record_id="deploy-1",
        instance_id="instance-1",
        cluster_id="cluster-1",
        name="hermes-1",
        namespace="ns-hermes",
        image_version="v1",
        replicas=1,
        cpu_request="100m",
        cpu_limit="500m",
        mem_request="256Mi",
        mem_limit="1Gi",
        storage_class="fast-storage",
        storage_size="20Gi",
        quota_cpu="1",
        quota_mem="1Gi",
        env_vars={"GATEWAY_TOKEN": "token"},
        advanced_config={},
        runtime="hermes",
        pvc_access_mode="ReadWriteMany",
    )


@pytest.mark.asyncio
async def test_execute_rebuild_pipeline_uses_current_k8s_builder_signatures(monkeypatch) -> None:
    fake_k8s = _FakeK8s()
    record = SimpleNamespace(status=DeployStatus.running, message=None, finished_at=None, config_snapshot=None)
    instance = SimpleNamespace(
        status=InstanceStatus.rebuilding,
        available_replicas=0,
    )
    db = _FakeDb([
        record,
        SimpleNamespace(id="cluster-1", ingress_class="nginx"),
        record,
        instance,
    ])

    async def fake_get_config(key, _db):
        values = {
            "registry_username": "user",
            "registry_password": "pass",
            "ingress_base_domain": None,
            "ingress_subdomain_suffix": None,
            "tls_secret_name": None,
            "network_policy_ingress_enabled": "false",
            "network_policy_egress_enabled": "false",
        }
        return values.get(key)

    async def fake_resolve_registry_config(_db, _runtime):
        return registry_service.ResolvedRegistryConfig(
            mode="custom",
            image_registry="registry.example.com/deskclaw-hermes",
            username="user",
            password="pass",
        )

    published: list[dict] = []

    monkeypatch.setattr(deploy_service.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(deploy_service.event_bus, "publish", lambda _topic, payload: published.append(payload))
    monkeypatch.setattr(
        deploy_service,
        "get_deploy_adapter",
        lambda: SimpleNamespace(
            get_namespace_labels=lambda org_id: {"nodeskclaw.io/org-id": org_id or "org-1"},
            get_tls_secret=lambda tls_secret, has_proxy: tls_secret,
            get_network_policy_org_id=lambda org_id: org_id,
            setup_proxy=AsyncMock(),
        ),
    )

    import app.core.deps as deps
    import app.services.config_service as config_service
    import app.services.registry_service as registry_service
    import app.services.runtime.registries.compute_registry as compute_registry

    monkeypatch.setattr(deps, "async_session_factory", lambda: _SessionFactory(db))
    monkeypatch.setattr(config_service, "get_config", fake_get_config)
    monkeypatch.setattr(registry_service, "resolve_registry_config", fake_resolve_registry_config)
    monkeypatch.setattr(compute_registry, "require_k8s_client", AsyncMock(return_value=fake_k8s))

    await deploy_service.execute_rebuild_pipeline(_ctx())

    fake_k8s.ensure_namespace.assert_awaited_once_with(
        "ns-hermes",
        extra_labels={"nodeskclaw.io/org-id": "org-1"},
    )

    created_by_fn = {call[0]: call[1] for call in fake_k8s.created}
    pvc = created_by_fn[fake_k8s.core.create_namespaced_persistent_volume_claim][1]
    assert pvc.metadata.name == "hermes-1-root-data"
    assert pvc.metadata.namespace == "ns-hermes"
    assert pvc.spec.storage_class_name == "fast-storage"
    assert pvc.spec.resources.requests["storage"] == "20Gi"
    assert pvc.spec.access_modes == ["ReadWriteMany"]

    deployment = fake_k8s.applied[0][2]
    assert fake_k8s.applied[0][:2] == ("ns-hermes", "hermes-1")
    assert deployment.metadata.name == "hermes-1"
    assert deployment.spec.template.spec.image_pull_secrets[0].name == "nodeskclaw-registry"
    assert record.status == DeployStatus.success
    assert json.loads(record.config_snapshot)[deploy_service.PROGRESS_STEP_NAMES_KEY] == deploy_service.REBUILD_STEPS
    assert instance.status == InstanceStatus.running
    assert published
    assert all(item["step_names"] == deploy_service.REBUILD_STEPS for item in published)


@pytest.mark.asyncio
async def test_execute_rebuild_pipeline_copies_agent_bundle_secret_refs(monkeypatch) -> None:
    fake_k8s = _FakeK8s({
        ("nodeskclaw-system", "mock-oauth-token"): SimpleNamespace(data={
            "access_token": "encoded-token",
            "refresh_token": "do-not-copy",
        }),
    })
    record = SimpleNamespace(status=DeployStatus.running, message=None, finished_at=None, config_snapshot=None)
    instance = SimpleNamespace(
        status=InstanceStatus.rebuilding,
        available_replicas=0,
    )
    db = _FakeDb([
        record,
        SimpleNamespace(id="cluster-1", ingress_class="nginx"),
        record,
        instance,
    ])

    async def fake_get_config(key, _db):
        values = {
            "registry_username": None,
            "registry_password": None,
            "ingress_base_domain": None,
            "ingress_subdomain_suffix": None,
            "tls_secret_name": None,
            "network_policy_ingress_enabled": "false",
            "network_policy_egress_enabled": "false",
        }
        return values.get(key)

    async def fake_resolve_registry_config(_db, _runtime):
        return registry_service.ResolvedRegistryConfig(
            mode="custom",
            image_registry="registry.example.com/deskclaw-hermes",
            username=None,
            password=None,
        )

    monkeypatch.setattr(deploy_service.settings, "PLATFORM_NAMESPACE", "nodeskclaw-system")
    monkeypatch.setattr(deploy_service.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(deploy_service.event_bus, "publish", lambda *_args: None)
    monkeypatch.setattr(
        deploy_service,
        "get_deploy_adapter",
        lambda: SimpleNamespace(
            get_namespace_labels=lambda org_id: {"nodeskclaw.io/org-id": org_id or "org-1"},
            get_tls_secret=lambda tls_secret, has_proxy: tls_secret,
            get_network_policy_org_id=lambda org_id: org_id,
            setup_proxy=AsyncMock(),
        ),
    )

    import app.core.deps as deps
    import app.services.config_service as config_service
    import app.services.registry_service as registry_service
    import app.services.runtime.registries.compute_registry as compute_registry

    monkeypatch.setattr(deps, "async_session_factory", lambda: _SessionFactory(db))
    monkeypatch.setattr(config_service, "get_config", fake_get_config)
    monkeypatch.setattr(registry_service, "resolve_registry_config", fake_resolve_registry_config)
    monkeypatch.setattr(compute_registry, "require_k8s_client", AsyncMock(return_value=fake_k8s))

    ctx = _ctx()
    ctx.advanced_config = {
        "secret_env_refs": [{
            "env": "OAUTH_ACCESS_TOKEN",
            "secret_name": "mock-oauth-token",
            "key": "access_token",
            "required": True,
            "source_namespace": "nodeskclaw-system",
        }],
    }

    await deploy_service.execute_rebuild_pipeline(ctx)

    assert fake_k8s.secret_reads == [
        ("ns-hermes", "mock-oauth-token"),
        ("nodeskclaw-system", "mock-oauth-token"),
    ]
    created_secrets = [
        args[1]
        for create_fn, args, _kwargs in fake_k8s.created
        if create_fn == fake_k8s.core.create_namespaced_secret
    ]
    assert len(created_secrets) == 1
    copied_secret = created_secrets[0]
    assert copied_secret.metadata.name == "mock-oauth-token"
    assert copied_secret.metadata.namespace == "ns-hermes"
    assert copied_secret.data == {"access_token": "encoded-token"}

    deployment = fake_k8s.applied[0][2]
    env_by_name = {item.name: item for item in deployment.spec.template.spec.containers[0].env}
    selector = env_by_name["OAUTH_ACCESS_TOKEN"].value_from.secret_key_ref
    assert selector.name == "mock-oauth-token"
    assert selector.key == "access_token"
