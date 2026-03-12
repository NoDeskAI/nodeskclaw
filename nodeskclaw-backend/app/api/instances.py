"""Instance management endpoints."""

import json
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import hooks
from app.core.deps import get_db
from app.core.exceptions import NotFoundError
from app.core.security import get_current_user
from app.models.cluster import Cluster
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.deploy import DeployRecordInfo
from app.schemas.instance import InstanceDetail, InstanceInfo, UpdateConfigRequest
from app.services import instance_service
from app.services.k8s.client_manager import k8s_manager
from app.services.k8s.k8s_client import K8sClient

logger = logging.getLogger(__name__)

instance_read_router = APIRouter()
instance_write_router = APIRouter()


@instance_read_router.get("/check-slug", response_model=ApiResponse[dict])
async def check_slug(
    slug: str = Query(..., min_length=1),
    org_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """检查实例标识（slug）在指定组织内是否冲突。

    管理端显式传 org_id；Portal 不传时 fallback 到 current_user.current_org_id。
    """
    effective_org_id = org_id or current_user.current_org_id
    if not effective_org_id:
        return ApiResponse(data={"conflict": False, "reason": ""})
    data = await instance_service.check_slug_conflict(slug, effective_org_id, db)
    return ApiResponse(data=data)


@instance_read_router.get("/check-name", response_model=ApiResponse[dict], deprecated=True)
async def check_name(
    name: str = Query(..., min_length=1),
    cluster_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """(已弃用) 检查实例名称冲突，保留供管理端过渡期使用。"""
    import re as _re
    from app.models.instance import Instance
    safe_name = _re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
    safe_name = _re.sub(r"-{2,}", "-", safe_name)
    result = await db.execute(
        select(Instance).where(
            Instance.cluster_id == cluster_id,
            Instance.deleted_at.is_(None),
        )
    )
    for inst in result.scalars().all():
        if inst.name == name:
            return ApiResponse(data={"conflict": True, "reason": f"实例名称 \"{name}\" 已存在"})
        inst_safe = _re.sub(r"[^a-z0-9-]", "-", inst.name.lower()).strip("-")
        inst_safe = _re.sub(r"-{2,}", "-", inst_safe)
        if inst_safe == safe_name:
            return ApiResponse(data={"conflict": True, "reason": f"名称清洗后与已有实例冲突"})
    return ApiResponse(data={"conflict": False, "reason": ""})


@instance_read_router.get("", response_model=ApiResponse[list[InstanceInfo]])
async def list_instances(
    cluster_id: str | None = Query(None),
    org_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """实例列表（按组织过滤，非超管只能看自己组织的）。"""
    # 非超管强制按当前组织过滤
    effective_org_id = org_id
    if not current_user.is_super_admin:
        effective_org_id = current_user.current_org_id
    data = await instance_service.list_instances(db, cluster_id, org_id=effective_org_id)
    return ApiResponse(data=data)


@instance_read_router.get("/{instance_id}", response_model=ApiResponse[InstanceDetail])
async def get_instance(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """实例详情（含 Pod 实时信息）。"""
    data = await instance_service.get_instance_detail(instance_id, db)
    return ApiResponse(data=data)


@instance_write_router.delete("/{instance_id}", response_model=ApiResponse)
async def delete_instance(
    instance_id: str,
    delete_k8s: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """删除实例。"""
    await instance_service.delete_instance(instance_id, db, delete_k8s)
    await hooks.emit("operation_audit", action="instance.deleted", target_type="instance", target_id=instance_id, actor_id=_current_user.id, org_id=_current_user.current_org_id, details={"delete_k8s": delete_k8s, "source": "admin"})
    return ApiResponse(message="实例已删除")


class ScaleBody(BaseModel):
    replicas: int


@instance_write_router.post("/{instance_id}/scale", response_model=ApiResponse)
async def scale_instance(
    instance_id: str,
    body: ScaleBody,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """扩缩容。"""
    await instance_service.scale_instance(instance_id, body.replicas, db)
    await hooks.emit("operation_audit", action="instance.scaled", target_type="instance", target_id=instance_id, actor_id=_current_user.id, org_id=_current_user.current_org_id, details={"replicas": body.replicas, "source": "admin"})
    return ApiResponse(message=f"已扩缩容至 {body.replicas} 副本")


@instance_write_router.post("/{instance_id}/restart", response_model=ApiResponse)
async def restart_instance(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """重启实例（scale 0 -> scale N）。"""
    logger.info("用户 %s (%s) 请求重启实例 %s", current_user.name, current_user.id, instance_id)
    await instance_service.restart_instance(instance_id, db)
    await hooks.emit("operation_audit", action="instance.restart", target_type="instance", target_id=instance_id, actor_id=current_user.id, org_id=current_user.current_org_id, details={"source": "admin"})
    return ApiResponse(message="已触发重启，实例将在数秒后恢复")


@instance_read_router.get("/{instance_id}/history", response_model=ApiResponse[list[DeployRecordInfo]])
async def deploy_history(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """部署历史。"""
    data = await instance_service.get_deploy_history(instance_id, db)
    return ApiResponse(data=data)


@instance_write_router.put("/{instance_id}/config", response_model=ApiResponse[InstanceInfo])
async def save_config(
    instance_id: str,
    body: UpdateConfigRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """保存实例配置变更到 pending_config（不立即生效）。"""
    data = await instance_service.save_config(instance_id, body, db)
    await hooks.emit("operation_audit", action="instance.config_saved", target_type="instance", target_id=instance_id, actor_id=_current_user.id, org_id=_current_user.current_org_id, details={"source": "admin"})
    return ApiResponse(data=data)


@instance_write_router.post("/{instance_id}/apply", response_model=ApiResponse[InstanceInfo])
async def apply_config(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """将 pending_config 应用到 K8s，触发滚动更新。"""
    data = await instance_service.apply_config(instance_id, current_user.id, db)
    await hooks.emit("operation_audit", action="instance.config_applied", target_type="instance", target_id=instance_id, actor_id=current_user.id, org_id=current_user.current_org_id, details={"source": "admin"})
    return ApiResponse(data=data)


class RollbackBody(BaseModel):
    target_revision: int


@instance_write_router.post("/{instance_id}/rollback", response_model=ApiResponse[InstanceInfo])
async def rollback_instance(
    instance_id: str,
    body: RollbackBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """回滚到指定版本。"""
    data = await instance_service.rollback_instance(
        instance_id, body.target_revision, current_user.id, db
    )
    await hooks.emit("operation_audit", action="instance.rolled_back", target_type="instance", target_id=instance_id, actor_id=current_user.id, org_id=current_user.current_org_id, details={"target_revision": body.target_revision, "source": "admin"})
    return ApiResponse(data=data)


@instance_write_router.post("/{instance_id}/sync-token", response_model=ApiResponse[dict])
async def sync_token(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """从运行中的 Pod 获取 Gateway Token 并回填到 DB。"""
    token = await instance_service.sync_gateway_token(instance_id, db)
    await hooks.emit("operation_audit", action="instance.token_synced", target_type="instance", target_id=instance_id, actor_id=_current_user.id, org_id=_current_user.current_org_id, details={"source": "admin"})
    return ApiResponse(data={"token": token})


@instance_read_router.get("/{instance_id}/pods/{pod_name}/logs", response_model=ApiResponse[str])
async def pod_logs(
    instance_id: str,
    pod_name: str,
    container: str | None = Query(None),
    tail_lines: int = Query(200),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """获取 Pod 日志。"""
    data = await instance_service.get_pod_logs(instance_id, pod_name, db, container, tail_lines)
    return ApiResponse(data=data)


@instance_read_router.get("/{instance_id}/pods/{pod_name}/logs/stream")
async def pod_logs_stream(
    instance_id: str,
    pod_name: str,
    container: str | None = Query(None),
    tail_lines: int = Query(50),
    since_seconds: int | None = Query(None, description="最近 N 秒的日志"),
    since_time: str | None = Query(None, description="ISO 8601 起始时间"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """SSE 流: 实时 Pod 日志，支持时间范围筛选。"""
    instance = await instance_service.get_instance(instance_id, db)
    result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id, Cluster.deleted_at.is_(None))
    )
    cluster = result.scalar_one_or_none()
    if not cluster:
        raise NotFoundError("集群不存在")

    api_client = await k8s_manager.get_or_create(cluster.id, cluster.kubeconfig_encrypted)

    async def generate():
        k8s = K8sClient(api_client)
        try:
            async for line in k8s.stream_pod_logs(
                instance.namespace, pod_name, container, tail_lines,
                since_seconds=since_seconds,
                since_time=since_time,
            ):
                data = json.dumps({"line": line})
                yield f"event: log\ndata: {data}\n\n"
        except Exception as e:
            logger.warning("日志流中断: %s", e)
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
