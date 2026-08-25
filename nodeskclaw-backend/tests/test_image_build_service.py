from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api import image_builds as image_build_api
from app.core.exceptions import BadRequestError
from app.models.image_build import ImageBuild
from app.schemas.image_build import ImageBuildCreate
from app.services import image_build_service


def _build(runtime: str = "openclaw") -> ImageBuild:
    return ImageBuild(
        id="12345678-1234-1234-1234-123456789abc",
        org_id="org-1",
        cluster_id="cluster-1",
        requested_by="user-1",
        runtime=runtime,
        version="2026.8.25",
        image_repository="registry.example.com/team/runtime",
        image_tag="v2026.8.25",
        source_repository="https://github.com/example/project.git",
        source_ref="main",
        namespace="nodeskclaw-builds",
        job_name=f"nodeskclaw-build-{runtime}-12345678",
        status="running",
    )


def _env_map(manifest: dict) -> dict[str, str]:
    env = manifest["spec"]["template"]["spec"]["containers"][0]["env"]
    return {item["name"]: item["value"] for item in env}


def test_build_openclaw_manifest_uses_rootless_amd64_buildkit() -> None:
    manifest = image_build_service.build_image_job_manifest(
        _build("openclaw"),
        registry_secret_name="build-auth",
    )

    pod_spec = manifest["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]
    source = pod_spec["initContainers"][0]
    env = _env_map(manifest)

    assert pod_spec["securityContext"]["runAsUser"] == 1000
    assert pod_spec["securityContext"]["seccompProfile"]["type"] == "Unconfined"
    assert source["command"] == ["/bin/sh", "-lc"]
    assert 'while [ "$attempt" -le 3 ]' in source["args"][0]
    assert env["BUILDKITD_FLAGS"] == "--oci-worker-no-process-sandbox"
    assert env["BUILD_CONTEXT"].endswith("nodeskclaw-artifacts/openclaw-image")
    assert env["DOCKERFILE_DIR"] == env["BUILD_CONTEXT"]
    assert env["VERSION_ARG_NAME"] == "OPENCLAW_VERSION"
    assert env["VERSION_ARG_VALUE"] == "2026.8.25"
    assert "platform=linux/amd64" in container["args"][0]
    assert any(volume["name"] == "registry-auth" for volume in pod_spec["volumes"])


def test_build_hermes_manifest_uses_repository_root_context() -> None:
    manifest = image_build_service.build_image_job_manifest(
        _build("hermes"),
        registry_secret_name=None,
    )
    env = _env_map(manifest)
    pod_spec = manifest["spec"]["template"]["spec"]

    assert env["BUILD_CONTEXT"] == "/workspace/source"
    assert env["DOCKERFILE_DIR"].endswith("nodeskclaw-artifacts/hermes-image")
    assert env["VERSION_ARG_NAME"] == "HERMES_VERSION"
    assert env["VERSION_ARG_VALUE"] == "v2026.8.25"
    assert all(volume["name"] != "registry-auth" for volume in pod_spec["volumes"])


@pytest.mark.parametrize(
    "value",
    ["", "../main", "feature//bad", "-bad", "bad ref", "feature/bad/"],
)
def test_validate_source_ref_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(BadRequestError):
        image_build_service.validate_source_ref(value)


@pytest.mark.parametrize("value", ["bad tag", "-bad", "bad/tag", "v"])
def test_normalize_version_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(BadRequestError):
        image_build_service.normalize_version(value)


@pytest.mark.asyncio
async def test_refresh_completed_build_publishes_catalog_and_captures_logs(monkeypatch) -> None:
    build = _build()
    completion_time = datetime.now(timezone.utc)
    k8s = SimpleNamespace(
        get_job=AsyncMock(
            return_value=SimpleNamespace(
                status=SimpleNamespace(
                    start_time=completion_time,
                    completion_time=completion_time,
                    conditions=[SimpleNamespace(type="Complete", status="True", message=None, reason=None)],
                    succeeded=1,
                    failed=0,
                    active=0,
                )
            )
        ),
        list_pods=AsyncMock(return_value=[{"name": "build-pod"}]),
        get_pod_logs=AsyncMock(return_value="build complete"),
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None)),
        flush=AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.cluster_service.get_cluster",
        AsyncMock(return_value=SimpleNamespace(id="cluster-1")),
    )
    monkeypatch.setattr(image_build_service, "require_k8s_client", AsyncMock(return_value=k8s))
    publish = AsyncMock(return_value=SimpleNamespace(id="version-1"))
    monkeypatch.setattr(image_build_service.engine_version_service, "publish", publish)

    refreshed = await image_build_service.refresh_build(build, db)

    assert refreshed.status == "succeeded"
    assert refreshed.engine_version_id == "version-1"
    assert refreshed.log_text == "[Source]\nbuild complete\n\n[BuildKit]\nbuild complete"
    publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_api_refreshes_build_before_serializing(monkeypatch) -> None:
    build = _build()
    now = datetime.now(timezone.utc)
    build.created_at = now
    build.updated_at = now
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
    monkeypatch.setattr(
        image_build_api.image_build_service,
        "start_build",
        AsyncMock(return_value=build),
    )
    monkeypatch.setattr(image_build_api.hooks, "emit", AsyncMock())

    response = await image_build_api.create_image_build(
        ImageBuildCreate(
            runtime="openclaw",
            version="2026.8.25",
            cluster_id="cluster-1",
        ),
        db=db,
        org_ctx=(SimpleNamespace(id="user-1"), SimpleNamespace(id="org-1")),
    )

    db.refresh.assert_awaited_once_with(build)
    assert response.data.id == build.id
