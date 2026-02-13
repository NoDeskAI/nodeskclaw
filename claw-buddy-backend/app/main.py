"""FastAPI application entry point."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    import logging

    from sqlalchemy import select

    from app.core.deps import async_session_factory, engine
    from app.models import Base  # noqa: F811 — 导入全部模型
    from app.models.cluster import Cluster, ClusterStatus
    from app.services.k8s.client_manager import k8s_manager

    logger = logging.getLogger(__name__)

    # ── Startup ──────────────────────────────────────
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 预热 K8s 连接池：从 DB 加载所有已连接集群
    async with async_session_factory() as db:
        result = await db.execute(
            select(Cluster).where(Cluster.status == ClusterStatus.connected)
        )
        clusters = result.scalars().all()
        for cluster in clusters:
            try:
                await k8s_manager.get_or_create(cluster.id, cluster.kubeconfig_encrypted)
                logger.info("预热集群连接: %s (%s)", cluster.name, cluster.id)
            except Exception as e:
                logger.warning("预热集群 %s 失败: %s", cluster.name, e)

    # 启动集群健康巡检后台任务
    from app.services.health_checker import HealthChecker

    health_checker = HealthChecker(async_session_factory)
    health_checker.start()

    yield

    # ── Shutdown ─────────────────────────────────────
    await health_checker.stop()
    await k8s_manager.close_all()
    logger.info("已关闭所有 K8s 连接")
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Exception handlers ───────────────────────────────
register_exception_handlers(app)

# ── Routers ──────────────────────────────────────────
app.include_router(api_router, prefix="/api/v1")

# ── Static files (前端 build 产物) ───────────────────
# 生产环境：Vite build 后的 dist 目录会被复制到 static/
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
