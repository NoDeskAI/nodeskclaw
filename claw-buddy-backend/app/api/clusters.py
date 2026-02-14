"""Cluster management endpoints."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.exceptions import NotFoundError
from app.core.security import get_current_user
from app.models.cluster import Cluster
from app.models.user import User
from app.schemas.cluster import ClusterCreate, ClusterInfo, ClusterUpdate, ConnectionTestResult
from app.schemas.common import ApiResponse
from app.services import cluster_service
from app.services.k8s.client_manager import k8s_manager
from app.services.k8s.k8s_client import K8sClient

router = APIRouter()


@router.get("", response_model=ApiResponse[list[ClusterInfo]])
async def list_clusters(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """集群列表。"""
    data = await cluster_service.list_clusters(db)
    return ApiResponse(data=data)


@router.post("", response_model=ApiResponse[ClusterInfo])
async def create_cluster(
    body: ClusterCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """添加集群。"""
    data = await cluster_service.create_cluster(body, current_user, db)
    return ApiResponse(data=data)


@router.get("/{cluster_id}", response_model=ApiResponse[ClusterInfo])
async def get_cluster(
    cluster_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """集群详情。"""
    cluster = await cluster_service.get_cluster(cluster_id, db)
    return ApiResponse(data=ClusterInfo.model_validate(cluster))


@router.put("/{cluster_id}", response_model=ApiResponse[ClusterInfo])
async def update_cluster(
    cluster_id: str,
    body: ClusterUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """更新集群配置。"""
    data = await cluster_service.update_cluster(cluster_id, body, db)
    return ApiResponse(data=data)


@router.delete("/{cluster_id}", response_model=ApiResponse)
async def delete_cluster(
    cluster_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """删除集群。"""
    await cluster_service.delete_cluster(cluster_id, db)
    return ApiResponse(message="集群已删除")


@router.get("/{cluster_id}/health", response_model=ApiResponse[dict])
async def cluster_health(
    cluster_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """集群健康详情 + Token 过期检测。"""
    from app.services.health_checker import get_cluster_health

    data = await get_cluster_health(cluster_id, db)
    return ApiResponse(data=data)


@router.get("/{cluster_id}/overview", response_model=ApiResponse[dict])
async def cluster_overview(
    cluster_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """集群概览: 资源汇总 + 节点列表。"""
    result = await db.execute(
        select(Cluster).where(Cluster.id == cluster_id, Cluster.deleted_at.is_(None))
    )
    cluster = result.scalar_one_or_none()
    if not cluster:
        raise NotFoundError("集群不存在")

    api_client = await k8s_manager.get_or_create(cluster.id, cluster.kubeconfig_encrypted)
    k8s = K8sClient(api_client)

    summary = await k8s.get_cluster_overview()
    nodes = await k8s.list_nodes()

    # 获取 StorageClass 列表（标记哪些被 ClawBuddy 启用）
    storage_classes = []
    try:
        import json as _json
        from kubernetes_asyncio.client import StorageV1Api
        from app.services.config_service import get_config

        storage_api = StorageV1Api(api_client)
        sc_list = await storage_api.list_storage_class()

        allowed_raw = await get_config("allowed_storage_classes", db)
        allowed_names: set[str] = set()
        if allowed_raw:
            try:
                allowed_names = set(_json.loads(allowed_raw))
            except (_json.JSONDecodeError, TypeError):
                pass

        for sc in sc_list.items:
            ann = sc.metadata.annotations or {}
            is_default = ann.get("storageclass.kubernetes.io/is-default-class") == "true"
            storage_classes.append({
                "name": sc.metadata.name,
                "provisioner": sc.provisioner or "",
                "reclaim_policy": sc.reclaim_policy,
                "allow_volume_expansion": sc.allow_volume_expansion or False,
                "is_default": is_default,
                "enabled": sc.metadata.name in allowed_names,
            })
    except Exception:
        pass  # StorageClass 获取失败不影响概览

    return ApiResponse(data={"summary": summary, "nodes": nodes, "storage_classes": storage_classes})


@router.post("/{cluster_id}/test", response_model=ApiResponse[ConnectionTestResult])
async def test_connection(
    cluster_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """测试集群连接。"""
    data = await cluster_service.test_connection(cluster_id, db)
    return ApiResponse(data=data)


class KubeconfigBody(BaseModel):
    kubeconfig: str


@router.post("/{cluster_id}/kubeconfig", response_model=ApiResponse[ClusterInfo])
async def update_kubeconfig(
    cluster_id: str,
    body: KubeconfigBody,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """更新 KubeConfig（重建连接）。"""
    data = await cluster_service.update_kubeconfig(cluster_id, body.kubeconfig, db)
    return ApiResponse(data=data)
