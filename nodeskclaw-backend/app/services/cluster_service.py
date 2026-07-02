"""Cluster service: CRUD, KubeConfig encryption, connection test."""

import logging

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError

from app.core.security import decrypt_kubeconfig, encrypt_kubeconfig
from app.models.cluster import Cluster, ClusterStatus
from app.models.corridor import HexConnection
from app.models.deploy_record import DeployRecord
from app.models.instance import Instance
from app.models.node_card import NodeCard
from app.models.user import User
from app.models.workspace_agent import WorkspaceAgent
from app.schemas.cluster import ClusterCreate, ClusterInfo, ClusterUpdate, ConnectionTestResult

logger = logging.getLogger(__name__)


async def list_clusters(db: AsyncSession, org_id: str | None = None) -> list[ClusterInfo]:
    query = select(Cluster).where(Cluster.deleted_at.is_(None))
    if org_id:
        query = query.where(Cluster.org_id == org_id)
    result = await db.execute(query.order_by(Cluster.created_at.desc()))
    clusters = result.scalars().all()
    return [ClusterInfo.model_validate(c) for c in clusters]


async def create_cluster(
    data: ClusterCreate, user: User, db: AsyncSession, org_id: str | None = None,
) -> ClusterInfo:
    """集群创建入口，仅支持 K8s 集群。"""
    compute = data.compute_provider or "k8s"
    if compute != "k8s":
        raise BadRequestError(
            message=f"不支持的集群类型 '{compute}'，仅支持 K8s 集群",
            message_key="errors.cluster.compute_provider_not_supported",
        )

    name_query = select(Cluster).where(
        Cluster.name == data.name, Cluster.deleted_at.is_(None),
    )
    if org_id:
        name_query = name_query.where(Cluster.org_id == org_id)
    existing = await db.execute(name_query)
    if existing.scalar_one_or_none():
        raise ConflictError(f"集群名称 '{data.name}' 已存在")

    if not data.kubeconfig:
        raise BadRequestError(
            message="K8s 集群必须提供 KubeConfig",
            message_key="errors.cluster.kubeconfig_required",
        )

    api_server_url, auth_type = _parse_kubeconfig_meta(data.kubeconfig)

    effective_proxy = data.proxy_endpoint
    if effective_proxy and api_server_url:
        effective_proxy = await _adopt_existing_proxy_endpoint(
            db, api_server_url, effective_proxy,
        )

    cluster = Cluster(
        name=data.name,
        compute_provider="k8s",
        credentials_encrypted=encrypt_kubeconfig(data.kubeconfig),
        provider_config={
            "cloud_vendor": data.provider,
            "auth_type": auth_type,
            "api_server_url": api_server_url,
            "ingress_class": data.ingress_class,
        },
        proxy_endpoint=effective_proxy,
        status=ClusterStatus.disconnected,
        created_by=user.id,
        org_id=org_id,
    )
    db.add(cluster)
    await db.commit()
    await db.refresh(cluster)

    if cluster.proxy_endpoint:
        await _ensure_gateway_proxy_service(
            cluster.id, cluster.proxy_endpoint, api_server_url,
        )

    return ClusterInfo.model_validate(cluster)


async def get_cluster(cluster_id: str, db: AsyncSession, org_id: str | None = None) -> Cluster:
    query = select(Cluster).where(Cluster.id == cluster_id, Cluster.deleted_at.is_(None))
    if org_id:
        query = query.where(Cluster.org_id == org_id)
    result = await db.execute(query)
    cluster = result.scalar_one_or_none()
    if not cluster:
        raise NotFoundError("集群不存在")
    return cluster


async def update_cluster(
    cluster_id: str, data: ClusterUpdate, db: AsyncSession, org_id: str | None = None,
) -> ClusterInfo:
    cluster = await get_cluster(cluster_id, db, org_id)
    if data.name is not None:
        cluster.name = data.name
    if data.provider is not None:
        cluster.set_provider_value("cloud_vendor", data.provider)
    if data.ingress_class is not None:
        cluster.set_provider_value("ingress_class", data.ingress_class)
    if data.proxy_endpoint is not None:
        cluster.proxy_endpoint = data.proxy_endpoint
        api_url = cluster.api_server_url
        if api_url and data.proxy_endpoint:
            stale = await db.execute(
                select(Cluster).where(
                    Cluster.deleted_at.is_(None),
                    Cluster.id != cluster.id,
                    Cluster.proxy_endpoint.isnot(None),
                    Cluster.proxy_endpoint != data.proxy_endpoint,
                    Cluster.provider_config["api_server_url"].as_string() == api_url,
                )
            )
            for other in stale.scalars():
                logger.warning(
                    "集群 %s (id=%s) 的 proxy_endpoint 仍为 %s，"
                    "与同物理集群 %s 的新值 %s 不一致，请同步更新",
                    other.name, other.id[:8], other.proxy_endpoint,
                    cluster.name, data.proxy_endpoint,
                )
    await db.commit()
    await db.refresh(cluster)

    if cluster.proxy_endpoint:
        await _ensure_gateway_proxy_service(
            cluster.id, cluster.proxy_endpoint, cluster.api_server_url,
        )

    return ClusterInfo.model_validate(cluster)


async def delete_cluster(cluster_id: str, db: AsyncSession, org_id: str | None = None) -> None:
    """逻辑删除集群，级联逻辑删除其下所有实例和部署记录。"""
    cluster = await get_cluster(cluster_id, db, org_id)

    # 查询该集群下所有未删除的实例
    inst_result = await db.execute(
        select(Instance).where(Instance.cluster_id == cluster.id, Instance.deleted_at.is_(None))
    )
    instance_ids = [inst.id for inst in inst_result.scalars().all()]

    # 级联逻辑删除部署记录
    if instance_ids:
        await db.execute(
            update(DeployRecord)
            .where(DeployRecord.instance_id.in_(instance_ids), DeployRecord.deleted_at.is_(None))
            .values(deleted_at=func.now())
        )

        wa_result = await db.execute(
            select(WorkspaceAgent.workspace_id, WorkspaceAgent.hex_q, WorkspaceAgent.hex_r)
            .where(
                WorkspaceAgent.instance_id.in_(instance_ids),
                WorkspaceAgent.deleted_at.is_(None),
            )
        )
        wa_positions = wa_result.all()

        await db.execute(
            update(WorkspaceAgent)
            .where(WorkspaceAgent.instance_id.in_(instance_ids), WorkspaceAgent.deleted_at.is_(None))
            .values(deleted_at=func.now())
        )

        await db.execute(
            update(NodeCard)
            .where(NodeCard.node_id.in_(instance_ids), NodeCard.deleted_at.is_(None))
            .values(deleted_at=func.now())
        )

        from sqlalchemy import or_, and_
        if wa_positions:
            hex_filters = [
                and_(
                    HexConnection.workspace_id == ws_id,
                    or_(
                        and_(HexConnection.hex_a_q == hq, HexConnection.hex_a_r == hr),
                        and_(HexConnection.hex_b_q == hq, HexConnection.hex_b_r == hr),
                    ),
                )
                for ws_id, hq, hr in wa_positions
            ]
            await db.execute(
                update(HexConnection)
                .where(or_(*hex_filters), HexConnection.deleted_at.is_(None))
                .values(deleted_at=func.now())
            )

        # 级联逻辑删除实例
        await db.execute(
            update(Instance)
            .where(Instance.cluster_id == cluster.id, Instance.deleted_at.is_(None))
            .values(deleted_at=func.now())
        )

    # 逻辑删除集群自身
    cluster.soft_delete()
    await db.commit()


async def update_kubeconfig(
    cluster_id: str, kubeconfig: str, db: AsyncSession, org_id: str | None = None,
) -> ClusterInfo:
    cluster = await get_cluster(cluster_id, db, org_id)
    api_server_url, auth_type = _parse_kubeconfig_meta(kubeconfig)
    cluster.credentials_encrypted = encrypt_kubeconfig(kubeconfig)
    cluster.set_provider_value("auth_type", auth_type)
    cluster.set_provider_value("api_server_url", api_server_url)

    # 清除旧的 K8s 客户端缓存，使用新 KubeConfig 重新连接
    from app.services.k8s.client_manager import k8s_manager
    await k8s_manager.remove(cluster_id)

    # 自动测试新 KubeConfig 的连通性
    try:
        from app.services.k8s.client_manager import create_temp_client
        from kubernetes_asyncio.client import VersionApi

        async with create_temp_client(kubeconfig) as api_client:
            info = await VersionApi(api_client).get_code()

        cluster.status = ClusterStatus.connected
        cluster.set_provider_value("k8s_version", info.git_version)
        cluster.health_status = "healthy"
    except Exception:
        logger.warning("KubeConfig connectivity test failed for cluster %s", cluster_id, exc_info=True)
        cluster.status = ClusterStatus.disconnected
        cluster.health_status = "unhealthy"

    await db.commit()
    await db.refresh(cluster)
    return ClusterInfo.model_validate(cluster)


async def test_connection(
    cluster_id: str, db: AsyncSession, org_id: str | None = None,
) -> ConnectionTestResult:
    """Test cluster connectivity."""
    cluster = await get_cluster(cluster_id, db, org_id)

    kubeconfig_plain = decrypt_kubeconfig(cluster.credentials_encrypted)

    try:
        from app.services.k8s.client_manager import create_temp_client

        async with create_temp_client(kubeconfig_plain) as api_client:
            from kubernetes_asyncio.client import VersionApi

            version_api = VersionApi(api_client)
            info = await version_api.get_code()

            from kubernetes_asyncio.client import CoreV1Api

            core_api = CoreV1Api(api_client)
            nodes = await core_api.list_node()

        cluster.status = ClusterStatus.connected
        cluster.set_provider_value("k8s_version", info.git_version)
        cluster.health_status = "healthy"
        await db.commit()

        return ConnectionTestResult(
            ok=True,
            version=info.git_version,
            nodes=len(nodes.items),
        )
    except Exception as e:
        cluster.status = ClusterStatus.disconnected
        cluster.health_status = "unhealthy"
        await db.commit()
        return ConnectionTestResult(ok=False, message=str(e))


def _parse_kubeconfig_meta(kubeconfig: str) -> tuple[str, str]:
    """Extract api_server_url and auth_type from kubeconfig YAML."""
    import yaml

    try:
        config = yaml.safe_load(kubeconfig)
        clusters = config.get("clusters", [])
        api_server = clusters[0]["cluster"]["server"] if clusters else ""

        users = config.get("users", [])
        user_data = users[0]["user"] if users else {}

        if "token" in user_data:
            auth_type = "token"
        elif "client-certificate-data" in user_data:
            auth_type = "certificate"
        elif "exec" in user_data:
            auth_type = "exec"
        else:
            auth_type = "unknown"

        return api_server, auth_type
    except Exception:
        return "", "unknown"


async def _adopt_existing_proxy_endpoint(
    db: AsyncSession, api_server_url: str, proposed: str,
) -> str:
    """If another cluster with the same api_server_url already has a proxy_endpoint, adopt it."""
    existing = await db.execute(
        select(Cluster).where(
            Cluster.deleted_at.is_(None),
            Cluster.proxy_endpoint.isnot(None),
            Cluster.proxy_endpoint != "",
            Cluster.provider_config["api_server_url"].as_string() == api_server_url,
        )
    )
    other = existing.scalars().first()
    if other and other.proxy_endpoint != proposed:
        logger.warning(
            "同物理集群 (api_server=%s) 已有集群 %s 使用 proxy_endpoint=%s，"
            "自动采用已有配置（忽略传入的 %s）",
            api_server_url[:30], other.name, other.proxy_endpoint, proposed,
        )
        return other.proxy_endpoint
    return proposed


async def _ensure_gateway_proxy_service(
    cluster_id: str,
    proxy_endpoint: str,
    api_server_url: str | None = None,
) -> None:
    """在 infra 网关集群创建/更新 ExternalName Service，指向 inst 集群 ALB。

    If a service for the same physical cluster already exists (matched by api-server-hash),
    updates that service instead of creating a new one.
    """
    try:
        from app.services.k8s.client_manager import GATEWAY_NS, k8s_manager
        from app.services.k8s.k8s_client import K8sClient
        from app.services.k8s.resource_builder import build_external_name_service

        gateway_api = await k8s_manager.get_gateway_client()
        gateway_k8s = K8sClient(gateway_api)

        target_name: str | None = None
        if api_server_url:
            from app.services.k8s.proxy_helpers import (
                compute_api_server_hash,
                find_proxy_svc_for_cluster,
            )
            api_hash = compute_api_server_hash(api_server_url)
            target_name = await find_proxy_svc_for_cluster(
                gateway_k8s.core, GATEWAY_NS, api_hash,
            )

        ext_svc = build_external_name_service(cluster_id, proxy_endpoint, api_server_url)

        if target_name:
            await gateway_k8s.core.patch_namespaced_service(
                target_name, GATEWAY_NS, ext_svc,
            )
            logger.info(
                "已更新共享 ExternalName Service: %s -> %s", target_name, proxy_endpoint,
            )
        else:
            try:
                await gateway_k8s.core.create_namespaced_service(GATEWAY_NS, ext_svc)
                logger.info(
                    "已创建 ExternalName Service: %s -> %s",
                    ext_svc.metadata.name, proxy_endpoint,
                )
            except Exception:
                await gateway_k8s.core.patch_namespaced_service(
                    ext_svc.metadata.name, GATEWAY_NS, ext_svc,
                )
                logger.info(
                    "已更新 ExternalName Service: %s -> %s",
                    ext_svc.metadata.name, proxy_endpoint,
                )
    except Exception as e:
        logger.warning("创建网关 ExternalName Service 失败: %s", e)
