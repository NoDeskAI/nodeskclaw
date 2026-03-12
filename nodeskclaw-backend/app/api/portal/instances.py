"""Portal instance endpoints — with instance-level permission checks."""

import json
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import hooks
from app.core.deps import get_db
from app.core.security import get_current_user
from app.models.cluster import Cluster
from app.models.instance import Instance
from app.models.instance_member import InstanceMember, InstanceRole
from app.models.base import not_deleted
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.deploy import DeployRecordInfo
from app.schemas.instance import InstanceDetail, InstanceInfo, UpdateConfigRequest
from app.services import instance_service
from app.services import instance_member_service
from app.services.k8s.client_manager import k8s_manager
from app.services.k8s.k8s_client import K8sClient

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/check-slug", response_model=ApiResponse[dict])
async def check_slug(
    slug: str = Query(..., min_length=1),
    org_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    effective_org_id = org_id or current_user.current_org_id
    if not effective_org_id:
        return ApiResponse(data={"conflict": False, "reason": ""})
    data = await instance_service.check_slug_conflict(slug, effective_org_id, db)
    return ApiResponse(data=data)


@router.get("", response_model=ApiResponse[list[InstanceInfo]])
async def list_instances(
    cluster_id: str | None = Query(None),
    org_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    effective_org_id = current_user.current_org_id

    query = (
        select(Instance, InstanceMember.role)
        .outerjoin(
            InstanceMember,
            (InstanceMember.instance_id == Instance.id)
            & (InstanceMember.user_id == current_user.id)
            & (InstanceMember.deleted_at.is_(None)),
        )
        .where(not_deleted(Instance))
        .order_by(Instance.created_at.desc())
    )
    if cluster_id:
        query = query.where(Instance.cluster_id == cluster_id)
    if effective_org_id:
        query = query.where(Instance.org_id == effective_org_id)

    query = instance_member_service.apply_accessible_filter(
        query, current_user.id, effective_org_id, db
    )

    result = await db.execute(query)
    items = []
    for inst, member_role in result.all():
        info = InstanceInfo.model_validate(inst)
        info.my_role = member_role or (
            InstanceRole.admin
            if await _is_org_admin(current_user.id, inst.org_id, db)
            else None
        )
        items.append(info)
    return ApiResponse(data=items)


async def _is_org_admin(user_id: str, org_id: str | None, db: AsyncSession) -> bool:
    if not org_id:
        return False
    role = await instance_member_service._get_org_role(user_id, org_id, db)
    return role == "admin"


@router.get("/{instance_id}", response_model=ApiResponse[InstanceDetail])
async def get_instance(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await instance_member_service.check_instance_access(
        instance_id, current_user, InstanceRole.viewer, db
    )
    data = await instance_service.get_instance_detail(instance_id, db)
    data.my_role = await instance_member_service.get_user_instance_role(
        instance_id, current_user, db
    )
    return ApiResponse(data=data)


class ScaleBody(BaseModel):
    replicas: int


@router.delete("/{instance_id}", response_model=ApiResponse)
async def delete_instance(
    instance_id: str,
    delete_k8s: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await instance_member_service.check_instance_access(
        instance_id, current_user, InstanceRole.admin, db
    )
    await instance_service.delete_instance(instance_id, db, delete_k8s)
    await hooks.emit("operation_audit", action="instance.deleted", target_type="instance", target_id=instance_id, actor_id=current_user.id, org_id=current_user.current_org_id, details={"delete_k8s": delete_k8s, "source": "portal"})
    await _cascade_soft_delete_members(instance_id, db)
    return ApiResponse(message="实例已删除")


@router.post("/{instance_id}/scale", response_model=ApiResponse)
async def scale_instance(
    instance_id: str,
    body: ScaleBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await instance_member_service.check_instance_access(
        instance_id, current_user, InstanceRole.editor, db
    )
    await instance_service.scale_instance(instance_id, body.replicas, db)
    await hooks.emit("operation_audit", action="instance.scaled", target_type="instance", target_id=instance_id, actor_id=current_user.id, org_id=current_user.current_org_id, details={"replicas": body.replicas, "source": "portal"})
    return ApiResponse(message=f"已扩缩容至 {body.replicas} 副本")


@router.post("/{instance_id}/restart", response_model=ApiResponse)
async def restart_instance(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await instance_member_service.check_instance_access(
        instance_id, current_user, InstanceRole.editor, db
    )
    logger.info("用户 %s (%s) 请求重启实例 %s", current_user.name, current_user.id, instance_id)
    await instance_service.restart_instance(instance_id, db)
    await hooks.emit("operation_audit", action="instance.restart", target_type="instance", target_id=instance_id, actor_id=current_user.id, org_id=current_user.current_org_id, details={"source": "portal"})
    return ApiResponse(message="已触发重启，实例将在数秒后恢复")


@router.get("/{instance_id}/history", response_model=ApiResponse[list[DeployRecordInfo]])
async def deploy_history(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await instance_member_service.check_instance_access(
        instance_id, current_user, InstanceRole.viewer, db
    )
    data = await instance_service.get_deploy_history(instance_id, db)
    return ApiResponse(data=data)


@router.put("/{instance_id}/config", response_model=ApiResponse[InstanceInfo])
async def save_config(
    instance_id: str,
    body: UpdateConfigRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await instance_member_service.check_instance_access(
        instance_id, current_user, InstanceRole.editor, db
    )
    data = await instance_service.save_config(instance_id, body, db)
    await hooks.emit("operation_audit", action="instance.config_saved", target_type="instance", target_id=instance_id, actor_id=current_user.id, org_id=current_user.current_org_id, details={"source": "portal"})
    return ApiResponse(data=data)


@router.post("/{instance_id}/apply", response_model=ApiResponse[InstanceInfo])
async def apply_config(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await instance_member_service.check_instance_access(
        instance_id, current_user, InstanceRole.editor, db
    )
    data = await instance_service.apply_config(instance_id, current_user.id, db)
    await hooks.emit("operation_audit", action="instance.config_applied", target_type="instance", target_id=instance_id, actor_id=current_user.id, org_id=current_user.current_org_id, details={"source": "portal"})
    return ApiResponse(data=data)


class RollbackBody(BaseModel):
    target_revision: int


@router.post("/{instance_id}/rollback", response_model=ApiResponse[InstanceInfo])
async def rollback_instance(
    instance_id: str,
    body: RollbackBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await instance_member_service.check_instance_access(
        instance_id, current_user, InstanceRole.editor, db
    )
    data = await instance_service.rollback_instance(
        instance_id, body.target_revision, current_user.id, db
    )
    await hooks.emit("operation_audit", action="instance.rolled_back", target_type="instance", target_id=instance_id, actor_id=current_user.id, org_id=current_user.current_org_id, details={"target_revision": body.target_revision, "source": "portal"})
    return ApiResponse(data=data)


@router.post("/{instance_id}/sync-token", response_model=ApiResponse[dict])
async def sync_token(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await instance_member_service.check_instance_access(
        instance_id, current_user, InstanceRole.editor, db
    )
    token = await instance_service.sync_gateway_token(instance_id, db)
    await hooks.emit("operation_audit", action="instance.token_synced", target_type="instance", target_id=instance_id, actor_id=current_user.id, org_id=current_user.current_org_id, details={"source": "portal"})
    return ApiResponse(data={"token": token})


@router.post("/{instance_id}/regenerate-token", response_model=ApiResponse[dict])
async def regenerate_token(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await instance_member_service.check_instance_access(
        instance_id, current_user, InstanceRole.editor, db
    )
    token = await instance_service.regenerate_gateway_token(instance_id, db)
    return ApiResponse(message="已重设访问令牌，实例正在重启", data={"token": token})


@router.get("/{instance_id}/pods/{pod_name}/logs", response_model=ApiResponse[str])
async def pod_logs(
    instance_id: str,
    pod_name: str,
    container: str | None = Query(None),
    tail_lines: int = Query(200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await instance_member_service.check_instance_access(
        instance_id, current_user, InstanceRole.viewer, db
    )
    data = await instance_service.get_pod_logs(instance_id, pod_name, db, container, tail_lines)
    return ApiResponse(data=data)


@router.get("/{instance_id}/pods/{pod_name}/logs/stream")
async def pod_logs_stream(
    instance_id: str,
    pod_name: str,
    container: str | None = Query(None),
    tail_lines: int = Query(50),
    since_seconds: int | None = Query(None),
    since_time: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await instance_member_service.check_instance_access(
        instance_id, current_user, InstanceRole.viewer, db
    )
    from app.core.exceptions import NotFoundError
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


async def _cascade_soft_delete_members(instance_id: str, db: AsyncSession) -> None:
    from sqlalchemy import func, update
    await db.execute(
        update(InstanceMember)
        .where(
            InstanceMember.instance_id == instance_id,
            InstanceMember.deleted_at.is_(None),
        )
        .values(deleted_at=func.now())
    )
    await db.commit()
