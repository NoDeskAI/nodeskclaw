"""Cluster service: CRUD, KubeConfig encryption, connection test."""

import asyncio
import logging

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.feature_gate import feature_gate
from app.core.security import decrypt_kubeconfig, encrypt_kubeconfig
from app.models.cluster import Cluster, ClusterStatus
from app.models.deploy_record import DeployRecord
from app.models.instance import Instance
from app.models.user import User
from app.schemas.cluster import ClusterCreate, ClusterInfo, ClusterUpdate, ConnectionTestResult

logger = logging.getLogger(__name__)


async def list_clusters(db: AsyncSession) -> list[ClusterInfo]:
    result = await db.execute(
        select(Cluster).where(Cluster.deleted_at.is_(None)).order_by(Cluster.created_at.desc())
    )
    clusters = result.scalars().all()
    return [ClusterInfo.model_validate(c) for c in clusters]


async def create_cluster(
    data: ClusterCreate, user: User, db: AsyncSession, org_id: str | None = None,
) -> ClusterInfo:
    if not feature_gate.is_enabled("multi_cluster"):
        count_result = await db.execute(
            select(func.count(Cluster.id)).where(
                Cluster.deleted_at.is_(None),
                Cluster.compute_provider == "k8s",
            )
        )
        if count_result.scalar_one() >= 1:
            raise ConflictError(
                message="已配置集群，当前仅支持单集群",
                message_key="errors.cluster.single_cluster_limit",
            )

    # CE 互斥：当前组织已有 Docker 集群时拒绝创建 K8s 集群
    if org_id:
        docker_exists = await db.execute(
            select(Cluster.id).where(
                Cluster.org_id == org_id,
                Cluster.compute_provider == "docker",
                Cluster.deleted_at.is_(None),
            )
        )
        if docker_exists.scalar_one_or_none():
            raise ConflictError(
                message="当前组织已启用 Docker 运行环境，无法同时添加 K8s 集群",
                message_key="errors.cluster.docker_k8s_mutual_exclusive",
            )

    name_query = select(Cluster).where(
        Cluster.name == data.name, Cluster.deleted_at.is_(None),
    )
    if org_id:
        name_query = name_query.where(Cluster.org_id == org_id)
    existing = await db.execute(name_query)
    if existing.scalar_one_or_none():
        raise ConflictError(f"集群名称 '{data.name}' 已存在")

    api_server_url, auth_type = _parse_kubeconfig_meta(data.kubeconfig)

    cluster = Cluster(
        name=data.name,
        provider=data.provider,
        compute_provider="k8s",
        kubeconfig_encrypted=encrypt_kubeconfig(data.kubeconfig),
        auth_type=auth_type,
        api_server_url=api_server_url,
        ingress_class=data.ingress_class,
        proxy_endpoint=data.proxy_endpoint,
        status=ClusterStatus.disconnected,
        created_by=user.id,
        org_id=org_id,
    )
    db.add(cluster)
    await db.commit()
    await db.refresh(cluster)

    if cluster.proxy_endpoint:
        await _ensure_gateway_proxy_service(cluster.id, cluster.proxy_endpoint)

    return ClusterInfo.model_validate(cluster)


async def get_cluster(cluster_id: str, db: AsyncSession) -> Cluster:
    result = await db.execute(
        select(Cluster).where(Cluster.id == cluster_id, Cluster.deleted_at.is_(None))
    )
    cluster = result.scalar_one_or_none()
    if not cluster:
        raise NotFoundError("集群不存在")
    return cluster


async def update_cluster(cluster_id: str, data: ClusterUpdate, db: AsyncSession) -> ClusterInfo:
    cluster = await get_cluster(cluster_id, db)
    if data.name is not None:
        cluster.name = data.name
    if data.provider is not None:
        cluster.provider = data.provider
    if data.ingress_class is not None:
        cluster.ingress_class = data.ingress_class
    if data.proxy_endpoint is not None:
        cluster.proxy_endpoint = data.proxy_endpoint
    await db.commit()
    await db.refresh(cluster)

    if cluster.proxy_endpoint:
        await _ensure_gateway_proxy_service(cluster.id, cluster.proxy_endpoint)

    return ClusterInfo.model_validate(cluster)


async def delete_cluster(cluster_id: str, db: AsyncSession) -> None:
    """逻辑删除集群，级联逻辑删除其下所有实例和部署记录。"""
    cluster = await get_cluster(cluster_id, db)

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
        # 级联逻辑删除实例
        await db.execute(
            update(Instance)
            .where(Instance.cluster_id == cluster.id, Instance.deleted_at.is_(None))
            .values(deleted_at=func.now())
        )

    # 逻辑删除集群自身
    cluster.soft_delete()
    await db.commit()


async def update_kubeconfig(cluster_id: str, kubeconfig: str, db: AsyncSession) -> ClusterInfo:
    cluster = await get_cluster(cluster_id, db)
    api_server_url, auth_type = _parse_kubeconfig_meta(kubeconfig)
    cluster.kubeconfig_encrypted = encrypt_kubeconfig(kubeconfig)
    cluster.auth_type = auth_type
    cluster.api_server_url = api_server_url

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
        cluster.k8s_version = info.git_version
        cluster.health_status = "healthy"
    except Exception:
        cluster.status = ClusterStatus.disconnected
        cluster.health_status = "unhealthy"

    await db.commit()
    await db.refresh(cluster)
    return ClusterInfo.model_validate(cluster)


async def create_docker_cluster(
    name: str, user: User, org_id: str, db: AsyncSession,
) -> ClusterInfo:
    """创建 Docker 运行环境（特殊集群）。org_id 必填。"""
    if not org_id:
        raise BadRequestError("Docker 集群必须归属组织")

    # 互斥：当前组织已有 K8s 集群时拒绝
    k8s_exists = await db.execute(
        select(Cluster.id).where(
            Cluster.org_id == org_id,
            Cluster.compute_provider == "k8s",
            Cluster.deleted_at.is_(None),
        )
    )
    if k8s_exists.scalar_one_or_none():
        raise ConflictError(
            message="当前组织已有 K8s 集群，无法同时启用 Docker 运行环境",
            message_key="errors.cluster.docker_k8s_mutual_exclusive",
        )

    # 唯一性：每个组织只能有一个 Docker 集群
    docker_exists = await db.execute(
        select(Cluster.id).where(
            Cluster.org_id == org_id,
            Cluster.compute_provider == "docker",
            Cluster.deleted_at.is_(None),
        )
    )
    if docker_exists.scalar_one_or_none():
        raise ConflictError(
            message="当前组织已有 Docker 运行环境",
            message_key="errors.cluster.docker_already_exists",
        )

    # Docker 环境检查
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode().strip() or "docker compose 不可用")
    except FileNotFoundError:
        raise BadRequestError("Docker 未安装或不在 PATH 中")
    except asyncio.TimeoutError:
        raise BadRequestError("Docker 环境检查超时")

    cluster = Cluster(
        name=name or "local-docker",
        provider="docker",
        compute_provider="docker",
        kubeconfig_encrypted="",
        auth_type="none",
        status=ClusterStatus.connected,
        health_status="healthy",
        created_by=user.id,
        org_id=org_id,
    )
    db.add(cluster)
    await db.commit()
    await db.refresh(cluster)
    return ClusterInfo.model_validate(cluster)


async def test_connection(cluster_id: str, db: AsyncSession) -> ConnectionTestResult:
    """Test cluster connectivity."""
    cluster = await get_cluster(cluster_id, db)

    if cluster.compute_provider == "docker":
        return await _test_docker_connection(cluster, db)

    kubeconfig_plain = decrypt_kubeconfig(cluster.kubeconfig_encrypted)

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
        cluster.k8s_version = info.git_version
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


async def _test_docker_connection(
    cluster: Cluster, db: AsyncSession,
) -> ConnectionTestResult:
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode != 0:
            cluster.status = ClusterStatus.disconnected
            cluster.health_status = "unhealthy"
            await db.commit()
            return ConnectionTestResult(ok=False, message=stderr.decode().strip())

        version_str = stdout.decode().strip()
        cluster.status = ClusterStatus.connected
        cluster.health_status = "healthy"
        await db.commit()
        return ConnectionTestResult(ok=True, version=version_str)
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


async def _ensure_gateway_proxy_service(cluster_id: str, proxy_endpoint: str) -> None:
    """在 infra 网关集群创建/更新 ExternalName Service，指向 inst 集群 ALB。"""
    try:
        from app.services.k8s.client_manager import GATEWAY_NS, k8s_manager
        from app.services.k8s.k8s_client import K8sClient
        from app.services.k8s.resource_builder import build_external_name_service

        gateway_api = await k8s_manager.get_gateway_client()
        gateway_k8s = K8sClient(gateway_api)
        ext_svc = build_external_name_service(cluster_id, proxy_endpoint)

        try:
            await gateway_k8s.core.create_namespaced_service(GATEWAY_NS, ext_svc)
            logger.info("已在网关集群创建 ExternalName Service: %s -> %s", ext_svc.metadata.name, proxy_endpoint)
        except Exception:
            await gateway_k8s.core.patch_namespaced_service(
                ext_svc.metadata.name, GATEWAY_NS, ext_svc,
            )
            logger.info("已在网关集群更新 ExternalName Service: %s -> %s", ext_svc.metadata.name, proxy_endpoint)
    except Exception as e:
        logger.warning("创建网关 ExternalName Service 失败: %s", e)
