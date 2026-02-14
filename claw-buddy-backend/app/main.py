"""FastAPI application entry point."""

import logging
import os
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers

# ── 滚动日志配置 ─────────────────────────────────────
_LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

_log_formatter = logging.Formatter(
    "%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# 文件日志：10MB 单文件，保留 5 个历史文件（共 ~60MB）
_file_handler = RotatingFileHandler(
    os.path.join(_LOG_DIR, "clawbuddy.log"),
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
_file_handler.setFormatter(_log_formatter)
_file_handler.setLevel(logging.INFO)

# 控制台日志
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_log_formatter)
_console_handler.setLevel(logging.INFO)

# 应用到 root logger
_root_logger = logging.getLogger()
_root_logger.setLevel(logging.INFO)
_root_logger.addHandler(_file_handler)
_root_logger.addHandler(_console_handler)


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

    # 自动迁移
    async with engine.begin() as conn:
        from sqlalchemy import text

        # 迁移 1: 为已有表添加 deleted_at 列（首次升级到软删除版本时执行）
        tables = ["users", "clusters", "instances", "deploy_records", "system_configs"]
        for table in tables:
            col_check = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = 'deleted_at'"
            ), {"table": table})
            if col_check.first() is None:
                await conn.execute(text(
                    f'ALTER TABLE {table} ADD COLUMN deleted_at TIMESTAMPTZ'
                ))
                await conn.execute(text(
                    f'CREATE INDEX IF NOT EXISTS ix_{table}_deleted_at ON {table}(deleted_at)'
                ))
                logger.info("自动迁移：已为 %s 表添加 deleted_at 列和索引", table)

        # 迁移 2: 为 instances 表添加 storage_class 列（NAS 持久化存储选择）
        sc_col = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'instances' AND column_name = 'storage_class'"
        ))
        if sc_col.first() is None:
            await conn.execute(text(
                "ALTER TABLE instances ADD COLUMN storage_class VARCHAR(64) NOT NULL DEFAULT 'nas-subpath'"
            ))
            logger.info("自动迁移：已为 instances 表添加 storage_class 列")

        # 迁移 3: 将 instances.storage_size 默认值改为 80Gi
        await conn.execute(text(
            "ALTER TABLE instances ALTER COLUMN storage_size SET DEFAULT '80Gi'"
        ))

        # 迁移 4: 将 instances.name 的 unique 约束替换为 partial unique index（兼容软删除）
        # 旧约束 instances_name_key 不兼容软删除，已删除的记录会阻止同名重建
        old_constraint = await conn.execute(text(
            "SELECT 1 FROM pg_constraint WHERE conname = 'instances_name_key'"
        ))
        if old_constraint.first() is not None:
            await conn.execute(text("ALTER TABLE instances DROP CONSTRAINT instances_name_key"))
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_instances_name_active "
                "ON instances (name) WHERE deleted_at IS NULL"
            ))
            logger.info("自动迁移：已将 instances.name 唯一约束替换为 partial unique index")

    # 预热 K8s 连接池：从 DB 加载所有已连接集群
    async with async_session_factory() as db:
        result = await db.execute(
            select(Cluster).where(
                Cluster.status == ClusterStatus.connected,
                Cluster.deleted_at.is_(None),
            )
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
