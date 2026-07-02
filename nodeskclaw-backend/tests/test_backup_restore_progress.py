from types import SimpleNamespace

import pytest

from app.models.deploy_record import DeployStatus
from app.models.instance import InstanceStatus
from app.services import backup_service
from app.services.deploy_service import REBUILD_STEPS


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class _Session:
    def __init__(self, values):
        self.values = list(values)
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, *_args, **_kwargs):
        return _Result(self.values.pop(0))

    async def commit(self):
        self.commits += 1


class _SessionFactory:
    def __init__(self, sessions):
        self.sessions = list(sessions)

    def __call__(self):
        return self.sessions.pop(0)


def _restore_instance() -> SimpleNamespace:
    return SimpleNamespace(
        id="instance-1",
        cluster_id="cluster-1",
        name="demo",
        slug="demo",
        namespace="ns-demo",
        image_version="v1",
        replicas=1,
        cpu_request="100m",
        cpu_limit="500m",
        mem_request="256Mi",
        mem_limit="1Gi",
        storage_class=None,
        storage_size="1Gi",
        quota_cpu="1",
        quota_mem="1Gi",
        env_vars=None,
        advanced_config=None,
        org_id="org-1",
        compute_provider="k8s",
        runtime="hermes",
        status=InstanceStatus.restoring,
    )


def _cluster() -> SimpleNamespace:
    return SimpleNamespace(id="cluster-1", proxy_endpoint=None)


@pytest.mark.asyncio
async def test_restore_marks_success_after_data_restore(monkeypatch) -> None:
    record = SimpleNamespace(status=DeployStatus.running, message=None, finished_at=None)
    instance = _restore_instance()
    backup = SimpleNamespace(storage_key="backups/instance-1/backup.tar.gz")
    session_factory = _SessionFactory([
        _Session([instance, _cluster(), backup]),
        _Session([instance, _cluster(), record]),
    ])
    calls: list[str] = []
    published: list[dict] = []

    class FakeK8s:
        async def exec_in_pod(self, *_args, **_kwargs):
            calls.append("restart-pod")

    async def fake_execute_rebuild_pipeline(ctx, *, finalize_success=True):
        assert ctx.record_id == "deploy-1"
        assert finalize_success is False
        calls.append("rebuild")
        instance.status = InstanceStatus.running

    async def fake_download_raw(storage_key):
        assert storage_key == backup.storage_key
        calls.append("download")
        return b"backup-data"

    async def fake_restore_k8s_data(inst, _db, data):
        assert inst is instance
        assert data == b"backup-data"
        assert record.status == DeployStatus.running
        assert record.finished_at is None
        calls.append("restore-data")

    async def fake_require_k8s_client(_cluster):
        return FakeK8s()

    async def fake_find_pod(_k8s, _namespace, _name):
        return "pod-demo"

    monkeypatch.setattr("app.core.deps.async_session_factory", session_factory)
    monkeypatch.setattr("app.services.deploy_service.execute_rebuild_pipeline", fake_execute_rebuild_pipeline)
    monkeypatch.setattr("app.services.storage_service.download_raw", fake_download_raw)
    monkeypatch.setattr(backup_service, "_restore_k8s_data", fake_restore_k8s_data)
    monkeypatch.setattr("app.services.runtime.registries.compute_registry.require_k8s_client", fake_require_k8s_client)
    monkeypatch.setattr(backup_service, "_find_pod", fake_find_pod)
    monkeypatch.setattr(backup_service.event_bus, "publish", lambda _topic, payload: published.append(payload))

    await backup_service._execute_restore("deploy-1", "instance-1", "backup-1")

    assert calls == ["rebuild", "download", "restore-data", "restart-pod"]
    assert record.status == DeployStatus.success
    assert record.message == "恢复成功"
    assert record.finished_at is not None
    assert published[-1]["status"] == "success"
    assert published[-1]["step"] == len(REBUILD_STEPS)
    assert published[-1]["total_steps"] == len(REBUILD_STEPS)
    assert published[-1]["step_names"] == REBUILD_STEPS


@pytest.mark.asyncio
async def test_restore_data_failure_publishes_failed_final_event(monkeypatch) -> None:
    record = SimpleNamespace(status=DeployStatus.running, message=None, finished_at=None)
    instance = _restore_instance()
    backup = SimpleNamespace(storage_key="backups/instance-1/backup.tar.gz")
    session_factory = _SessionFactory([
        _Session([instance, _cluster(), backup]),
        _Session([instance]),
        _Session([record, instance]),
    ])
    published: list[dict] = []

    async def fake_execute_rebuild_pipeline(_ctx, *, finalize_success=True):
        assert finalize_success is False
        instance.status = InstanceStatus.running

    async def fake_download_raw(_storage_key):
        return b"backup-data"

    async def fail_restore_k8s_data(_inst, _db, _data):
        raise RuntimeError("restore boom")

    monkeypatch.setattr("app.core.deps.async_session_factory", session_factory)
    monkeypatch.setattr("app.services.deploy_service.execute_rebuild_pipeline", fake_execute_rebuild_pipeline)
    monkeypatch.setattr("app.services.storage_service.download_raw", fake_download_raw)
    monkeypatch.setattr(backup_service, "_restore_k8s_data", fail_restore_k8s_data)
    monkeypatch.setattr(backup_service.event_bus, "publish", lambda _topic, payload: published.append(payload))

    await backup_service._execute_restore("deploy-1", "instance-1", "backup-1")

    assert record.status == DeployStatus.failed
    assert record.message == "restore boom"
    assert record.finished_at is not None
    assert instance.status == InstanceStatus.failed
    assert published[-1]["status"] == "failed"
    assert published[-1]["message"] == "restore boom"
    assert published[-1]["step"] == len(REBUILD_STEPS)
    assert published[-1]["total_steps"] == len(REBUILD_STEPS)
    assert published[-1]["step_names"] == REBUILD_STEPS
