"""Instance service: list, detail, delete, scale, restart, config save/apply."""

from __future__ import annotations

import asyncio
import json
import logging
import re as _re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Coroutine

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models.cluster import Cluster
from app.models.workspace import Workspace
from app.models.workspace_agent import WorkspaceAgent
from app.models.deploy_record import DeployAction, DeployRecord, DeployStatus
from app.models.instance import Instance, InstanceStatus
from app.models.node_card import NodeCard
from app.schemas.deploy import DeployRecordInfo
from app.schemas.instance import InstanceDetail, InstanceInfo, UpdateConfigRequest, WorkspaceBrief
from app.services.runtime.compute.base import ComputeHandle
from app.utils.display_status import compute_display_status
from app.services.k8s.client_manager import k8s_manager
from app.services.k8s.k8s_client import K8sClient
from app.services.k8s.resource_builder import build_configmap, build_labels

logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task] = set()


@dataclass(slots=True)
class DisplayNameUpdateResult:
    info: InstanceInfo
    changed: bool
    old_display_name: str | None
    new_display_name: str | None
    old_effective_name: str
    new_effective_name: str
    synced_workspace_ids: list[str]


async def _get_instance_workspace_ids(db: AsyncSession, instance_id: str) -> list[str]:
    """Get all workspace IDs associated with an instance via WorkspaceAgent."""
    result = await db.execute(
        select(WorkspaceAgent.workspace_id).where(
            WorkspaceAgent.instance_id == instance_id,
            WorkspaceAgent.deleted_at.is_(None),
        )
    )
    return [row[0] for row in result.all()]


def _fire_task(coro: Coroutine) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


_PV_CLEANUP_DELAY = 15
_PV_CLEANUP_RETRIES = 3
_DELETE_FINALIZER_DELAY = 10
_DELETE_FINALIZER_RETRIES = 30


async def _deferred_pv_cleanup(k8s: K8sClient, namespace: str) -> None:
    """Namespace 删除是异步的，等待 PVC 被回收后清理残留的 Released PV。"""
    for attempt in range(1, _PV_CLEANUP_RETRIES + 1):
        await asyncio.sleep(_PV_CLEANUP_DELAY)
        try:
            deleted = await k8s.cleanup_released_pvs(namespace)
            if deleted:
                logger.info("后台清理了 %d 个 Released PV (namespace=%s)", deleted, namespace)
            return
        except Exception as e:
            logger.warning(
                "后台清理 PV 第 %d 次失败 (namespace=%s): %s",
                attempt, namespace, e,
            )


async def _cleanup_backup_s3_objects(keys: list[str]) -> None:
    """异步清理已软删除的备份在 S3 上的对象。"""
    from app.services import storage_service
    for key in keys:
        try:
            await storage_service.delete_raw(key)
        except Exception as e:
            logger.warning("清理备份 S3 对象失败 (key=%s): %s", key, e)


def _sanitize_name(name: str) -> str:
    """将实例名称清洗为 RFC 1123 格式（与 deploy_service 逻辑保持一致）。"""
    safe = _re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
    return _re.sub(r"-{2,}", "-", safe)


def _effective_instance_name(instance: Instance) -> str:
    return instance.agent_display_name or instance.name


def _normalize_instance_display_name(display_name: str | None, original_name: str) -> str | None:
    if display_name is None:
        return None
    trimmed = display_name.strip()
    if not trimmed:
        raise BadRequestError("显示名称不能为空", "errors.instance.display_name_empty")
    if len(trimmed) > 64:
        raise BadRequestError(
            "显示名称不能超过 64 个字符",
            "errors.instance.display_name_too_long",
            message_params={"max": "64"},
        )
    if _re.search(r"[\x00-\x1f\x7f]", trimmed):
        raise BadRequestError("显示名称不能包含控制字符", "errors.instance.display_name_invalid")
    return None if trimmed == original_name else trimmed


def _k8s_name(instance: Instance) -> str:
    """K8s 资源名：优先用 slug，兼容未迁移的旧实例回退到 name。"""
    return instance.slug or instance.name


def _get_compute_provider(compute_provider: str):
    from app.services.runtime.registries.compute_registry import COMPUTE_REGISTRY
    spec = COMPUTE_REGISTRY.get(compute_provider)
    return spec.provider if spec and spec.provider else None


def _parse_advanced_config(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_equivalent(left, right) -> bool:
    return json.loads(json.dumps(left, sort_keys=True)) == json.loads(json.dumps(right, sort_keys=True))


def _merge_reserved_advanced_config(
    requested_advanced_config: dict,
    existing_advanced_config: str | None,
) -> dict:
    merged = json.loads(json.dumps(requested_advanced_config))
    existing = _parse_advanced_config(existing_advanced_config)
    existing_has_refs = "secret_env_refs" in existing

    if "secret_env_refs" in merged:
        if not existing_has_refs or not _json_equivalent(merged["secret_env_refs"], existing["secret_env_refs"]):
            raise BadRequestError(
                message="advanced_config.secret_env_refs 是系统保留字段，不能由实例配置请求直接声明",
                message_key="errors.template.secret_env_refs_reserved",
            )

    if existing_has_refs:
        merged["secret_env_refs"] = existing["secret_env_refs"]
    else:
        merged.pop("secret_env_refs", None)
    return merged


def _is_k8s_not_found(exc: Exception) -> bool:
    return getattr(exc, "status", None) == 404


async def _get_k8s_client_for_cluster(cluster: Cluster) -> K8sClient:
    from app.services.runtime.registries.compute_registry import require_k8s_client
    return await require_k8s_client(cluster)


async def _get_gateway_k8s_client() -> K8sClient:
    gateway_api = await k8s_manager.get_gateway_client()
    return K8sClient(gateway_api)


async def _delete_namespace_and_check_absent(k8s: K8sClient, namespace: str) -> bool:
    try:
        await k8s.core.delete_namespace(namespace)
        logger.info("已请求删除命名空间 %s", namespace)
    except Exception as e:
        if not _is_k8s_not_found(e):
            raise

    try:
        await k8s.core.read_namespace(namespace)
        return False
    except Exception as e:
        if _is_k8s_not_found(e):
            return True
        raise


async def _delete_proxy_ingress_and_check_absent(gateway_k8s: K8sClient, proxy_name: str) -> bool:
    from app.services.k8s.client_manager import GATEWAY_NS

    try:
        await gateway_k8s.networking.delete_namespaced_ingress(proxy_name, GATEWAY_NS)
        logger.info("已请求清理网关代理 Ingress: %s", proxy_name)
    except Exception as e:
        if not _is_k8s_not_found(e):
            raise

    try:
        await gateway_k8s.networking.read_namespaced_ingress(proxy_name, GATEWAY_NS)
        return False
    except Exception as e:
        if _is_k8s_not_found(e):
            return True
        raise


async def _soft_delete_instance_records(instance: Instance, db: AsyncSession) -> None:
    instance.soft_delete()
    await db.execute(
        update(DeployRecord)
        .where(DeployRecord.instance_id == instance.id, DeployRecord.deleted_at.is_(None))
        .values(deleted_at=func.now())
    )

    from app.models.backup import InstanceBackup
    backup_result = await db.execute(
        select(InstanceBackup.storage_key).where(
            InstanceBackup.instance_id == instance.id,
            InstanceBackup.deleted_at.is_(None),
            InstanceBackup.storage_key.isnot(None),
        )
    )
    s3_keys = [row[0] for row in backup_result.all()]
    await db.execute(
        update(InstanceBackup)
        .where(InstanceBackup.instance_id == instance.id, InstanceBackup.deleted_at.is_(None))
        .values(deleted_at=func.now())
    )

    from app.models.instance_member import InstanceMember
    await db.execute(
        update(InstanceMember)
        .where(InstanceMember.instance_id == instance.id, InstanceMember.deleted_at.is_(None))
        .values(deleted_at=func.now())
    )
    await db.commit()

    if s3_keys:
        _fire_task(_cleanup_backup_s3_objects(s3_keys))


async def _destroy_non_k8s_instance(instance: Instance) -> bool:
    """销毁非 K8s 实例的运行资源；provider 未注册时跳过资源销毁，放行记录清理。"""
    provider = _get_compute_provider(instance.compute_provider)
    if provider is None or not hasattr(provider, "destroy_instance"):
        logger.warning(
            "实例 %s 使用的 compute_provider=%s 未注册销毁器，跳过运行资源清理",
            instance.id, instance.compute_provider,
        )
        return True

    handle = ComputeHandle(
        provider=instance.compute_provider, instance_id=instance.id,
        namespace=instance.namespace, endpoint=instance.ingress_domain or "",
        status=instance.status,
        extra={"slug": instance.slug, "runtime": instance.runtime},
    )
    await provider.destroy_instance(handle)
    logger.info("已销毁 %s 运行资源（实例 %s）", instance.compute_provider, instance.name)
    return True


async def mark_instance_deleting(instance: Instance, db: AsyncSession) -> None:
    instance.status = InstanceStatus.deleting
    await db.commit()
    schedule_instance_deletion_finalizer(instance.id)


def schedule_instance_deletion_finalizer(instance_id: str) -> asyncio.Task:
    return _fire_task(_run_instance_deletion_finalizer(instance_id))


async def _run_instance_deletion_finalizer(instance_id: str) -> None:
    from app.core.deps import async_session_factory

    for attempt in range(1, _DELETE_FINALIZER_RETRIES + 1):
        try:
            async with async_session_factory() as db:
                if await finalize_instance_deletion_once(instance_id, db):
                    return
        except Exception:
            logger.warning(
                "实例删除 finalizer 第 %d 次失败: instance_id=%s",
                attempt, instance_id, exc_info=True,
            )
        await asyncio.sleep(_DELETE_FINALIZER_DELAY)

    logger.error(
        "实例删除 finalizer 多次重试后仍未完成: instance_id=%s retries=%d",
        instance_id, _DELETE_FINALIZER_RETRIES,
    )


async def finalize_instance_deletion_once(instance_id: str, db: AsyncSession) -> bool:
    result = await db.execute(
        select(Instance).where(
            Instance.id == instance_id,
            Instance.deleted_at.is_(None),
        )
    )
    instance = result.scalar_one_or_none()
    if instance is None:
        return True

    if instance.status != InstanceStatus.deleting:
        instance.status = InstanceStatus.deleting
        await db.commit()

    if instance.compute_provider != "k8s":
        try:
            if not await _destroy_non_k8s_instance(instance):
                return False
        except Exception:
            logger.warning("销毁实例 %s 的运行资源失败", instance.name, exc_info=True)
            return False

        await _soft_delete_instance_records(instance, db)
        logger.info("实例 %s 删除完成，DB 已软删除", instance.name)
        return True

    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id, Cluster.deleted_at.is_(None))
    )
    cluster = cluster_result.scalar_one_or_none()
    if not cluster or not cluster.is_k8s or not cluster.credentials_encrypted:
        logger.warning(
            "实例 %s 删除等待中：集群不存在或缺少 K8s 连接凭证",
            instance.name,
        )
        return False

    try:
        k8s = await _get_k8s_client_for_cluster(cluster)
        namespace_absent = await _delete_namespace_and_check_absent(k8s, instance.namespace)
    except Exception:
        logger.warning("清理实例 %s 的命名空间失败", instance.name, exc_info=True)
        return False

    proxy_absent = True
    if cluster.proxy_endpoint:
        proxy_name = f"proxy-{_k8s_name(instance)}"
        try:
            gateway_k8s = await _get_gateway_k8s_client()
            proxy_absent = await _delete_proxy_ingress_and_check_absent(gateway_k8s, proxy_name)
        except Exception:
            logger.warning("清理网关代理 Ingress %s 失败", proxy_name, exc_info=True)
            proxy_absent = False

    if not namespace_absent or not proxy_absent:
        logger.info(
            "实例 %s 删除等待中：namespace_absent=%s proxy_absent=%s",
            instance.name, namespace_absent, proxy_absent,
        )
        return False

    _fire_task(_deferred_pv_cleanup(k8s, instance.namespace))
    await _soft_delete_instance_records(instance, db)
    logger.info("实例 %s 删除完成，K8s 资源确认不存在，DB 已软删除", instance.name)
    return True


async def _in_deploy_grace(instance_id: str, db: AsyncSession, grace_seconds: int = 60) -> bool:
    """Check if the instance was deployed/redeployed within the last *grace_seconds*."""
    latest = await db.execute(
        select(DeployRecord.finished_at)
        .where(
            DeployRecord.instance_id == instance_id,
            DeployRecord.status == DeployStatus.success,
            DeployRecord.deleted_at.is_(None),
        )
        .order_by(DeployRecord.finished_at.desc())
        .limit(1)
    )
    finished_at = latest.scalar_one_or_none()
    if not finished_at:
        return False
    return (datetime.now(timezone.utc) - finished_at).total_seconds() < grace_seconds


def _compute_endpoint_url(instance: Instance, *, tls_enabled: bool = True) -> str | None:
    from app.services.runtime.registries.runtime_registry import RUNTIME_REGISTRY
    spec = RUNTIME_REGISTRY.get(instance.runtime)
    if spec and not spec.has_web_ui:
        return None
    if instance.ingress_domain:
        proto = "https" if tls_enabled else "http"
        return f"{proto}://{instance.ingress_domain}"
    return None


def _normalize_gateway_env_vars(env_vars: dict[str, str], token: str) -> dict[str, str]:
    """统一实例访问令牌相关环境变量。"""
    normalized = dict(env_vars)
    normalized["GATEWAY_TOKEN"] = token
    normalized["OPENCLAW_GATEWAY_TOKEN"] = token
    normalized["NODESKCLAW_TOKEN"] = token
    return normalized


async def _replace_instance_configmap(
    instance: Instance, env_vars: dict[str, str], k8s: K8sClient,
) -> None:
    """用新的环境变量替换实例 ConfigMap。"""
    k_name = _k8s_name(instance)
    labels = build_labels(k_name, instance.id, instance.image_version)
    cm = build_configmap(f"{k_name}-config", instance.namespace, env_vars, labels)
    try:
        await k8s.core.replace_namespaced_config_map(
            f"{k_name}-config", instance.namespace, cm,
        )
    except Exception:
        await k8s.create_or_skip(
            k8s.core.create_namespaced_config_map, instance.namespace, cm,
        )


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
    from app.services.config_service import get_config
    tls_enabled = (await get_config("ingress_tls_enabled", db)) != "false"

    query = (
        select(Instance)
        .where(Instance.deleted_at.is_(None))
        .order_by(Instance.created_at.desc())
    )
    if cluster_id:
        query = query.where(Instance.cluster_id == cluster_id)
    if org_id:
        query = query.where(Instance.org_id == org_id)
    result = await db.execute(query)

    from app.services.tunnel import tunnel_adapter
    connected = tunnel_adapter.connected_instances
    health_corrected = False

    items: list[InstanceInfo] = []
    for i in result.scalars().all():
        if i.status == "running" and i.health_status != "healthy" and i.id in connected:
            i.health_status = "healthy"
            health_corrected = True
        wa_result = await db.execute(
            select(WorkspaceAgent, Workspace).join(
                Workspace,
                (Workspace.id == WorkspaceAgent.workspace_id) & (Workspace.deleted_at.is_(None)),
            ).where(
                WorkspaceAgent.instance_id == i.id,
                WorkspaceAgent.deleted_at.is_(None),
            )
        )
        workspaces = [
            WorkspaceBrief(id=wa.workspace_id, name=ws.name)
            for wa, ws in wa_result.all()
        ]
        info = InstanceInfo.model_validate(i)
        info.workspaces = workspaces
        info.endpoint_url = _compute_endpoint_url(i, tls_enabled=tls_enabled)
        items.append(info)

    if health_corrected:
        try:
            await db.commit()
        except Exception:
            logger.debug("列表 tunnel 健康修正持久化失败（非致命）")

    return items


async def get_instance(instance_id: str, db: AsyncSession, org_id: str | None = None) -> Instance:
    query = select(Instance).where(Instance.id == instance_id, Instance.deleted_at.is_(None))
    if org_id is not None:
        query = query.where(Instance.org_id == org_id)
    result = await db.execute(query)
    instance = result.scalar_one_or_none()
    if not instance:
        raise NotFoundError("实例不存在")
    return instance


async def _global_display_sync_targets(
    instance_id: str,
    db: AsyncSession,
) -> list[tuple[WorkspaceAgent, Workspace]]:
    result = await db.execute(
        select(WorkspaceAgent, Workspace)
        .join(
            Workspace,
            (Workspace.id == WorkspaceAgent.workspace_id) & (Workspace.deleted_at.is_(None)),
        )
        .where(
            WorkspaceAgent.instance_id == instance_id,
            WorkspaceAgent.display_name.is_(None),
            WorkspaceAgent.deleted_at.is_(None),
        )
    )
    return list(result.all())


async def _ensure_node_card_name_available(
    db: AsyncSession,
    *,
    instance_id: str,
    workspace: Workspace,
    display_name: str,
) -> None:
    result = await db.execute(
        select(NodeCard).where(
            NodeCard.workspace_id == workspace.id,
            NodeCard.node_id != instance_id,
            NodeCard.name == display_name,
            NodeCard.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is not None:
        raise ConflictError(
            f"显示名称在办公室「{workspace.name}」中已被使用",
            "errors.instance.display_name_conflict_in_workspace",
            message_params={"workspace": workspace.name, "name": display_name},
        )


async def update_display_name(
    instance_id: str,
    display_name: str | None,
    db: AsyncSession,
    org_id: str | None = None,
) -> DisplayNameUpdateResult:
    instance = await get_instance(instance_id, db, org_id)
    old_display_name = instance.agent_display_name
    old_effective_name = _effective_instance_name(instance)
    new_display_name = _normalize_instance_display_name(display_name, instance.name)
    new_effective_name = new_display_name or instance.name
    stored_changed = instance.agent_display_name != new_display_name
    effective_changed = old_effective_name != new_effective_name

    if not stored_changed:
        return DisplayNameUpdateResult(
            info=InstanceInfo.model_validate(instance),
            changed=False,
            old_display_name=old_display_name,
            new_display_name=new_display_name,
            old_effective_name=old_effective_name,
            new_effective_name=new_effective_name,
            synced_workspace_ids=[],
        )

    sync_targets: list[tuple[WorkspaceAgent, Workspace]] = []
    synced_workspace_ids: list[str] = []
    if effective_changed:
        sync_targets = await _global_display_sync_targets(instance_id, db)
        for _wa, workspace in sync_targets:
            await _ensure_node_card_name_available(
                db,
                instance_id=instance_id,
                workspace=workspace,
                display_name=new_effective_name,
            )

    instance.agent_display_name = new_display_name

    if effective_changed:
        for wa, _workspace in sync_targets:
            card_result = await db.execute(
                select(NodeCard).where(
                    NodeCard.workspace_id == wa.workspace_id,
                    NodeCard.node_id == instance_id,
                    NodeCard.deleted_at.is_(None),
                )
            )
            card = card_result.scalar_one_or_none()
            if card is not None and card.name != new_effective_name:
                card.name = new_effective_name
                synced_workspace_ids.append(wa.workspace_id)

    await db.commit()

    if synced_workspace_ids:
        from app.services import conversation_service
        for workspace_id in dict.fromkeys(synced_workspace_ids):
            await conversation_service.sync_conversations_and_notify_topology(workspace_id, db)
        await db.commit()

    await db.refresh(instance)
    return DisplayNameUpdateResult(
        info=InstanceInfo.model_validate(instance),
        changed=effective_changed,
        old_display_name=old_display_name,
        new_display_name=instance.agent_display_name,
        old_effective_name=old_effective_name,
        new_effective_name=_effective_instance_name(instance),
        synced_workspace_ids=list(dict.fromkeys(synced_workspace_ids)),
    )


async def get_instance_detail(instance_id: str, db: AsyncSession, org_id: str | None = None) -> InstanceDetail:
    """Get instance info enriched with live K8s pod data."""
    from app.services.config_service import get_config
    tls_enabled = (await get_config("ingress_tls_enabled", db)) != "false"

    instance = await get_instance(instance_id, db, org_id)

    wa_result = await db.execute(
        select(WorkspaceAgent, Workspace).join(
            Workspace,
            (Workspace.id == WorkspaceAgent.workspace_id) & (Workspace.deleted_at.is_(None)),
        ).where(
            WorkspaceAgent.instance_id == instance_id,
            WorkspaceAgent.deleted_at.is_(None),
        )
    )
    workspaces = [
        WorkspaceBrief(id=wa.workspace_id, name=ws.name)
        for wa, ws in wa_result.all()
    ]

    # Get cluster for k8s connection
    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id, Cluster.deleted_at.is_(None))
    )
    cluster = cluster_result.scalar_one_or_none()

    info_base = InstanceInfo.model_validate(instance)
    info_base.endpoint_url = _compute_endpoint_url(instance, tls_enabled=tls_enabled)

    detail = InstanceDetail(
        **info_base.model_dump(),
        cpu_request=instance.cpu_request,
        cpu_limit=instance.cpu_limit,
        mem_request=instance.mem_request,
        mem_limit=instance.mem_limit,
        env_vars=json.loads(instance.env_vars) if instance.env_vars else {},
    )
    detail.workspaces = workspaces

    if cluster and cluster.is_k8s and cluster.credentials_encrypted:
        try:
            from app.services.runtime.registries.compute_registry import require_k8s_client
            k8s = await require_k8s_client(cluster)
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

            if instance.status == InstanceStatus.running:
                from app.services.tunnel import tunnel_adapter
                from app.services.runtime.compute.k8s_provider import evaluate_k8s_health
                tunnel_connected = instance.id in tunnel_adapter.connected_instances
                probe = evaluate_k8s_health(tunnel_connected, pods)
                if probe["healthy"] is True:
                    detail.health_status = "healthy"
                elif probe["healthy"] is False:
                    detail.health_status = "unhealthy"
                else:
                    detail.health_status = "unknown"
        except Exception as e:
            logger.warning("Failed to fetch pods for instance %s: %s", instance_id, e)

    if (
        not instance.ingress_domain
        and cluster
        and cluster.is_k8s
        and cluster.credentials_encrypted
    ):
        try:
            from app.services.runtime.registries.compute_registry import require_k8s_client
            _heal_k8s = await require_k8s_client(cluster)
            _ing = await _heal_k8s.get_ingress(instance.namespace, _k8s_name(instance))
            if _ing.spec and _ing.spec.rules and _ing.spec.rules[0].host:
                instance.ingress_domain = _ing.spec.rules[0].host
                await db.commit()
                detail.ingress_domain = instance.ingress_domain
                detail.endpoint_url = _compute_endpoint_url(instance, tls_enabled=tls_enabled)
        except Exception:
            pass

    if instance.status == InstanceStatus.running and detail.health_status != instance.health_status:
        instance.health_status = detail.health_status
        await db.commit()

    detail.display_status = compute_display_status(detail.status, detail.health_status)
    return detail


async def delete_instance(instance_id: str, db: AsyncSession, delete_k8s: bool = True, org_id: str | None = None):
    """请求删除实例，最终清理完成后再逻辑删除 DB 记录。"""
    if not delete_k8s:
        raise BadRequestError(
            message="删除实例必须同步清理运行资源",
            message_key="errors.instance.delete_k8s_required",
        )

    instance = await get_instance(instance_id, db, org_id)

    wa_count_result = await db.execute(
        select(func.count()).select_from(WorkspaceAgent).where(
            WorkspaceAgent.instance_id == instance_id,
            WorkspaceAgent.deleted_at.is_(None),
        )
    )
    if wa_count_result.scalar() > 0:
        raise ConflictError(
            message="该实例已加入办公室，请先从办公室中移除",
            message_key="errors.instance.still_in_workspace",
        )

    await mark_instance_deleting(instance, db)


async def scale_instance(instance_id: str, replicas: int, db: AsyncSession, org_id: str | None = None):
    instance = await get_instance(instance_id, db, org_id)

    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id, Cluster.deleted_at.is_(None))
    )
    cluster = cluster_result.scalar_one_or_none()
    if not cluster:
        raise NotFoundError("集群不存在")

    from app.services.runtime.registries.compute_registry import require_k8s_client
    k8s = await require_k8s_client(cluster)
    await k8s.scale_deployment(instance.namespace, _k8s_name(instance), replicas)

    instance.replicas = replicas
    await db.commit()


async def restart_instance(instance_id: str, db: AsyncSession, org_id: str | None = None):
    instance = await get_instance(instance_id, db, org_id)

    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id, Cluster.deleted_at.is_(None))
    )
    cluster = cluster_result.scalar_one_or_none()
    if not cluster:
        raise NotFoundError("集群不存在")

    prev_status = instance.status
    instance.status = InstanceStatus.restarting
    await db.commit()

    from app.services.runtime.registries.compute_registry import require_k8s_client
    k8s = await require_k8s_client(cluster)
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
    _fire_task(_monitor_restart(instance_id, cluster.id, cluster.credentials_encrypted, instance.namespace, name))


_RESTART_POLL_INTERVAL = 5
_RESTART_TIMEOUT = 120


def _broadcast_agent_status(workspace_ids: list[str], instance_id: str, status: str) -> None:
    payload = {"instance_id": instance_id, "status": status}
    try:
        from app.api.workspaces import broadcast_event
        for ws_id in workspace_ids:
            broadcast_event(ws_id, "agent:status", payload)
    except Exception:
        logger.debug("广播 agent:status 失败: instance=%s", instance_id)


async def _monitor_restart(
    instance_id: str, cluster_id: str, credentials_encrypted: str, namespace: str, deploy_name: str,
) -> None:
    """Poll K8s pod status after restart and update DB status when ready."""
    from app.core.deps import async_session_factory

    await asyncio.sleep(_RESTART_POLL_INTERVAL)

    elapsed = 0
    while elapsed < _RESTART_TIMEOUT:
        try:
            api_client = await k8s_manager.get_or_create(cluster_id, credentials_encrypted)
            k8s = K8sClient(api_client)
            pods = await k8s.list_pods(namespace)
            has_ready = any(
                all(c.get("ready", False) for c in p.get("containers", []))
                and len(p.get("containers", [])) > 0
                for p in pods
            )
            if has_ready:
                async with async_session_factory() as db:
                    result = await db.execute(
                        select(Instance).where(
                            Instance.id == instance_id,
                            Instance.deleted_at.is_(None),
                        )
                    )
                    inst = result.scalar_one_or_none()
                    if inst and inst.status == InstanceStatus.restarting:
                        inst.status = InstanceStatus.running
                        inst.health_status = "healthy"
                        await db.commit()
                        logger.info("实例 %s 重启完成，状态已恢复为 running", inst.name)
                        ws_ids = await _get_instance_workspace_ids(db, instance_id)
                        _broadcast_agent_status(ws_ids, instance_id, "running")
                return
        except Exception as e:
            logger.debug("重启监控轮询异常: instance=%s error=%s", instance_id, e)

        await asyncio.sleep(_RESTART_POLL_INTERVAL)
        elapsed += _RESTART_POLL_INTERVAL

    logger.warning("重启监控超时 (%ds)，强制恢复状态: instance=%s", _RESTART_TIMEOUT, instance_id)
    try:
        async with async_session_factory() as db:
            result = await db.execute(
                select(Instance).where(
                    Instance.id == instance_id,
                    Instance.deleted_at.is_(None),
                )
            )
            inst = result.scalar_one_or_none()
            if inst and inst.status == InstanceStatus.restarting:
                inst.status = InstanceStatus.running
                inst.health_status = "unknown"
                await db.commit()
                ws_ids = await _get_instance_workspace_ids(db, instance_id)
                _broadcast_agent_status(ws_ids, instance_id, "running")
    except Exception:
        logger.exception("重启超时后恢复状态失败: instance=%s", instance_id)


async def get_deploy_history(instance_id: str, db: AsyncSession, org_id: str | None = None) -> list[DeployRecordInfo]:
    await get_instance(instance_id, db, org_id)
    result = await db.execute(
        select(DeployRecord)
        .where(DeployRecord.instance_id == instance_id, DeployRecord.deleted_at.is_(None))
        .order_by(DeployRecord.created_at.desc())
    )
    return [DeployRecordInfo.model_validate(r) for r in result.scalars().all()]


async def get_pod_logs(
    instance_id: str,
    pod_name: str,
    db: AsyncSession,
    container: str | None = None,
    tail_lines: int = 200,
    org_id: str | None = None,
) -> str:
    instance = await get_instance(instance_id, db, org_id)

    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id, Cluster.deleted_at.is_(None))
    )
    cluster = cluster_result.scalar_one_or_none()
    if not cluster:
        raise NotFoundError("集群不存在")

    from app.services.runtime.registries.compute_registry import require_k8s_client
    k8s = await require_k8s_client(cluster)
    return await k8s.get_pod_logs(instance.namespace, pod_name, container, tail_lines)


# ────────────────────────────────────────────────────────────
# 两步操作模式: save_config (仅存 DB) + apply_config (执行 K8s)
# ────────────────────────────────────────────────────────────

async def save_config(
    instance_id: str, req: UpdateConfigRequest, db: AsyncSession, org_id: str | None = None
) -> InstanceInfo:
    """
    Step 1: 仅保存配置变更到 pending_config，不执行 K8s 操作。
    """
    instance = await get_instance(instance_id, db, org_id)
    advanced_config = (
        _merge_reserved_advanced_config(req.advanced_config, instance.advanced_config)
        if req.advanced_config is not None else None
    )

    pending = {
        "image_version": req.image_version,
        "cpu_request": req.cpu_request,
        "cpu_limit": req.cpu_limit,
        "mem_request": req.mem_request,
        "mem_limit": req.mem_limit,
        "env_vars": req.env_vars,
        "replicas": req.replicas,
        "advanced_config": advanced_config,
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
    instance_id: str, user_id: str, db: AsyncSession, org_id: str | None = None
) -> InstanceInfo:
    """
    Step 2: 读取 pending_config，执行 K8s 滚动更新，成功后清空 pending_config。
    """
    instance = await get_instance(instance_id, db, org_id)

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
    instance_id: str, req: UpdateConfigRequest, user_id: str, db: AsyncSession, org_id: str | None = None
) -> InstanceInfo:
    """兼容旧接口: 直接保存 + 应用（供回滚等场景使用）。"""
    instance = await get_instance(instance_id, db, org_id)
    if req.advanced_config is not None:
        req = req.model_copy(update={
            "advanced_config": _merge_reserved_advanced_config(
                req.advanced_config,
                instance.advanced_config,
            ),
        })
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
    if req.advanced_config is not None:
        req = req.model_copy(update={
            "advanced_config": _merge_reserved_advanced_config(
                req.advanced_config,
                instance.advanced_config,
            ),
        })

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

    try:
        from app.services.runtime.registries.compute_registry import require_k8s_client
        k8s = await require_k8s_client(cluster)

        from app.core.exceptions import RegistryError
        from app.services.registry_service import (
            ensure_registry_pull_secret,
            resolve_registry_config,
        )

        registry_config = await resolve_registry_config(db, instance.runtime)
        image_registry = registry_config.image_registry
        if not image_registry:
            raise RegistryError("镜像仓库未配置")
        image = f"{image_registry}:{instance.image_version}"
        pull_secret_name = await ensure_registry_pull_secret(
            k8s,
            instance.namespace,
            registry_config,
        )
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
                        "imagePullSecrets": (
                            [{"name": pull_secret_name}] if pull_secret_name else []
                        ),
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


async def sync_gateway_token(instance_id: str, db: AsyncSession, org_id: str | None = None) -> str:
    """从运行中的 Pod 读取 GATEWAY_TOKEN 并回填到 DB 和 ConfigMap。"""
    instance = await get_instance(instance_id, db, org_id)

    env_vars = json.loads(instance.env_vars) if instance.env_vars else {}
    existing_token = env_vars.get("GATEWAY_TOKEN") or env_vars.get("OPENCLAW_GATEWAY_TOKEN")
    if existing_token:
        normalized_env_vars = _normalize_gateway_env_vars(env_vars, existing_token)
        changed = normalized_env_vars != env_vars or instance.proxy_token != existing_token
        if changed:
            instance.env_vars = json.dumps(normalized_env_vars)
            instance.proxy_token = existing_token
            await db.commit()
        return existing_token

    # 获取集群连接
    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id, Cluster.deleted_at.is_(None))
    )
    cluster = cluster_result.scalar_one_or_none()
    if not cluster:
        raise NotFoundError("集群不存在")

    if not cluster.is_k8s:
        raise BadRequestError("仅 K8s 集群支持此操作", message_key="errors.cluster.unsupported_operation")
    from app.services.runtime.registries.compute_registry import require_k8s_client
    k8s = await require_k8s_client(cluster)

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
    normalized_env_vars = _normalize_gateway_env_vars(env_vars, token)
    instance.env_vars = json.dumps(normalized_env_vars)
    instance.proxy_token = token

    # 回填到 ConfigMap
    try:
        await _replace_instance_configmap(instance, normalized_env_vars, k8s)
    except Exception as e:
        logger.warning("回填 ConfigMap 失败: %s", e)

    await db.commit()
    return token


async def regenerate_gateway_token(instance_id: str, db: AsyncSession, org_id: str | None = None) -> str:
    """生成新的访问令牌，更新配置并触发实例重启。"""
    instance = await get_instance(instance_id, db, org_id)
    old_env_vars_json = instance.env_vars
    old_env_vars = json.loads(instance.env_vars) if instance.env_vars else {}
    old_proxy_token = instance.proxy_token

    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id, Cluster.deleted_at.is_(None))
    )
    cluster = cluster_result.scalar_one_or_none()
    if not cluster:
        raise NotFoundError("集群不存在")

    if not cluster.is_k8s:
        raise BadRequestError("仅 K8s 集群支持此操作", message_key="errors.cluster.unsupported_operation")
    from app.services.runtime.registries.compute_registry import require_k8s_client
    k8s = await require_k8s_client(cluster)

    new_token = secrets.token_hex(24)
    while new_token == old_env_vars.get("GATEWAY_TOKEN"):
        new_token = secrets.token_hex(24)
    new_env_vars = _normalize_gateway_env_vars(old_env_vars, new_token)

    try:
        await _replace_instance_configmap(instance, new_env_vars, k8s)
        instance.env_vars = json.dumps(new_env_vars)
        instance.proxy_token = new_token
        await db.commit()
    except Exception as exc:
        logger.exception("更新实例访问令牌失败: instance=%s", instance_id)
        await db.rollback()
        try:
            fresh_instance = await get_instance(instance_id, db, org_id)
            await _replace_instance_configmap(fresh_instance, old_env_vars, k8s)
        except Exception:
            logger.exception("恢复旧访问令牌 ConfigMap 失败: instance=%s", instance_id)
        raise ConflictError("重设访问令牌失败，请稍后重试") from exc

    try:
        await restart_instance(instance_id, db, org_id)
    except Exception as exc:
        logger.exception("访问令牌更新后触发重启失败: instance=%s", instance_id)
        try:
            rollback_instance = await get_instance(instance_id, db, org_id)
            rollback_instance.env_vars = old_env_vars_json
            rollback_instance.proxy_token = old_proxy_token
            await _replace_instance_configmap(rollback_instance, old_env_vars, k8s)
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception("重设访问令牌失败后回滚旧令牌失败: instance=%s", instance_id)
        raise ConflictError("重设访问令牌后触发重启失败，已回滚旧令牌") from exc

    return new_token


async def rollback_instance(
    instance_id: str, target_revision: int, user_id: str, db: AsyncSession, org_id: str | None = None
) -> InstanceInfo:
    """回滚实例到指定版本。"""
    await get_instance(instance_id, db, org_id)

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

    return await update_config(instance_id, req, user_id, db, org_id)


async def batch_upgrade_image_version(
    runtime: str, target_version: str, user_id: str, db: AsyncSession,
    *, dry_run: bool = False,
) -> dict:
    """批量将指定 runtime 的所有实例镜像版本对齐到 target_version。"""
    excluded = [
        InstanceStatus.creating,
        InstanceStatus.deploying,
        InstanceStatus.updating,
        InstanceStatus.restarting,
        InstanceStatus.deleting,
        InstanceStatus.rebuilding,
        InstanceStatus.restoring,
    ]
    result = await db.execute(
        select(Instance).where(
            Instance.runtime == runtime,
            Instance.deleted_at.is_(None),
            Instance.status.notin_([s.value for s in excluded]),
        )
    )
    instances = list(result.scalars().all())

    upgraded: list[dict] = []
    skipped: list[dict] = []
    failed: list[dict] = []

    for instance in instances:
        brief = {
            "id": instance.id, "name": instance.name,
            "slug": instance.slug, "current_version": instance.image_version,
        }
        if instance.image_version == target_version:
            skipped.append(brief)
            continue

        if dry_run:
            upgraded.append(brief)
            continue

        try:
            await _execute_config_update(
                instance, UpdateConfigRequest(image_version=target_version), user_id, db,
            )
            upgraded.append({**brief, "current_version": target_version})
        except Exception as e:
            logger.exception("批量升级实例 %s 失败", instance.name)
            failed.append({**brief, "error": str(e)[:200]})

    return {"upgraded": upgraded, "skipped": skipped, "failed": failed}
