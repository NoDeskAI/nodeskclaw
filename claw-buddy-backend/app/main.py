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

        # ── 迁移 5: SaaS 多租户字段 ──────────────────────

        # 5a: users 表新增 is_super_admin
        col = await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'is_super_admin'"
        ))
        if col.first() is None:
            await conn.execute(text(
                "ALTER TABLE users ADD COLUMN is_super_admin BOOLEAN NOT NULL DEFAULT false"
            ))
            # 把现有 admin 用户提升为 super_admin
            await conn.execute(text(
                "UPDATE users SET is_super_admin = true WHERE role = 'admin'"
            ))
            logger.info("自动迁移：已为 users 表添加 is_super_admin 列")

        # 5b: users 表新增 current_org_id
        col = await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'current_org_id'"
        ))
        if col.first() is None:
            await conn.execute(text(
                "ALTER TABLE users ADD COLUMN current_org_id VARCHAR(36) "
                "REFERENCES organizations(id)"
            ))
            logger.info("自动迁移：已为 users 表添加 current_org_id 列")

        # 5c: instances 表新增 org_id
        col = await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'instances' AND column_name = 'org_id'"
        ))
        if col.first() is None:
            await conn.execute(text(
                "ALTER TABLE instances ADD COLUMN org_id VARCHAR(36) "
                "REFERENCES organizations(id)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_instances_org_id ON instances(org_id)"
            ))
            logger.info("自动迁移：已为 instances 表添加 org_id 列")

        # 5d: clusters 表新增 org_id
        col = await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'clusters' AND column_name = 'org_id'"
        ))
        if col.first() is None:
            await conn.execute(text(
                "ALTER TABLE clusters ADD COLUMN org_id VARCHAR(36) "
                "REFERENCES organizations(id)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_clusters_org_id ON clusters(org_id)"
            ))
            logger.info("自动迁移：已为 clusters 表添加 org_id 列")

    # ── 迁移 5e: 种子数据（默认组织 + 套餐 + 数据归属） ──
    async with async_session_factory() as db:
        from app.models.org_membership import OrgMembership, OrgRole
        from app.models.organization import Organization
        from app.models.plan import Plan

        # 检查是否已有组织（幂等）
        org_result = await db.execute(
            select(Organization).where(Organization.slug == "default")
        )
        default_org = org_result.scalar_one_or_none()

        if default_org is None:
            import uuid
            default_org_id = str(uuid.uuid4())
            default_org = Organization(
                id=default_org_id,
                name="默认组织",
                slug="default",
                plan="pro",
                max_instances=50,
                max_cpu_total="200",
                max_mem_total="400Gi",
            )
            db.add(default_org)
            await db.flush()

            # 把现有用户全部归入默认组织
            users_result = await db.execute(
                select(User).where(User.deleted_at.is_(None))
            )
            for u in users_result.scalars().all():
                membership = OrgMembership(
                    user_id=u.id,
                    org_id=default_org.id,
                    role=OrgRole.admin if u.role == "admin" else OrgRole.member,
                )
                db.add(membership)
                u.current_org_id = default_org.id

            # 把现有实例归入默认组织
            from app.models.instance import Instance
            inst_result = await db.execute(
                select(Instance).where(
                    Instance.org_id.is_(None),
                    Instance.deleted_at.is_(None),
                )
            )
            for inst in inst_result.scalars().all():
                inst.org_id = default_org.id

            await db.commit()
            logger.info("自动迁移：已创建默认组织并迁移现有数据")

        # 种子套餐（幂等）
        plan_result = await db.execute(select(Plan).limit(1))
        if plan_result.scalar_one_or_none() is None:
            seed_plans = [
                Plan(
                    name="free", display_name="免费版",
                    max_instances=1,
                    max_cpu_per_instance="2000m", max_mem_per_instance="4Gi",
                    allowed_specs='["small"]',
                    dedicated_cluster=False, price_monthly=0,
                ),
                Plan(
                    name="pro", display_name="专业版",
                    max_instances=10,
                    max_cpu_per_instance="4000m", max_mem_per_instance="8Gi",
                    allowed_specs='["small","medium"]',
                    dedicated_cluster=False, price_monthly=9900,
                ),
                Plan(
                    name="enterprise", display_name="企业版",
                    max_instances=50,
                    max_cpu_per_instance="8000m", max_mem_per_instance="16Gi",
                    allowed_specs='["small","medium","large"]',
                    dedicated_cluster=True, price_monthly=49900,
                ),
            ]
            db.add_all(seed_plans)
            await db.commit()
            logger.info("自动迁移：已种子化 3 个套餐")

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
