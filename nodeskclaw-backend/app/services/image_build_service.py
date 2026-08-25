"""Run OpenClaw and Hermes image builds as rootless BuildKit Jobs in Kubernetes."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from kubernetes_asyncio.client import ApiException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models.base import not_deleted
from app.models.engine_version import EngineVersion
from app.models.image_build import ImageBuild
from app.services import engine_version_service, registry_service
from app.services.runtime.registries.compute_registry import require_k8s_client
from app.services.runtime.registries.runtime_registry import RUNTIME_REGISTRY

logger = logging.getLogger(__name__)

SUPPORTED_RUNTIMES = frozenset({"openclaw", "hermes"})
ACTIVE_STATUSES = ("pending", "running")
TERMINAL_STATUSES = ("succeeded", "failed")
_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SOURCE_REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
_LOG_LIMIT = 200_000


def _build_proxy_env() -> list[dict[str, str]]:
    proxy_url = settings.IMAGE_BUILD_PROXY_URL.strip()
    if not proxy_url:
        return []
    no_proxy = settings.IMAGE_BUILD_NO_PROXY.strip()
    values = {
        "HTTP_PROXY": proxy_url,
        "HTTPS_PROXY": proxy_url,
        "http_proxy": proxy_url,
        "https_proxy": proxy_url,
    }
    if no_proxy:
        values["NO_PROXY"] = no_proxy
        values["no_proxy"] = no_proxy
    return [{"name": name, "value": value} for name, value in values.items()]


def _build_mirror_env() -> list[dict[str, str]]:
    values = {
        "PIP_INDEX_URL": settings.IMAGE_BUILD_PIP_INDEX_URL.strip(),
        "PIP_TRUSTED_HOST": settings.IMAGE_BUILD_PIP_TRUSTED_HOST.strip(),
        "NPM_REGISTRY": settings.IMAGE_BUILD_NPM_REGISTRY.strip(),
        "APT_MIRROR": settings.IMAGE_BUILD_APT_MIRROR.strip(),
    }
    return [
        {"name": name, "value": value}
        for name, value in values.items()
        if value
    ]


def normalize_version(value: str) -> str:
    version = value.strip().removeprefix("v")
    if not _VERSION_PATTERN.fullmatch(version):
        raise BadRequestError(
            "版本号只能包含字母、数字、点、短横线和下划线",
            "errors.image_build.invalid_version",
        )
    return version


def validate_source_ref(value: str) -> str:
    source_ref = value.strip()
    if (
        not _SOURCE_REF_PATTERN.fullmatch(source_ref)
        or ".." in source_ref
        or "//" in source_ref
        or source_ref.endswith("/")
    ):
        raise BadRequestError(
            "源码分支或标签格式无效",
            "errors.image_build.invalid_source_ref",
        )
    return source_ref


def build_image_job_manifest(
    build: ImageBuild,
    *,
    registry_secret_name: str | None,
) -> dict:
    proxy_env = _build_proxy_env()
    mirror_env = _build_mirror_env()
    labels = {
        "app.kubernetes.io/name": "nodeskclaw-image-build",
        "app.kubernetes.io/managed-by": "nodeskclaw",
        "nodeskclaw/image-build-id": build.id,
        "nodeskclaw/runtime": build.runtime,
    }
    if build.runtime == "openclaw":
        build_context = "/workspace/source/nodeskclaw-artifacts/openclaw-image"
        dockerfile_dir = build_context
        source_paths = "nodeskclaw-artifacts/openclaw-image"
        version_arg_name = "OPENCLAW_VERSION"
        version_arg_value = build.version
    else:
        build_context = "/workspace/source"
        dockerfile_dir = "/workspace/source/nodeskclaw-artifacts/hermes-image"
        source_paths = "nodeskclaw-artifacts/hermes-image hermes-nodeskclaw-bridge"
        version_arg_name = "HERMES_VERSION"
        version_arg_value = f"v{build.version}"

    volumes = [
        {"name": "workspace", "emptyDir": {}},
        {"name": "buildkit-state", "emptyDir": {}},
    ]
    volume_mounts = [
        {"name": "workspace", "mountPath": "/workspace"},
        {
            "name": "buildkit-state",
            "mountPath": "/home/user/.local/share/buildkit",
        },
    ]
    if registry_secret_name:
        volumes.append(
            {
                "name": "registry-auth",
                "secret": {
                    "secretName": registry_secret_name,
                    "items": [{"key": ".dockerconfigjson", "path": "config.json"}],
                },
            }
        )
        volume_mounts.append(
            {
                "name": "registry-auth",
                "mountPath": "/home/user/.docker",
                "readOnly": True,
            }
        )

    build_script = """set -eu
set --
[ -z "${HTTP_PROXY:-}" ] || set -- "$@" --opt "build-arg:HTTP_PROXY=$HTTP_PROXY"
[ -z "${HTTPS_PROXY:-}" ] || set -- "$@" --opt "build-arg:HTTPS_PROXY=$HTTPS_PROXY"
[ -z "${http_proxy:-}" ] || set -- "$@" --opt "build-arg:http_proxy=$http_proxy"
[ -z "${https_proxy:-}" ] || set -- "$@" --opt "build-arg:https_proxy=$https_proxy"
[ -z "${NO_PROXY:-}" ] || set -- "$@" --opt "build-arg:NO_PROXY=$NO_PROXY"
[ -z "${no_proxy:-}" ] || set -- "$@" --opt "build-arg:no_proxy=$no_proxy"
[ -z "${PIP_INDEX_URL:-}" ] || set -- "$@" --opt "build-arg:PIP_INDEX_URL=$PIP_INDEX_URL"
[ -z "${PIP_TRUSTED_HOST:-}" ] || set -- "$@" --opt "build-arg:PIP_TRUSTED_HOST=$PIP_TRUSTED_HOST"
[ -z "${NPM_REGISTRY:-}" ] || set -- "$@" --opt "build-arg:NPM_REGISTRY=$NPM_REGISTRY"
[ -z "${APT_MIRROR:-}" ] || set -- "$@" --opt "build-arg:APT_MIRROR=$APT_MIRROR"
exec buildctl-daemonless.sh build \\
  --frontend dockerfile.v0 \\
  --local context=\"$BUILD_CONTEXT\" \\
  --local dockerfile=\"$DOCKERFILE_DIR\" \\
  --opt filename=Dockerfile \\
  --opt platform=linux/amd64 \\
  --opt \"build-arg:$VERSION_ARG_NAME=$VERSION_ARG_VALUE\" \\
  --opt \"build-arg:IMAGE_VERSION=$IMAGE_TAG\" \\
  \"$@\" --opt \"build-arg:BASE_IMAGE_REGISTRY=$BASE_IMAGE_REGISTRY\" --output \"type=image,name=$IMAGE_REFERENCE,push=true\"
"""
    source_script = """set -eu
attempt=1
while [ "$attempt" -le 3 ]; do
  rm -rf /workspace/source
  if git clone --depth 1 --filter=blob:none --sparse --branch "$SOURCE_REF" \
      -- "$SOURCE_REPOSITORY" /workspace/source &&
      git -C /workspace/source sparse-checkout set $SOURCE_PATHS; then
    exit 0
  fi
  if [ "$attempt" -eq 3 ]; then
    exit 1
  fi
  sleep $((attempt * 5))
  attempt=$((attempt + 1))
done
"""
    manifest = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": build.job_name,
            "namespace": build.namespace,
            "labels": labels,
        },
        "spec": {
            "backoffLimit": 0,
            "activeDeadlineSeconds": settings.IMAGE_BUILD_TIMEOUT_SECONDS,
            "ttlSecondsAfterFinished": settings.IMAGE_BUILD_TTL_SECONDS,
            "template": {
                "metadata": {
                    "labels": labels,
                    "annotations": {"container.apparmor.security.beta.kubernetes.io/builder": "unconfined"},
                },
                "spec": {
                    "restartPolicy": "Never",
                    "securityContext": {
                        "runAsUser": 1000,
                        "runAsGroup": 1000,
                        "fsGroup": 1000,
                        "seccompProfile": {"type": "Unconfined"},
                        "appArmorProfile": {"type": "Unconfined"},
                    },
                    "initContainers": [
                        {
                            "name": "source",
                            "image": settings.IMAGE_BUILD_GIT_IMAGE,
                            "imagePullPolicy": "IfNotPresent",
                            "command": ["/bin/sh", "-lc"],
                            "args": [source_script],
                            "env": [
                                {"name": "SOURCE_REF", "value": build.source_ref},
                                {
                                    "name": "SOURCE_REPOSITORY",
                                    "value": build.source_repository,
                                },
                                {"name": "SOURCE_PATHS", "value": source_paths},
                                *proxy_env,
                            ],
                            "volumeMounts": [{"name": "workspace", "mountPath": "/workspace"}],
                        }
                    ],
                    "containers": [
                        {
                            "name": "builder",
                            "image": settings.IMAGE_BUILDER_IMAGE,
                            "imagePullPolicy": "IfNotPresent",
                            "command": ["/bin/sh", "-lc"],
                            "args": [build_script],
                            "env": [
                                {
                                    "name": "BUILDKITD_FLAGS",
                                    "value": "--oci-worker-no-process-sandbox",
                                },
                                {"name": "DOCKER_CONFIG", "value": "/home/user/.docker"},
                                {"name": "BUILD_CONTEXT", "value": build_context},
                                {"name": "DOCKERFILE_DIR", "value": dockerfile_dir},
                                {"name": "VERSION_ARG_NAME", "value": version_arg_name},
                                {"name": "VERSION_ARG_VALUE", "value": version_arg_value},
                                {"name": "IMAGE_TAG", "value": build.image_tag},
                                {"name": "IMAGE_REFERENCE", "value": build.image_reference},
                                {
                                    "name": "BASE_IMAGE_REGISTRY",
                                    "value": settings.IMAGE_BUILD_BASE_IMAGE_REGISTRY,
                                },
                                *mirror_env,
                                *proxy_env,
                            ],
                            "resources": {
                                "requests": {
                                    "cpu": settings.IMAGE_BUILD_CPU_REQUEST,
                                    "memory": settings.IMAGE_BUILD_MEMORY_REQUEST,
                                },
                                "limits": {
                                    "cpu": settings.IMAGE_BUILD_CPU_LIMIT,
                                    "memory": settings.IMAGE_BUILD_MEMORY_LIMIT,
                                },
                            },
                            "volumeMounts": volume_mounts,
                        }
                    ],
                    "volumes": volumes,
                },
            },
        },
    }
    pod_spec = manifest["spec"]["template"]["spec"]
    proxy_url = settings.IMAGE_BUILD_PROXY_URL.strip()
    if proxy_url.startswith(("http://127.0.0.1:", "https://127.0.0.1:")):
        pod_spec["hostNetwork"] = True
        pod_spec["dnsPolicy"] = "ClusterFirstWithHostNet"
    return manifest


async def start_build(
    *,
    runtime: str,
    version: str,
    cluster_id: str,
    source_ref: str | None,
    release_notes: str | None,
    user_id: str,
    org_id: str,
    db: AsyncSession,
) -> ImageBuild:
    if runtime not in SUPPORTED_RUNTIMES or RUNTIME_REGISTRY.get(runtime) is None:
        raise BadRequestError(
            f"不支持构建运行时 {runtime}",
            "errors.image_build.unsupported_runtime",
        )
    normalized_version = normalize_version(version)
    effective_source_ref = validate_source_ref(source_ref or settings.IMAGE_BUILD_SOURCE_REF)
    source_repository = settings.IMAGE_BUILD_SOURCE_REPOSITORY.strip()
    if not source_repository:
        raise BadRequestError(
            "未配置镜像构建源码仓库",
            "errors.image_build.source_repository_missing",
        )

    existing_version = await db.execute(
        select(EngineVersion).where(
            EngineVersion.runtime == runtime,
            EngineVersion.version == normalized_version,
            not_deleted(EngineVersion),
        )
    )
    if existing_version.scalar_one_or_none():
        raise ConflictError(
            f"版本 {normalized_version} 已发布，无需重复构建",
            "errors.image_build.version_already_published",
        )

    from app.services import cluster_service

    cluster = await cluster_service.get_cluster(cluster_id, db, org_id)
    k8s = await require_k8s_client(cluster)
    registry_config = await registry_service.resolve_registry_config(db, runtime)
    image_repository = registry_config.image_registry
    if not image_repository:
        raise BadRequestError(
            "请先在镜像仓库设置中配置当前引擎的目标仓库",
            "errors.image_build.registry_missing",
        )
    if registry_config.mode == "hosted" and not registry_config.credentials:
        raise BadRequestError(
            "团队托管仓库缺少推送凭证，请联系平台管理员补充配置",
            "errors.image_build.hosted_registry_credentials_missing",
        )

    image_tag = f"v{normalized_version}"
    active = await db.execute(
        select(ImageBuild).where(
            ImageBuild.image_repository == image_repository,
            ImageBuild.image_tag == image_tag,
            ImageBuild.status.in_(ACTIVE_STATUSES),
            not_deleted(ImageBuild),
        )
    )
    if active.scalar_one_or_none():
        raise ConflictError(
            f"镜像 {image_repository}:{image_tag} 正在构建",
            "errors.image_build.already_running",
        )

    build = ImageBuild(
        org_id=org_id,
        cluster_id=cluster.id,
        requested_by=user_id,
        runtime=runtime,
        version=normalized_version,
        image_repository=image_repository,
        image_tag=image_tag,
        source_repository=source_repository,
        source_ref=effective_source_ref,
        namespace=settings.IMAGE_BUILD_NAMESPACE,
        job_name="pending",
        status="pending",
        release_notes=release_notes,
    )
    db.add(build)
    await db.flush()
    build.job_name = f"nodeskclaw-build-{runtime}-{build.id[:8]}"

    try:
        await k8s.ensure_namespace(
            build.namespace,
            {"nodeskclaw/component": "image-builder"},
        )
        registry_secret_name = None
        if registry_config.credentials:
            registry_secret_name = f"{build.job_name}-auth"
            await registry_service.ensure_registry_pull_secret(
                k8s,
                build.namespace,
                registry_config,
                secret_name=registry_secret_name,
            )
        manifest = build_image_job_manifest(
            build,
            registry_secret_name=registry_secret_name,
        )
        created_job = await k8s.create_job(build.namespace, manifest)
        if registry_secret_name:
            try:
                await k8s.core.patch_namespaced_secret(
                    registry_secret_name,
                    build.namespace,
                    {
                        "metadata": {
                            "ownerReferences": [
                                {
                                    "apiVersion": "batch/v1",
                                    "kind": "Job",
                                    "name": build.job_name,
                                    "uid": created_job.metadata.uid,
                                    "controller": False,
                                    "blockOwnerDeletion": False,
                                }
                            ]
                        }
                    },
                )
            except Exception:
                logger.warning(
                    "无法为镜像仓库 Secret 设置 Job 所有者: build_id=%s",
                    build.id,
                    exc_info=True,
                )
        build.status = "running"
        build.started_at = datetime.now(timezone.utc)
        await db.flush()
    except Exception as exc:
        logger.exception("创建镜像构建任务失败: build_id=%s", build.id)
        build.status = "failed"
        build.error_message = _safe_error_message(exc)
        build.finished_at = datetime.now(timezone.utc)
        await db.commit()
        raise BadRequestError(
            "无法在所选集群启动镜像构建，请检查集群连接和权限",
            "errors.image_build.job_create_failed",
        ) from exc
    return build


async def list_builds(
    *,
    org_id: str,
    db: AsyncSession,
    runtime: str | None = None,
) -> list[ImageBuild]:
    query = select(ImageBuild).where(
        ImageBuild.org_id == org_id,
        not_deleted(ImageBuild),
    )
    if runtime:
        query = query.where(ImageBuild.runtime == runtime)
    result = await db.execute(query.order_by(ImageBuild.created_at.desc()).limit(50))
    return list(result.scalars().all())


async def get_build(build_id: str, *, org_id: str, db: AsyncSession) -> ImageBuild:
    result = await db.execute(
        select(ImageBuild).where(
            ImageBuild.id == build_id,
            ImageBuild.org_id == org_id,
            not_deleted(ImageBuild),
        )
    )
    build = result.scalar_one_or_none()
    if build is None:
        raise NotFoundError("镜像构建任务不存在", "errors.image_build.not_found")
    return build


async def refresh_build(build: ImageBuild, db: AsyncSession) -> ImageBuild:
    if build.status in TERMINAL_STATUSES:
        return build

    from app.services import cluster_service

    cluster = await cluster_service.get_cluster(build.cluster_id, db, build.org_id)
    k8s = await require_k8s_client(cluster)
    try:
        job = await k8s.get_job(build.namespace, build.job_name)
    except ApiException as exc:
        if exc.status == 404:
            build.status = "failed"
            build.error_message = "K8s 构建任务已不存在"
            build.finished_at = datetime.now(timezone.utc)
            await db.flush()
            return build
        raise

    status = job.status
    if status.start_time and build.started_at is None:
        build.started_at = status.start_time

    conditions = status.conditions or []
    completed = any(c.type == "Complete" and c.status == "True" for c in conditions)
    failed = any(c.type == "Failed" and c.status == "True" for c in conditions)
    if completed or (status.succeeded or 0) > 0:
        build.status = "succeeded"
        build.finished_at = status.completion_time or datetime.now(timezone.utc)
        await _publish_completed_build(build, db)
    elif failed or (status.failed or 0) > 0:
        build.status = "failed"
        build.finished_at = status.completion_time or datetime.now(timezone.utc)
        build.error_message = _job_failure_message(conditions)
    elif (status.active or 0) > 0:
        build.status = "running"

    await _refresh_logs(build, k8s)
    await db.flush()
    return build


async def refresh_build_logs(build: ImageBuild, db: AsyncSession) -> ImageBuild:
    refreshed = await refresh_build(build, db)
    if refreshed.status in TERMINAL_STATUSES and not refreshed.log_text:
        from app.services import cluster_service

        cluster = await cluster_service.get_cluster(build.cluster_id, db, build.org_id)
        k8s = await require_k8s_client(cluster)
        await _refresh_logs(refreshed, k8s)
        await db.flush()
    return refreshed


async def _refresh_logs(build: ImageBuild, k8s) -> None:
    pods = await k8s.list_pods(
        build.namespace,
        label_selector=f"job-name={build.job_name}",
    )
    if not pods:
        return
    pod_name = pods[0]["name"]
    log_sections = []
    for container_name, heading in (("source", "Source"), ("builder", "BuildKit")):
        try:
            log_text = await k8s.get_pod_logs(
                build.namespace,
                pod_name,
                container=container_name,
                tail_lines=5000,
            )
        except ApiException as exc:
            if exc.status in {400, 404}:
                continue
            raise
        if log_text:
            log_sections.append(f"[{heading}]\n{log_text}")
    if log_sections:
        build.log_text = "\n\n".join(log_sections)[-_LOG_LIMIT:]


async def _publish_completed_build(build: ImageBuild, db: AsyncSession) -> None:
    if build.engine_version_id:
        return
    existing = await db.execute(
        select(EngineVersion).where(
            EngineVersion.runtime == build.runtime,
            EngineVersion.version == build.version,
            not_deleted(EngineVersion),
        )
    )
    engine_version = existing.scalar_one_or_none()
    if engine_version is None:
        engine_version = await engine_version_service.publish(
            runtime=build.runtime,
            version=build.version,
            image_tag=build.image_tag,
            release_notes=build.release_notes,
            user_id=build.requested_by,
            db=db,
        )
    build.engine_version_id = engine_version.id


def _job_failure_message(conditions) -> str:
    for condition in reversed(conditions):
        if condition.type == "Failed" and condition.status == "True":
            return condition.message or condition.reason or "K8s 构建任务失败"
    return "K8s 构建任务失败，请查看构建日志"


def _safe_error_message(exc: Exception) -> str:
    if isinstance(exc, ApiException):
        return f"K8s API {exc.status or ''} {exc.reason or '请求失败'}".strip()
    return str(exc)[:1000] or exc.__class__.__name__
