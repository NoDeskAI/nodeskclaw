"""Backup service: create / list / get / delete / restore / clone.

备份流程：从 Pod/Docker 打包运行时数据 -> 上传 S3
恢复流程：重建 K8s 资源 -> 从 S3 下载 -> 解压到 Pod/Docker
克隆流程：备份源 -> 部署新实例 -> 恢复备份到新实例
"""

import asyncio
import base64
import io
import json
import logging
import secrets
import tarfile
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models.backup import BackupStatus, BackupType, InstanceBackup
from app.models.cluster import Cluster
from app.models.deploy_record import DeployAction, DeployRecord, DeployStatus
from app.models.instance import Instance, InstanceStatus

logger = logging.getLogger(__name__)

TRANSITIONAL_STATUSES = {
    InstanceStatus.deploying,
    InstanceStatus.updating,
    InstanceStatus.rebuilding,
    InstanceStatus.restoring,
    InstanceStatus.deleting,
}

BACKUP_CHUNK_SIZE = 1_048_576  # 1MB per base64 chunk for K8s exec


def assert_not_transitional(instance: Instance) -> None:
    if instance.status in TRANSITIONAL_STATUSES:
        raise ConflictError(
            message=f"实例正在 {instance.status.value}，请等待完成后再操作",
            message_key="errors.instance.in_transitional_state",
        )


def _build_storage_key(instance_id: str, backup_id: str) -> str:
    return f"backups/{instance_id}/{backup_id}.tar.gz"


def _build_config_snapshot(instance: Instance) -> dict:
    return {
        "schema_version": 1,
        "name": instance.name,
        "slug": instance.slug,
        "image_version": instance.image_version,
        "replicas": instance.replicas,
        "cpu_request": instance.cpu_request,
        "cpu_limit": instance.cpu_limit,
        "mem_request": instance.mem_request,
        "mem_limit": instance.mem_limit,
        "env_vars": instance.env_vars,
        "advanced_config": instance.advanced_config,
        "storage_class": instance.storage_class,
        "storage_size": instance.storage_size,
        "service_type": instance.service_type,
        "llm_providers": instance.llm_providers,
        "compute_provider": instance.compute_provider,
        "runtime": instance.runtime,
    }


def _get_runtime_backup_config(runtime: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return (backup_dirs, exclude_patterns) from RuntimeSpec."""
    from app.services.runtime.registries.runtime_registry import RUNTIME_REGISTRY
    spec = RUNTIME_REGISTRY.get(runtime)
    if spec and spec.backup_dirs:
        return spec.backup_dirs, spec.backup_exclude_patterns
    if spec:
        rel = spec.data_dir_container_path.lstrip("/root/").lstrip("/")
        return (rel,), spec.backup_exclude_patterns
    return (".openclaw",), ("node_modules", "dist", "__pycache__", ".git", "cache", "*.pyc")


# ── CRUD ──────────────────────────────────────────────────

async def create_backup(
    instance_id: str, user_id: str, db: AsyncSession,
    org_id: str | None = None,
    backup_type: BackupType = BackupType.manual,
) -> InstanceBackup:
    """Create a backup record and kick off async backup task."""
    instance = await _load_instance(instance_id, db, org_id)
    assert_not_transitional(instance)
    if instance.status != InstanceStatus.running:
        raise BadRequestError(
            message="实例必须处于运行中才能创建备份",
            message_key="errors.backup.instance_not_running",
        )

    backup = InstanceBackup(
        instance_id=instance.id,
        type=backup_type,
        status=BackupStatus.pending,
        config_snapshot=json.dumps(_build_config_snapshot(instance)),
        triggered_by=user_id,
        org_id=instance.org_id,
    )
    db.add(backup)
    await db.commit()
    await db.refresh(backup)

    asyncio.create_task(_execute_backup(backup.id, instance.id))
    return backup


async def list_backups(instance_id: str, db: AsyncSession, org_id: str | None = None) -> list[InstanceBackup]:
    instance = await _load_instance(instance_id, db, org_id)
    result = await db.execute(
        select(InstanceBackup)
        .where(
            InstanceBackup.instance_id == instance.id,
            InstanceBackup.deleted_at.is_(None),
        )
        .order_by(InstanceBackup.created_at.desc())
    )
    return list(result.scalars().all())


async def get_backup(backup_id: str, db: AsyncSession) -> InstanceBackup:
    result = await db.execute(
        select(InstanceBackup).where(
            InstanceBackup.id == backup_id,
            InstanceBackup.deleted_at.is_(None),
        )
    )
    backup = result.scalar_one_or_none()
    if not backup:
        raise NotFoundError("备份不存在", message_key="errors.backup.not_found")
    return backup


async def delete_backup(backup_id: str, db: AsyncSession) -> None:
    backup = await get_backup(backup_id, db)

    if backup.storage_key:
        try:
            from app.services import storage_service
            await storage_service.delete_raw(backup.storage_key)
        except Exception:
            logger.warning("删除备份 S3 对象失败: key=%s", backup.storage_key, exc_info=True)

    backup.soft_delete()
    await db.commit()


# ── Restore ───────────────────────────────────────────────

async def restore_from_backup(
    instance_id: str, backup_id: str, user_id: str, db: AsyncSession,
    org_id: str | None = None,
) -> str:
    """Restore instance from backup. Returns deploy_record.id for SSE progress."""
    instance = await _load_instance(instance_id, db, org_id)
    assert_not_transitional(instance)

    backup = await get_backup(backup_id, db)
    if backup.instance_id != instance_id:
        raise BadRequestError(
            message="备份不属于该实例",
            message_key="errors.backup.wrong_instance",
        )
    if backup.status != BackupStatus.completed:
        raise BadRequestError(
            message="备份未完成",
            message_key="errors.backup.not_completed",
        )

    snapshot = json.loads(backup.config_snapshot) if backup.config_snapshot else {}
    if snapshot.get("schema_version", 1) > 1:
        raise BadRequestError(
            message="备份格式版本不兼容，请升级后端后重试",
            message_key="errors.backup.incompatible_schema",
        )

    instance.status = InstanceStatus.restoring
    await db.commit()

    max_rev = await db.execute(
        select(func.coalesce(func.max(DeployRecord.revision), 0)).where(
            DeployRecord.instance_id == instance.id, DeployRecord.deleted_at.is_(None)
        )
    )
    next_rev = max_rev.scalar() + 1
    record = DeployRecord(
        instance_id=instance.id,
        revision=next_rev,
        action=DeployAction.restore,
        image_version=instance.image_version,
        status=DeployStatus.running,
        triggered_by=user_id,
        started_at=datetime.now(timezone.utc),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    asyncio.create_task(_execute_restore(record.id, instance.id, backup.id))
    return record.id


# ── Clone ─────────────────────────────────────────────────

async def clone_instance(
    instance_id: str, new_name: str, user_id: str, db: AsyncSession,
    org_id: str | None = None, cluster_id: str | None = None,
) -> tuple[str, str]:
    """Clone instance. Returns (new_instance_id, deploy_record_id)."""
    instance = await _load_instance(instance_id, db, org_id)
    assert_not_transitional(instance)
    if instance.status != InstanceStatus.running:
        raise BadRequestError(
            message="实例必须处于运行中才能克隆",
            message_key="errors.clone.instance_not_running",
        )

    backup = await create_backup(instance_id, user_id, db, org_id, BackupType.manual)

    target_cluster_id = cluster_id or instance.cluster_id
    env_vars = json.loads(instance.env_vars) if instance.env_vars else {}
    new_token = secrets.token_hex(24)
    env_vars["GATEWAY_TOKEN"] = new_token
    env_vars["OPENCLAW_GATEWAY_TOKEN"] = new_token
    env_vars["NODESKCLAW_TOKEN"] = new_token

    from app.schemas.deploy import DeployRequest
    from app.models.user import User

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one()

    deploy_req = DeployRequest(
        name=new_name,
        cluster_id=target_cluster_id,
        image_version=instance.image_version,
        replicas=instance.replicas,
        cpu_request=instance.cpu_request,
        cpu_limit=instance.cpu_limit,
        mem_request=instance.mem_request,
        mem_limit=instance.mem_limit,
        storage_class=instance.storage_class,
        storage_size=instance.storage_size,
        runtime=instance.runtime,
        env_vars=env_vars,
        advanced_config=json.loads(instance.advanced_config) if instance.advanced_config else None,
    )

    from app.services.deploy_service import deploy_instance, execute_deploy_pipeline, register_deploy_task
    deploy_id, ctx = await deploy_instance(deploy_req, user, db, org_id)

    task = asyncio.create_task(
        _execute_clone_pipeline(ctx, backup.id, deploy_id)
    )
    register_deploy_task(deploy_id, task)

    new_inst_result = await db.execute(
        select(Instance).where(Instance.id == ctx.instance_id, Instance.deleted_at.is_(None))
    )
    new_instance = new_inst_result.scalar_one()

    return new_instance.id, deploy_id


# ── Internal: backup execution ────────────────────────────

async def _execute_backup(backup_id: str, instance_id: str) -> None:
    from app.core.deps import async_session_factory

    try:
        async with async_session_factory() as db:
            backup = (await db.execute(
                select(InstanceBackup).where(InstanceBackup.id == backup_id)
            )).scalar_one()
            backup.status = BackupStatus.in_progress
            await db.commit()

            instance = (await db.execute(
                select(Instance).where(Instance.id == instance_id, Instance.deleted_at.is_(None))
            )).scalar_one()

            backup_dirs, exclude_patterns = _get_runtime_backup_config(instance.runtime)
            storage_key = _build_storage_key(instance_id, backup_id)

            if instance.compute_provider == "docker":
                data = await _backup_docker(instance, backup_dirs, exclude_patterns)
            else:
                data = await _backup_k8s(instance, db, backup_dirs, exclude_patterns)

            from app.services import storage_service
            await storage_service.upload_raw(storage_key, data)

            backup.storage_key = storage_key
            backup.data_size = len(data)
            backup.status = BackupStatus.completed
            backup.completed_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info("备份完成: backup_id=%s instance=%s size=%d", backup_id, instance.name, len(data))

    except Exception as e:
        logger.exception("备份失败: backup_id=%s", backup_id)
        try:
            async with async_session_factory() as db:
                backup = (await db.execute(
                    select(InstanceBackup).where(InstanceBackup.id == backup_id)
                )).scalar_one()
                backup.status = BackupStatus.failed
                backup.message = str(e)[:500]
                await db.commit()
        except Exception:
            logger.exception("更新备份失败状态时出错")


async def _backup_k8s(
    instance: Instance, db: AsyncSession,
    backup_dirs: tuple[str, ...], exclude_patterns: tuple[str, ...],
) -> bytes:
    """Backup K8s instance via kubectl exec + base64 chunked transfer."""
    cluster = (await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id)
    )).scalar_one()
    from app.services.runtime.registries.compute_registry import require_k8s_client
    k8s = await require_k8s_client(cluster)

    pod_name = await _find_pod(k8s, instance.namespace, instance.slug or instance.name)

    exclude_args = []
    for pat in exclude_patterns:
        exclude_args.extend(["--exclude", pat])

    tar_cmd = ["tar", "czf", "/tmp/backup.tar.gz", "-C", "/root"] + list(backup_dirs) + exclude_args
    await k8s.exec_in_pod(instance.namespace, pod_name, tar_cmd)

    size_output = await k8s.exec_in_pod(
        instance.namespace, pod_name,
        ["stat", "-c", "%s", "/tmp/backup.tar.gz"],
    )
    file_size = int(size_output.strip())

    chunks: list[bytes] = []
    offset = 0
    while offset < file_size:
        chunk_cmd = [
            "bash", "-c",
            f"dd if=/tmp/backup.tar.gz bs={BACKUP_CHUNK_SIZE} skip={offset // BACKUP_CHUNK_SIZE} count=1 2>/dev/null | base64",
        ]
        b64_chunk = await k8s.exec_in_pod(instance.namespace, pod_name, chunk_cmd)
        chunks.append(base64.b64decode(b64_chunk.strip()))
        offset += BACKUP_CHUNK_SIZE

    await k8s.exec_in_pod(instance.namespace, pod_name, ["rm", "-f", "/tmp/backup.tar.gz"])
    return b"".join(chunks)


async def _backup_docker(
    instance: Instance,
    backup_dirs: tuple[str, ...], exclude_patterns: tuple[str, ...],
) -> bytes:
    """Backup Docker instance from host filesystem."""
    from app.services.docker_constants import DOCKER_DATA_DIR

    slug = instance.slug or instance.name
    data_root = DOCKER_DATA_DIR / slug / "data"

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for d in backup_dirs:
            full_path = data_root / d
            if full_path.exists():
                tar.add(
                    str(full_path), arcname=d,
                    filter=lambda ti: None if any(p in ti.name for p in exclude_patterns) else ti,
                )
    return buf.getvalue()


# ── Internal: restore execution ───────────────────────────

async def _execute_restore(record_id: str, instance_id: str, backup_id: str) -> None:
    from app.core.deps import async_session_factory
    from app.services.config_service import get_config
    from app.services.deploy_service import (
        REBUILD_STEPS, execute_rebuild_pipeline, _DeployContext,
    )

    try:
        async with async_session_factory() as db:
            instance = (await db.execute(
                select(Instance).where(Instance.id == instance_id, Instance.deleted_at.is_(None))
            )).scalar_one()
            cluster = (await db.execute(
                select(Cluster).where(Cluster.id == instance.cluster_id)
            )).scalar_one()
            backup = (await db.execute(
                select(InstanceBackup).where(InstanceBackup.id == backup_id)
            )).scalar_one()

            env_vars = json.loads(instance.env_vars) if instance.env_vars else {}
            advanced = json.loads(instance.advanced_config) if instance.advanced_config else None

            ctx = _DeployContext(
                record_id=record_id,
                instance_id=instance.id,
                cluster_id=cluster.id,
                name=instance.slug or instance.name,
                namespace=instance.namespace,
                image_version=instance.image_version,
                replicas=instance.replicas,
                cpu_request=instance.cpu_request,
                cpu_limit=instance.cpu_limit,
                mem_request=instance.mem_request,
                mem_limit=instance.mem_limit,
                storage_class=instance.storage_class,
                storage_size=instance.storage_size,
                quota_cpu=instance.quota_cpu,
                quota_mem=instance.quota_mem,
                env_vars=env_vars,
                advanced_config=advanced,
                proxy_endpoint=cluster.proxy_endpoint,
                org_id=instance.org_id,
                compute_provider=instance.compute_provider,
                runtime=instance.runtime,
            )

        await execute_rebuild_pipeline(ctx)

        async with async_session_factory() as db:
            inst = (await db.execute(
                select(Instance).where(Instance.id == instance_id, Instance.deleted_at.is_(None))
            )).scalar_one()

            if inst.status == InstanceStatus.running:
                from app.services import storage_service
                data = await storage_service.download_raw(backup.storage_key)

                if inst.compute_provider == "docker":
                    await _restore_docker_data(inst, data)
                else:
                    await _restore_k8s_data(inst, db, data)

                from app.services.runtime.registries.compute_registry import require_k8s_client
                if inst.compute_provider != "docker":
                    c = (await db.execute(select(Cluster).where(Cluster.id == inst.cluster_id))).scalar_one()
                    k8s = await require_k8s_client(c)
                    pod = await _find_pod(k8s, inst.namespace, inst.slug or inst.name)
                    await k8s.exec_in_pod(inst.namespace, pod, ["kill", "1"])
                    logger.info("恢复数据后重启 Pod: %s/%s", inst.namespace, pod)
            else:
                logger.warning("恢复重建阶段失败，跳过数据恢复: instance=%s status=%s", inst.name, inst.status)

    except Exception as e:
        logger.exception("恢复失败: instance_id=%s", instance_id)
        try:
            async with async_session_factory() as db:
                rec = (await db.execute(
                    select(DeployRecord).where(DeployRecord.id == record_id, DeployRecord.deleted_at.is_(None))
                )).scalar_one()
                rec.status = DeployStatus.failed
                rec.message = str(e)[:500]
                rec.finished_at = datetime.now(timezone.utc)
                inst = (await db.execute(
                    select(Instance).where(Instance.id == instance_id, Instance.deleted_at.is_(None))
                )).scalar_one()
                inst.status = InstanceStatus.failed
                await db.commit()
        except Exception:
            logger.exception("更新恢复失败状态时出错")


async def _restore_k8s_data(instance: Instance, db: AsyncSession, data: bytes) -> None:
    cluster = (await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id)
    )).scalar_one()
    from app.services.runtime.registries.compute_registry import require_k8s_client
    k8s = await require_k8s_client(cluster)
    pod = await _find_pod(k8s, instance.namespace, instance.slug or instance.name)

    encoded = base64.b64encode(data).decode("ascii")
    chunk_size = 98_000
    tmp_b64 = "/tmp/backup.b64"

    await k8s.exec_in_pod(instance.namespace, pod, ["rm", "-f", tmp_b64])
    for i in range(0, len(encoded), chunk_size):
        chunk = encoded[i:i + chunk_size]
        await k8s.exec_in_pod(
            instance.namespace, pod,
            ["bash", "-c", f"printf '%s' '{chunk}' >> {tmp_b64}"],
        )

    await k8s.exec_in_pod(
        instance.namespace, pod,
        ["bash", "-c", f"base64 -d {tmp_b64} > /tmp/backup.tar.gz && tar xzf /tmp/backup.tar.gz -C /root && rm -f /tmp/backup.tar.gz {tmp_b64}"],
    )


async def _restore_docker_data(instance: Instance, data: bytes) -> None:
    from app.services.docker_constants import DOCKER_DATA_DIR
    slug = instance.slug or instance.name
    data_root = DOCKER_DATA_DIR / slug / "data"

    buf = io.BytesIO(data)
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        tar.extractall(path=str(data_root))


# ── Internal: clone pipeline ──────────────────────────────

async def _execute_clone_pipeline(ctx, backup_id: str, deploy_id: str) -> None:
    """Deploy new instance, then wait for backup + restore data."""
    from app.core.deps import async_session_factory
    from app.services.deploy_service import execute_deploy_pipeline

    await execute_deploy_pipeline(ctx)

    async with async_session_factory() as db:
        new_inst = (await db.execute(
            select(Instance).where(Instance.id == ctx.instance_id, Instance.deleted_at.is_(None))
        )).scalar_one_or_none()
        if not new_inst or new_inst.status != InstanceStatus.running:
            logger.warning("克隆目标实例部署未成功，跳过数据恢复: %s", ctx.instance_id)
            return

        backup = await _wait_for_backup(backup_id)
        if not backup or backup.status != BackupStatus.completed:
            logger.warning("克隆源备份未完成，跳过数据恢复: backup_id=%s", backup_id)
            return

        from app.services import storage_service
        data = await storage_service.download_raw(backup.storage_key)

        if new_inst.compute_provider == "docker":
            await _restore_docker_data(new_inst, data)
        else:
            await _restore_k8s_data(new_inst, db, data)

        if new_inst.compute_provider != "docker":
            cluster = (await db.execute(
                select(Cluster).where(Cluster.id == new_inst.cluster_id)
            )).scalar_one()
            from app.services.runtime.registries.compute_registry import require_k8s_client
            k8s = await require_k8s_client(cluster)
            pod = await _find_pod(k8s, new_inst.namespace, new_inst.slug or new_inst.name)
            await k8s.exec_in_pod(new_inst.namespace, pod, ["kill", "1"])

    logger.info("克隆完成: source_backup=%s new_instance=%s", backup_id, ctx.instance_id)


async def _wait_for_backup(backup_id: str, timeout: int = 600) -> InstanceBackup | None:
    from app.core.deps import async_session_factory
    elapsed = 0
    while elapsed < timeout:
        async with async_session_factory() as db:
            backup = (await db.execute(
                select(InstanceBackup).where(InstanceBackup.id == backup_id)
            )).scalar_one_or_none()
            if backup and backup.status in (BackupStatus.completed, BackupStatus.failed):
                return backup
        await asyncio.sleep(2)
        elapsed += 2
    return None


# ── Helpers ───────────────────────────────────────────────

async def _load_instance(
    instance_id: str, db: AsyncSession, org_id: str | None = None,
) -> Instance:
    result = await db.execute(
        select(Instance).where(Instance.id == instance_id, Instance.deleted_at.is_(None))
    )
    instance = result.scalar_one_or_none()
    if not instance:
        raise NotFoundError("实例不存在", message_key="errors.instance.not_found")
    if org_id and instance.org_id != org_id:
        raise NotFoundError("实例不存在", message_key="errors.instance.not_found")
    return instance


async def _find_pod(k8s, namespace: str, name: str) -> str:
    pods = await k8s.core.list_namespaced_pod(namespace, label_selector=f"app.kubernetes.io/name={name}")
    for pod in pods.items:
        if pod.status.phase == "Running":
            return pod.metadata.name
    raise BadRequestError(
        message=f"未找到运行中的 Pod: {namespace}/{name}",
        message_key="errors.backup.no_running_pod",
    )
