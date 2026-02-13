"""Instance service: list, detail, delete, scale, restart, config save/apply."""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.cluster import Cluster
from app.models.deploy_record import DeployAction, DeployRecord, DeployStatus
from app.models.instance import Instance, InstanceStatus
from app.schemas.deploy import DeployRecordInfo
from app.schemas.instance import InstanceDetail, InstanceInfo, UpdateConfigRequest
from app.services.k8s.client_manager import k8s_manager
from app.services.k8s.k8s_client import K8sClient
from app.services.k8s.resource_builder import build_configmap, build_labels

logger = logging.getLogger(__name__)


async def list_instances(db: AsyncSession, cluster_id: str | None = None) -> list[InstanceInfo]:
    query = select(Instance).order_by(Instance.created_at.desc())
    if cluster_id:
        query = query.where(Instance.cluster_id == cluster_id)
    result = await db.execute(query)
    return [InstanceInfo.model_validate(i) for i in result.scalars().all()]


async def get_instance(instance_id: str, db: AsyncSession) -> Instance:
    result = await db.execute(select(Instance).where(Instance.id == instance_id))
    instance = result.scalar_one_or_none()
    if not instance:
        raise NotFoundError("实例不存在")
    return instance


async def get_instance_detail(instance_id: str, db: AsyncSession) -> InstanceDetail:
    """Get instance info enriched with live K8s pod data."""
    instance = await get_instance(instance_id, db)

    # Get cluster for k8s connection
    cluster_result = await db.execute(select(Cluster).where(Cluster.id == instance.cluster_id))
    cluster = cluster_result.scalar_one_or_none()

    detail = InstanceDetail(
        **InstanceInfo.model_validate(instance).model_dump(),
        cpu_request=instance.cpu_request,
        cpu_limit=instance.cpu_limit,
        mem_request=instance.mem_request,
        mem_limit=instance.mem_limit,
        env_vars=json.loads(instance.env_vars) if instance.env_vars else {},
    )

    if cluster and cluster.kubeconfig_encrypted:
        try:
            api_client = await k8s_manager.get_or_create(cluster.id, cluster.kubeconfig_encrypted)
            k8s = K8sClient(api_client)
            label_selector = f"app.kubernetes.io/name={instance.name}"
            pods = await k8s.list_pods(instance.namespace, label_selector)
            detail.pods = [
                {
                    "name": p["name"],
                    "status": p["phase"],
                    "node": p.get("node"),
                    "ip": p.get("ip"),
                    "restart_count": sum(c.get("restart_count", 0) for c in p.get("containers", [])),
                    "containers": [
                        {
                            "name": c["name"],
                            "image": "",
                            "ready": c.get("ready", False),
                            "restart_count": c.get("restart_count", 0),
                            "state": c.get("state", "unknown"),
                        }
                        for c in p.get("containers", [])
                    ],
                }
                for p in pods
            ]
        except Exception as e:
            logger.warning("Failed to fetch pods for instance %s: %s", instance_id, e)

    return detail


async def delete_instance(instance_id: str, db: AsyncSession, delete_k8s: bool = True):
    """Delete instance from DB and optionally from K8s."""
    instance = await get_instance(instance_id, db)

    if delete_k8s:
        cluster_result = await db.execute(select(Cluster).where(Cluster.id == instance.cluster_id))
        cluster = cluster_result.scalar_one_or_none()
        if cluster and cluster.kubeconfig_encrypted:
            try:
                api_client = await k8s_manager.get_or_create(cluster.id, cluster.kubeconfig_encrypted)
                k8s = K8sClient(api_client)
                # Delete deployment and service
                try:
                    await k8s.apps.delete_namespaced_deployment(instance.name, instance.namespace)
                except Exception:
                    pass
                try:
                    await k8s.core.delete_namespaced_service(instance.name, instance.namespace)
                except Exception:
                    pass
                # PVC is NOT deleted by default (user data protection)
            except Exception as e:
                logger.warning("Failed to delete K8s resources for %s: %s", instance.name, e)

    await db.delete(instance)
    await db.commit()


async def scale_instance(instance_id: str, replicas: int, db: AsyncSession):
    instance = await get_instance(instance_id, db)
    cluster_result = await db.execute(select(Cluster).where(Cluster.id == instance.cluster_id))
    cluster = cluster_result.scalar_one_or_none()
    if not cluster:
        raise NotFoundError("集群不存在")

    api_client = await k8s_manager.get_or_create(cluster.id, cluster.kubeconfig_encrypted)
    k8s = K8sClient(api_client)
    await k8s.scale_deployment(instance.namespace, instance.name, replicas)

    instance.replicas = replicas
    await db.commit()


async def restart_instance(instance_id: str, db: AsyncSession):
    instance = await get_instance(instance_id, db)
    cluster_result = await db.execute(select(Cluster).where(Cluster.id == instance.cluster_id))
    cluster = cluster_result.scalar_one_or_none()
    if not cluster:
        raise NotFoundError("集群不存在")

    api_client = await k8s_manager.get_or_create(cluster.id, cluster.kubeconfig_encrypted)
    k8s = K8sClient(api_client)
    await k8s.restart_deployment(instance.namespace, instance.name)


async def get_deploy_history(instance_id: str, db: AsyncSession) -> list[DeployRecordInfo]:
    result = await db.execute(
        select(DeployRecord)
        .where(DeployRecord.instance_id == instance_id)
        .order_by(DeployRecord.created_at.desc())
    )
    return [DeployRecordInfo.model_validate(r) for r in result.scalars().all()]


async def get_pod_logs(
    instance_id: str, pod_name: str, db: AsyncSession, container: str | None = None, tail_lines: int = 200
) -> str:
    instance = await get_instance(instance_id, db)
    cluster_result = await db.execute(select(Cluster).where(Cluster.id == instance.cluster_id))
    cluster = cluster_result.scalar_one_or_none()
    if not cluster:
        raise NotFoundError("集群不存在")

    api_client = await k8s_manager.get_or_create(cluster.id, cluster.kubeconfig_encrypted)
    k8s = K8sClient(api_client)
    return await k8s.get_pod_logs(instance.namespace, pod_name, container, tail_lines)


# ────────────────────────────────────────────────────────────
# 两步操作模式: save_config (仅存 DB) + apply_config (执行 K8s)
# ────────────────────────────────────────────────────────────

async def save_config(
    instance_id: str, req: UpdateConfigRequest, db: AsyncSession
) -> InstanceInfo:
    """
    Step 1: 仅保存配置变更到 pending_config，不执行 K8s 操作。
    """
    instance = await get_instance(instance_id, db)

    pending = {
        "image_version": req.image_version,
        "cpu_request": req.cpu_request,
        "cpu_limit": req.cpu_limit,
        "mem_request": req.mem_request,
        "mem_limit": req.mem_limit,
        "env_vars": req.env_vars,
        "replicas": req.replicas,
        "advanced_config": req.advanced_config,
    }
    # 过滤掉 None 值，仅保留用户确实修改的字段
    pending = {k: v for k, v in pending.items() if v is not None}

    if not pending:
        return InstanceInfo.model_validate(instance)

    instance.pending_config = json.dumps(pending)
    await db.commit()
    await db.refresh(instance)
    return InstanceInfo.model_validate(instance)


async def apply_config(
    instance_id: str, user_id: str, db: AsyncSession
) -> InstanceInfo:
    """
    Step 2: 读取 pending_config，执行 K8s 滚动更新，成功后清空 pending_config。
    """
    instance = await get_instance(instance_id, db)

    if not instance.pending_config:
        raise NotFoundError("没有待应用的配置变更")

    pending = json.loads(instance.pending_config)
    req = UpdateConfigRequest(**pending)

    result = await _execute_config_update(instance, req, user_id, db)

    # 清空 pending_config
    instance.pending_config = None
    await db.commit()
    await db.refresh(instance)
    return result


async def update_config(
    instance_id: str, req: UpdateConfigRequest, user_id: str, db: AsyncSession
) -> InstanceInfo:
    """兼容旧接口: 直接保存 + 应用（供回滚等场景使用）。"""
    instance = await get_instance(instance_id, db)
    return await _execute_config_update(instance, req, user_id, db)


async def _execute_config_update(
    instance: Instance, req: UpdateConfigRequest, user_id: str, db: AsyncSession
) -> InstanceInfo:
    """内部方法: 真正执行配置变更 + K8s 滚动更新。"""
    cluster_result = await db.execute(select(Cluster).where(Cluster.id == instance.cluster_id))
    cluster = cluster_result.scalar_one_or_none()
    if not cluster:
        raise NotFoundError("集群不存在")

    # 保存旧配置快照
    old_snapshot = {
        "image_version": instance.image_version,
        "cpu_request": instance.cpu_request,
        "cpu_limit": instance.cpu_limit,
        "mem_request": instance.mem_request,
        "mem_limit": instance.mem_limit,
        "replicas": instance.replicas,
        "env_vars": instance.env_vars,
        "advanced_config": instance.advanced_config,
    }

    # 应用变更到 DB
    changed = False
    if req.image_version and req.image_version != instance.image_version:
        instance.image_version = req.image_version
        changed = True
    if req.cpu_request:
        instance.cpu_request = req.cpu_request
        changed = True
    if req.cpu_limit:
        instance.cpu_limit = req.cpu_limit
        changed = True
    if req.mem_request:
        instance.mem_request = req.mem_request
        changed = True
    if req.mem_limit:
        instance.mem_limit = req.mem_limit
        changed = True
    if req.replicas is not None and req.replicas != instance.replicas:
        instance.replicas = req.replicas
        changed = True
    if req.env_vars is not None:
        instance.env_vars = json.dumps(req.env_vars) if req.env_vars else None
        changed = True
    if req.advanced_config is not None:
        instance.advanced_config = json.dumps(req.advanced_config)
        changed = True

    if not changed:
        return InstanceInfo.model_validate(instance)

    instance.status = InstanceStatus.updating

    # 创建部署记录
    max_rev = await db.execute(
        select(func.coalesce(func.max(DeployRecord.revision), 0)).where(
            DeployRecord.instance_id == instance.id
        )
    )
    next_rev = max_rev.scalar() + 1

    record = DeployRecord(
        instance_id=instance.id,
        revision=next_rev,
        action=DeployAction.upgrade,
        image_version=instance.image_version,
        replicas=instance.replicas,
        config_snapshot=json.dumps(old_snapshot),
        status=DeployStatus.running,
        triggered_by=user_id,
        started_at=datetime.now(timezone.utc),
    )
    db.add(record)
    await db.commit()
    await db.refresh(instance)

    # 执行 K8s 滚动更新
    try:
        api_client = await k8s_manager.get_or_create(cluster.id, cluster.kubeconfig_encrypted)
        k8s = K8sClient(api_client)

        # Patch deployment
        from app.services.config_service import get_config

        image_registry = await get_config("image_registry", db) or "openclaw"
        image = f"{image_registry}:{instance.image_version}"
        patch_body = {
            "spec": {
                "replicas": instance.replicas,
                "template": {
                    "metadata": {
                        "annotations": {
                            "clawbuddy/updatedAt": datetime.now(timezone.utc).isoformat()
                        }
                    },
                    "spec": {
                        "containers": [{
                            "name": instance.name,
                            "image": image,
                            "resources": {
                                "requests": {"cpu": instance.cpu_request, "memory": instance.mem_request},
                                "limits": {"cpu": instance.cpu_limit, "memory": instance.mem_limit},
                            },
                        }]
                    },
                },
            }
        }
        await k8s.apps.patch_namespaced_deployment(instance.name, instance.namespace, patch_body)

        # Update ConfigMap if env_vars changed
        if req.env_vars is not None:
            labels = build_labels(instance.name, instance.id, instance.image_version)
            cm = build_configmap(f"{instance.name}-config", instance.namespace, req.env_vars, labels)
            try:
                await k8s.core.replace_namespaced_config_map(
                    f"{instance.name}-config", instance.namespace, cm
                )
            except Exception:
                await k8s.create_or_skip(
                    k8s.core.create_namespaced_config_map, instance.namespace, cm
                )

        instance.status = InstanceStatus.running
        instance.current_revision = next_rev
        record.status = DeployStatus.success
        record.finished_at = datetime.now(timezone.utc)
    except Exception as e:
        logger.exception("配置更新失败: %s", instance.name)
        instance.status = InstanceStatus.failed
        record.status = DeployStatus.failed
        record.message = str(e)[:500]
        record.finished_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(instance)
    return InstanceInfo.model_validate(instance)


async def rollback_instance(
    instance_id: str, target_revision: int, user_id: str, db: AsyncSession
) -> InstanceInfo:
    """回滚实例到指定版本。"""
    instance = await get_instance(instance_id, db)

    # 查找目标版本记录
    result = await db.execute(
        select(DeployRecord).where(
            DeployRecord.instance_id == instance_id,
            DeployRecord.revision == target_revision,
        )
    )
    target_record = result.scalar_one_or_none()
    if not target_record or not target_record.config_snapshot:
        raise NotFoundError("目标版本不存在或无配置快照")

    snapshot = json.loads(target_record.config_snapshot)

    # 构造 UpdateConfigRequest 从快照
    env_vars = snapshot.get("env_vars")
    if isinstance(env_vars, str):
        env_vars = json.loads(env_vars) if env_vars else {}

    req = UpdateConfigRequest(
        image_version=snapshot.get("image_version"),
        cpu_request=snapshot.get("cpu_request"),
        cpu_limit=snapshot.get("cpu_limit"),
        mem_request=snapshot.get("mem_request"),
        mem_limit=snapshot.get("mem_limit"),
        replicas=snapshot.get("replicas"),
        env_vars=env_vars,
    )

    return await update_config(instance_id, req, user_id, db)
