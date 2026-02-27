"""Instance service: list, detail, delete, scale, restart, config save/apply."""

import asyncio
import json
import logging
import re as _re
from datetime import datetime, timezone
from typing import Coroutine

from sqlalchemy import func, select, update
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

_background_tasks: set[asyncio.Task] = set()


def _fire_task(coro: Coroutine) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def _sanitize_name(name: str) -> str:
    """将实例名称清洗为 RFC 1123 格式（与 deploy_service 逻辑保持一致）。"""
    safe = _re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
    return _re.sub(r"-{2,}", "-", safe)


def _k8s_name(instance: Instance) -> str:
    """K8s 资源名：优先用 slug，兼容未迁移的旧实例回退到 name。"""
    return instance.slug or instance.name


async def check_slug_conflict(
    slug: str, org_id: str, db: AsyncSession
) -> dict:
    """检查实例标识（slug）在同一组织内是否冲突。"""
    result = await db.execute(
        select(Instance).where(
            Instance.slug == slug,
            Instance.org_id == org_id,
            Instance.deleted_at.is_(None),
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return {"conflict": True, "reason": f"实例标识 \"{slug}\" 在当前组织中已存在"}
    return {"conflict": False, "reason": ""}


async def list_instances(
    db: AsyncSession,
    cluster_id: str | None = None,
    org_id: str | None = None,
) -> list[InstanceInfo]:
    query = select(Instance).where(Instance.deleted_at.is_(None)).order_by(Instance.created_at.desc())
    if cluster_id:
        query = query.where(Instance.cluster_id == cluster_id)
    if org_id:
        query = query.where(Instance.org_id == org_id)
    result = await db.execute(query)
    return [InstanceInfo.model_validate(i) for i in result.scalars().all()]


async def get_instance(instance_id: str, db: AsyncSession) -> Instance:
    result = await db.execute(
        select(Instance).where(Instance.id == instance_id, Instance.deleted_at.is_(None))
    )
    instance = result.scalar_one_or_none()
    if not instance:
        raise NotFoundError("实例不存在")
    return instance


async def get_instance_detail(instance_id: str, db: AsyncSession) -> InstanceDetail:
    """Get instance info enriched with live K8s pod data."""
    instance = await get_instance(instance_id, db)

    # Get cluster for k8s connection
    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id, Cluster.deleted_at.is_(None))
    )
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
            label_selector = f"app.kubernetes.io/name={_k8s_name(instance)}"
            pods = await k8s.list_pods(instance.namespace, label_selector)
            detail.pods = [
                {
                    "name": p["name"],
                    "status": p["phase"],
                    "ready": all(c.get("ready", False) for c in p.get("containers", [])) and len(p.get("containers", [])) > 0,
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

            if instance.status == InstanceStatus.restarting:
                has_ready = any(
                    all(c.get("ready", False) for c in p.get("containers", []))
                    and len(p.get("containers", [])) > 0
                    for p in pods
                )
                if has_ready:
                    instance.status = InstanceStatus.running
                    await db.commit()
                    detail.status = InstanceStatus.running
                    logger.info("实例 %s 重启完成，状态恢复为 running", instance_id)
        except Exception as e:
            logger.warning("Failed to fetch pods for instance %s: %s", instance_id, e)

    return detail


async def delete_instance(instance_id: str, db: AsyncSession, delete_k8s: bool = True):
    """逻辑删除实例：标记 deleted_at，从 K8s 删除整个命名空间（级联删除所有资源）。"""
    instance = await get_instance(instance_id, db)

    if instance.workspace_id:
        from app.services.sse_listener import sse_listener_manager
        await sse_listener_manager.disconnect(instance_id)

    if delete_k8s:
        cluster_result = await db.execute(
            select(Cluster).where(Cluster.id == instance.cluster_id, Cluster.deleted_at.is_(None))
        )
        cluster = cluster_result.scalar_one_or_none()
        if cluster and cluster.kubeconfig_encrypted:
            try:
                api_client = await k8s_manager.get_or_create(cluster.id, cluster.kubeconfig_encrypted)
                k8s = K8sClient(api_client)
                try:
                    await k8s.core.delete_namespace(instance.namespace)
                    logger.info("已删除命名空间 %s（实例 %s）", instance.namespace, instance.name)
                except Exception:
                    logger.warning("删除命名空间 %s 失败，可能已不存在", instance.namespace)
            except Exception as e:
                logger.warning("删除实例 %s 的 K8s 资源失败: %s", instance.name, e)

            # 清理 infra 网关集群上的代理 Ingress
            if cluster and cluster.proxy_endpoint:
                try:
                    from app.services.k8s.client_manager import GATEWAY_NS
                    gateway_api = await k8s_manager.get_gateway_client()
                    gateway_k8s = K8sClient(gateway_api)
                    inst_name = instance.name
                    await gateway_k8s.networking.delete_namespaced_ingress(
                        f"proxy-{inst_name}", GATEWAY_NS,
                    )
                    logger.info("已清理网关代理 Ingress: proxy-%s", inst_name)
                except Exception:
                    logger.debug("清理网关代理 Ingress 失败（可能不存在）")

    # 逻辑删除实例
    instance.soft_delete()
    # 级联逻辑删除关联的部署记录
    await db.execute(
        update(DeployRecord)
        .where(DeployRecord.instance_id == instance.id, DeployRecord.deleted_at.is_(None))
        .values(deleted_at=func.now())
    )
    await db.commit()


async def scale_instance(instance_id: str, replicas: int, db: AsyncSession):
    instance = await get_instance(instance_id, db)
    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id, Cluster.deleted_at.is_(None))
    )
    cluster = cluster_result.scalar_one_or_none()
    if not cluster:
        raise NotFoundError("集群不存在")

    api_client = await k8s_manager.get_or_create(cluster.id, cluster.kubeconfig_encrypted)
    k8s = K8sClient(api_client)
    await k8s.scale_deployment(instance.namespace, _k8s_name(instance), replicas)

    instance.replicas = replicas
    await db.commit()


async def restart_instance(instance_id: str, db: AsyncSession):
    instance = await get_instance(instance_id, db)
    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id, Cluster.deleted_at.is_(None))
    )
    cluster = cluster_result.scalar_one_or_none()
    if not cluster:
        raise NotFoundError("集群不存在")

    prev_status = instance.status
    instance.status = InstanceStatus.restarting
    await db.commit()

    api_client = await k8s_manager.get_or_create(cluster.id, cluster.kubeconfig_encrypted)
    k8s = K8sClient(api_client)
    name = _k8s_name(instance)
    desired = instance.replicas or 1

    try:
        await k8s.scale_deployment(instance.namespace, name, 0)
        await k8s.scale_deployment(instance.namespace, name, desired)
    except Exception as e:
        logger.error("重启 scale 操作失败，回滚状态: instance=%s error=%s", instance.name, e)
        instance.status = prev_status
        await db.commit()
        raise

    logger.info("实例 %s (%s) 已触发重启 (scale 0->%d)", instance.name, instance_id, desired)
    _fire_task(_monitor_restart(instance_id, cluster.id, cluster.kubeconfig_encrypted, instance.namespace, name))


_RESTART_POLL_INTERVAL = 5
_RESTART_TIMEOUT = 120


def _broadcast_agent_status(workspace_id: str | None, instance_id: str, status: str) -> None:
    if not workspace_id:
        return
    try:
        from app.api.workspaces import broadcast_event
        broadcast_event(workspace_id, "agent:status", {
            "instance_id": instance_id,
            "status": status,
        })
    except Exception:
        logger.debug("广播 agent:status 失败: instance=%s", instance_id)


async def _monitor_restart(
    instance_id: str, cluster_id: str, kubeconfig_encrypted: str, namespace: str, deploy_name: str,
) -> None:
    """Poll K8s pod status after restart and update DB status when ready."""
    from app.core.deps import async_session_factory

    await asyncio.sleep(_RESTART_POLL_INTERVAL)

    elapsed = 0
    while elapsed < _RESTART_TIMEOUT:
        try:
            api_client = await k8s_manager.get_or_create(cluster_id, kubeconfig_encrypted)
            k8s = K8sClient(api_client)
            pods = await k8s.list_pods(namespace)
            has_ready = any(
                all(c.get("ready", False) for c in p.get("containers", []))
                and len(p.get("containers", [])) > 0
                for p in pods
            )
            if has_ready:
                async with async_session_factory() as db:
                    result = await db.execute(select(Instance).where(Instance.id == instance_id))
                    inst = result.scalar_one_or_none()
                    if inst and inst.status == InstanceStatus.restarting:
                        inst.status = InstanceStatus.running
                        await db.commit()
                        logger.info("实例 %s 重启完成，状态已恢复为 running", inst.name)
                        _broadcast_agent_status(inst.workspace_id, instance_id, "running")
                return
        except Exception as e:
            logger.debug("重启监控轮询异常: instance=%s error=%s", instance_id, e)

        await asyncio.sleep(_RESTART_POLL_INTERVAL)
        elapsed += _RESTART_POLL_INTERVAL

    logger.warning("重启监控超时 (%ds)，强制恢复状态: instance=%s", _RESTART_TIMEOUT, instance_id)
    try:
        async with async_session_factory() as db:
            result = await db.execute(select(Instance).where(Instance.id == instance_id))
            inst = result.scalar_one_or_none()
            if inst and inst.status == InstanceStatus.restarting:
                inst.status = InstanceStatus.running
                await db.commit()
                _broadcast_agent_status(inst.workspace_id, instance_id, "running")
    except Exception:
        logger.exception("重启超时后恢复状态失败: instance=%s", instance_id)


async def get_deploy_history(instance_id: str, db: AsyncSession) -> list[DeployRecordInfo]:
    result = await db.execute(
        select(DeployRecord)
        .where(DeployRecord.instance_id == instance_id, DeployRecord.deleted_at.is_(None))
        .order_by(DeployRecord.created_at.desc())
    )
    return [DeployRecordInfo.model_validate(r) for r in result.scalars().all()]


async def get_pod_logs(
    instance_id: str, pod_name: str, db: AsyncSession, container: str | None = None, tail_lines: int = 200
) -> str:
    instance = await get_instance(instance_id, db)
    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id, Cluster.deleted_at.is_(None))
    )
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
    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id, Cluster.deleted_at.is_(None))
    )
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
            DeployRecord.instance_id == instance.id, DeployRecord.deleted_at.is_(None)
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
                            "nodeskclaw/updatedAt": datetime.now(timezone.utc).isoformat()
                        }
                    },
                    "spec": {
                        "containers": [{
                            "name": _k8s_name(instance),
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
        k_name = _k8s_name(instance)
        await k8s.apps.patch_namespaced_deployment(k_name, instance.namespace, patch_body)

        # Update ConfigMap if env_vars changed
        if req.env_vars is not None:
            labels = build_labels(k_name, instance.id, instance.image_version)
            cm = build_configmap(f"{k_name}-config", instance.namespace, req.env_vars, labels)
            try:
                await k8s.core.replace_namespaced_config_map(
                    f"{k_name}-config", instance.namespace, cm
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


async def sync_gateway_token(instance_id: str, db: AsyncSession) -> str:
    """从运行中的 Pod 读取 OPENCLAW_GATEWAY_TOKEN 并回填到 DB 和 ConfigMap。"""
    instance = await get_instance(instance_id, db)

    # 如果 DB 中已有 Token，直接返回
    env_vars = json.loads(instance.env_vars) if instance.env_vars else {}
    if env_vars.get("OPENCLAW_GATEWAY_TOKEN"):
        return env_vars["OPENCLAW_GATEWAY_TOKEN"]

    # 获取集群连接
    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id, Cluster.deleted_at.is_(None))
    )
    cluster = cluster_result.scalar_one_or_none()
    if not cluster:
        raise NotFoundError("集群不存在")

    api_client = await k8s_manager.get_or_create(cluster.id, cluster.kubeconfig_encrypted)
    k8s = K8sClient(api_client)

    # 找一个 Running 的 Pod
    k_name = _k8s_name(instance)
    label_selector = f"app.kubernetes.io/name={k_name}"
    pods = await k8s.list_pods(instance.namespace, label_selector)
    logger.info("sync_gateway_token: found %d pods (label=%s)", len(pods), label_selector)
    running_pods = [p for p in pods if p["phase"] == "Running"]
    if not running_pods:
        phases = [p["phase"] for p in pods]
        raise NotFoundError(f"没有运行中的 Pod，无法获取 Token（当前状态: {phases}）")

    pod_name = running_pods[0]["name"]
    logger.info("sync_gateway_token: reading logs from pod %s", pod_name)

    # 从 Pod 启动日志中解析 Token（entrypoint 会打印 "[entrypoint] Token: xxx"）
    # 使用 limit_bytes 从头部读取（Token 在容器启动时输出，tail_lines 取不到）
    try:
        logs = await k8s.core.read_namespaced_pod_log(
            pod_name, instance.namespace, limit_bytes=65536,
        )
    except Exception as e:
        logger.exception("sync_gateway_token: get_pod_logs failed")
        raise NotFoundError(f"读取 Pod 日志失败: {e}")

    match = _re.search(r"\[entrypoint\] Token: (\S+)", logs)
    if not match:
        raise NotFoundError(
            "Pod 日志中未找到 Gateway Token（容器可能使用了用户指定的 Token 而未打印）"
        )
    token = match.group(1)

    # 回填到 DB
    env_vars["OPENCLAW_GATEWAY_TOKEN"] = token
    instance.env_vars = json.dumps(env_vars)

    # 回填到 ConfigMap
    try:
        labels = build_labels(k_name, instance.id, instance.image_version)
        cm = build_configmap(f"{k_name}-config", instance.namespace, env_vars, labels)
        try:
            await k8s.core.replace_namespaced_config_map(
                f"{k_name}-config", instance.namespace, cm
            )
        except Exception:
            await k8s.create_or_skip(
                k8s.core.create_namespaced_config_map, instance.namespace, cm
            )
    except Exception as e:
        logger.warning("回填 ConfigMap 失败: %s", e)

    await db.commit()
    return token


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
            DeployRecord.deleted_at.is_(None),
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
