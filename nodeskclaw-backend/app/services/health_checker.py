"""Cluster health checker: periodic background task that polls all connected clusters."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.cluster import Cluster, ClusterStatus
from app.services.k8s.event_bus import event_bus

logger = logging.getLogger(__name__)

HEALTH_CHECK_INTERVAL = 60  # seconds


class HealthChecker:
    """Background task: polls cluster health every HEALTH_CHECK_INTERVAL seconds."""

    def __init__(self, session_factory: async_sessionmaker):
        self._session_factory = session_factory
        self._task: asyncio.Task | None = None

    def start(self):
        self._task = asyncio.create_task(self._loop())
        logger.info("集群健康巡检已启动 (间隔 %ds)", HEALTH_CHECK_INTERVAL)

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("集群健康巡检已停止")

    async def _loop(self):
        while True:
            try:
                await self._check_all()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("健康巡检异常")
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)

    async def _check_all(self):
        async with self._session_factory() as db:
            result = await db.execute(
                select(Cluster).where(
                    Cluster.status == ClusterStatus.connected,
                    Cluster.compute_provider == "k8s",
                    Cluster.deleted_at.is_(None),
                )
            )
            clusters = result.scalars().all()

            for cluster in clusters:
                await self._check_one(cluster, db)

            await db.commit()

    async def _check_one(self, cluster: Cluster, db):
        old_status = cluster.health_status
        now = datetime.now(timezone.utc)

        try:
            from app.services.runtime.registries.compute_registry import require_k8s_client
            k8s = await require_k8s_client(cluster)
            info = await k8s.test_connection()
            cluster.health_status = "healthy"
            cluster.set_provider_value("k8s_version", info.get("version"))
            cluster.last_health_check = now

            # 检测 token 过期
            if cluster.token_expires_at and cluster.token_expires_at < now:
                cluster.health_status = "token_expired"
                logger.warning("集群 %s token 已过期", cluster.name)

        except Exception as e:
            cluster.health_status = "unhealthy"
            cluster.last_health_check = now
            logger.warning("集群 %s 健康检查失败: %s", cluster.name, e)

        # 状态变更时推送事件
        if old_status != cluster.health_status:
            event_bus.publish(
                "cluster_health",
                {
                    "cluster_id": cluster.id,
                    "cluster_name": cluster.name,
                    "old_status": old_status,
                    "new_status": cluster.health_status,
                },
            )
            logger.info(
                "集群 %s 健康状态变更: %s -> %s",
                cluster.name, old_status, cluster.health_status,
            )


async def get_cluster_health(cluster_id: str, db, org_id: str | None = None) -> dict:
    """Return health details for a single cluster."""
    query = select(Cluster).where(Cluster.id == cluster_id, Cluster.deleted_at.is_(None))
    if org_id:
        query = query.where(Cluster.org_id == org_id)
    result = await db.execute(query)
    cluster = result.scalar_one_or_none()
    if not cluster:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("集群不存在")

    now = datetime.now(timezone.utc)
    token_warning = None
    if cluster.token_expires_at:
        remaining = (cluster.token_expires_at - now).total_seconds()
        if remaining <= 0:
            token_warning = "expired"
        elif remaining < 6 * 3600:  # < 6 hours
            token_warning = "warning"

    health = {
        "cluster_id": cluster.id,
        "name": cluster.name,
        "status": cluster.status,
        "health_status": cluster.health_status or "unknown",
        "k8s_version": cluster.k8s_version,
        "last_health_check": cluster.last_health_check.isoformat() if cluster.last_health_check else None,
        "token_expires_at": cluster.token_expires_at.isoformat() if cluster.token_expires_at else None,
        "token_expired": bool(
            cluster.token_expires_at and cluster.token_expires_at < now
        ),
        "token_warning": token_warning,  # null | "warning" | "expired"
    }

    # 尝试获取实时集群概览
    if cluster.status == ClusterStatus.connected and cluster.is_k8s and cluster.credentials_encrypted:
        try:
            from app.services.runtime.registries.compute_registry import require_k8s_client
            k8s = await require_k8s_client(cluster)
            overview = await k8s.get_cluster_overview()
            health["overview"] = overview
        except Exception as e:
            health["overview"] = None
            health["overview_error"] = str(e)

    return health
