"""Cluster service: CRUD, KubeConfig encryption, connection test."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import decrypt_kubeconfig, encrypt_kubeconfig
from app.models.cluster import Cluster, ClusterStatus
from app.models.user import User
from app.schemas.cluster import ClusterCreate, ClusterInfo, ClusterUpdate, ConnectionTestResult


async def list_clusters(db: AsyncSession) -> list[ClusterInfo]:
    result = await db.execute(select(Cluster).order_by(Cluster.created_at.desc()))
    clusters = result.scalars().all()
    return [ClusterInfo.model_validate(c) for c in clusters]


async def create_cluster(data: ClusterCreate, user: User, db: AsyncSession) -> ClusterInfo:
    # Check name uniqueness
    existing = await db.execute(select(Cluster).where(Cluster.name == data.name))
    if existing.scalar_one_or_none():
        raise ConflictError(f"集群名称 '{data.name}' 已存在")

    # Parse kubeconfig for api_server_url and auth_type
    api_server_url, auth_type = _parse_kubeconfig_meta(data.kubeconfig)

    cluster = Cluster(
        name=data.name,
        provider=data.provider,
        kubeconfig_encrypted=encrypt_kubeconfig(data.kubeconfig),
        auth_type=auth_type,
        api_server_url=api_server_url,
        status=ClusterStatus.disconnected,
        created_by=user.id,
    )
    db.add(cluster)
    await db.commit()
    await db.refresh(cluster)
    return ClusterInfo.model_validate(cluster)


async def get_cluster(cluster_id: str, db: AsyncSession) -> Cluster:
    result = await db.execute(select(Cluster).where(Cluster.id == cluster_id))
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
    await db.commit()
    await db.refresh(cluster)
    return ClusterInfo.model_validate(cluster)


async def delete_cluster(cluster_id: str, db: AsyncSession) -> None:
    cluster = await get_cluster(cluster_id, db)
    await db.delete(cluster)
    await db.commit()


async def update_kubeconfig(cluster_id: str, kubeconfig: str, db: AsyncSession) -> ClusterInfo:
    cluster = await get_cluster(cluster_id, db)
    api_server_url, auth_type = _parse_kubeconfig_meta(kubeconfig)
    cluster.kubeconfig_encrypted = encrypt_kubeconfig(kubeconfig)
    cluster.auth_type = auth_type
    cluster.api_server_url = api_server_url
    cluster.status = ClusterStatus.disconnected
    await db.commit()
    await db.refresh(cluster)
    return ClusterInfo.model_validate(cluster)


async def test_connection(cluster_id: str, db: AsyncSession) -> ConnectionTestResult:
    """Test cluster connectivity using kubernetes-asyncio."""
    cluster = await get_cluster(cluster_id, db)
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

        # Update cluster status
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
