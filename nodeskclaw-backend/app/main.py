"""FastAPI application entry point."""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import admin_router, api_router, webhook_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers

# ── 滚动日志配置 ─────────────────────────────────────
_LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

_log_formatter = logging.Formatter(
    "%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class _ColorFormatter(logging.Formatter):
    _COLORS = {
        logging.DEBUG: "\033[37m",       # grey
        logging.INFO: "\033[32m",        # green
        logging.WARNING: "\033[33m",     # yellow
        logging.ERROR: "\033[31m",       # red
        logging.CRITICAL: "\033[1;31m",  # bold red
    }
    _RESET = "\033[0m"

    def __init__(self):
        super().__init__(
            "%(asctime)s %(colored_level)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    def format(self, record):
        color = self._COLORS.get(record.levelno, "")
        record.colored_level = f"{color}%(levelname)-5s{self._RESET}" % {"levelname": record.levelname}
        return super().format(record)


# 文件日志：10MB 单文件，保留 5 个历史文件（共 ~60MB）
_file_handler = RotatingFileHandler(
    os.path.join(_LOG_DIR, "nodeskclaw.log"),
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
_file_handler.setFormatter(_log_formatter)
_file_handler.setLevel(logging.INFO)

# 控制台日志（带颜色）
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_ColorFormatter())
_console_handler.setLevel(logging.INFO)

# 应用到 root logger
_root_logger = logging.getLogger()
_root_logger.setLevel(logging.INFO)
_root_logger.addHandler(_file_handler)
_root_logger.addHandler(_console_handler)

logging.getLogger("sqlalchemy.engine").setLevel(
    logging.INFO if settings.LOG_SQL else logging.WARNING
)

for _uv_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    _uv_logger = logging.getLogger(_uv_name)
    _uv_logger.handlers.clear()
    _uv_logger.propagate = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    import logging

    from sqlalchemy import select

    from app.core.deps import async_session_factory, engine
    from app.models.cluster import Cluster, ClusterStatus
    from app.services.k8s.client_manager import k8s_manager
    from app.utils.oauth_providers.feishu import FeishuProvider
    from app.utils.oauth_providers.registry import register_provider

    logger = logging.getLogger(__name__)

    # ── EE Model 注册（在 create_all 之前导入，使其加入 Base.metadata）──
    from app.core.feature_gate import feature_gate as _fg
    if _fg.is_ee:
        _proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        if _proj_root not in sys.path:
            sys.path.insert(0, _proj_root)
        try:
            import ee.backend.models  # noqa: F401
            logger.info("EE Models 已注册")
        except ImportError:
            pass

    # ── Startup ──────────────────────────────────────
    register_provider(FeishuProvider())

    # ── 自动创建开发数据库（仅 DATABASE_NAME_SUFFIX 非空时触发）──
    if settings.DATABASE_NAME_SUFFIX:
        import asyncpg
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1))
        target_db = parsed.path.lstrip("/")
        db_user = parsed.username or ""
        admin_url = urlunparse(parsed._replace(path="/postgres"))
        _auto_conn = await asyncpg.connect(admin_url)
        try:
            exists = await _auto_conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", target_db
            )
            if not exists:
                await _auto_conn.execute(f'CREATE DATABASE "{target_db}"')
                logger.info("自动创建开发数据库: %s", target_db)
            else:
                logger.info("开发数据库已存在: %s", target_db)
        finally:
            await _auto_conn.close()

        _target_url = urlunparse(parsed._replace(path=f"/{target_db}"))
        _target_conn = await asyncpg.connect(_target_url)
        try:
            await _target_conn.execute(
                "CREATE SCHEMA IF NOT EXISTS nodeskclaw AUTHORIZATION current_user"
            )
            await _target_conn.execute(
                f'ALTER DATABASE "{target_db}" SET search_path TO nodeskclaw, public'
            )
            await _target_conn.execute("SET search_path TO nodeskclaw, public")
            logger.info("开发数据库 schema 已就绪: nodeskclaw (search_path = nodeskclaw, public)")
        finally:
            await _target_conn.close()

    # ── 自动迁移（Alembic upgrade head，幂等）──
    async def _auto_migrate():
        from alembic.config import Config
        from alembic import command

        def _run():
            root_log = logging.getLogger()
            saved_handlers = root_log.handlers[:]
            saved_level = root_log.level

            backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            cfg = Config(os.path.join(backend_root, "alembic.ini"))
            cfg.set_main_option("script_location", os.path.join(backend_root, "alembic"))
            command.upgrade(cfg, "head")

            # alembic.ini 的 [loggers] 节会通过 fileConfig() 覆盖 root logger，
            # 将级别设为 WARNING 并替换所有 handler，导致后续 INFO 日志全部丢失。
            # 此处恢复应用自身的日志配置。
            root_log.handlers = saved_handlers
            root_log.level = saved_level
            for name in logging.Logger.manager.loggerDict:
                obj = logging.Logger.manager.loggerDict[name]
                if isinstance(obj, logging.Logger) and obj.disabled:
                    obj.disabled = False

        await asyncio.to_thread(_run)

    if os.environ.get("SKIP_AUTO_MIGRATE") == "1":
        logger.info("SKIP_AUTO_MIGRATE=1，跳过自动迁移")
    else:
        try:
            logger.info("正在执行数据库迁移 (alembic upgrade head) ...")
            await _auto_migrate()
            logger.info("数据库迁移完成")
        except Exception:
            logger.exception("数据库迁移失败，应用无法启动")
            raise

    # ── 种子数据（幂等，每次启动执行）──
    from app.startup.seed import run_seed
    _seed_credentials = await run_seed(async_session_factory, is_ee=_fg.is_ee)

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

    # ── 恢复卡在 deploying 状态的实例 ─────────────────
    # 后端重启（如 --reload）会杀死 asyncio.create_task 部署管道，
    # 实例可能永远卡在 deploying。启动时从 K8s 同步真实状态。
    async with async_session_factory() as db:
        from app.models.instance import Instance, InstanceStatus

        stuck_result = await db.execute(
            select(Instance).where(
                Instance.status.in_(["deploying", "creating"]),
                Instance.deleted_at.is_(None),
            )
        )
        stuck_instances = stuck_result.scalars().all()
        for inst in stuck_instances:
            try:
                cluster_result = await db.execute(
                    select(Cluster).where(
                        Cluster.id == inst.cluster_id,
                        Cluster.deleted_at.is_(None),
                    )
                )
                cluster = cluster_result.scalar_one_or_none()
                if not cluster or not cluster.kubeconfig_encrypted:
                    continue

                from app.services.k8s.k8s_client import K8sClient
                api_client = await k8s_manager.get_or_create(cluster.id, cluster.kubeconfig_encrypted)
                k8s = K8sClient(api_client)

                k8s_name = inst.slug or inst.name
                dep_status = await k8s.get_deployment_status(inst.namespace, k8s_name)
                if dep_status["ready_replicas"] >= inst.replicas:
                    inst.status = InstanceStatus.running
                    inst.available_replicas = dep_status["available_replicas"]
                    logger.info("恢复实例状态: %s → running (ready=%d)", inst.name, dep_status["ready_replicas"])
                else:
                    logger.info(
                        "实例 %s 仍未就绪 (ready=%d/%d)，保持 deploying",
                        inst.name, dep_status["ready_replicas"], inst.replicas,
                    )
            except Exception as e:
                logger.warning("恢复实例 %s 状态失败: %s", inst.name, e)

        if stuck_instances:
            await db.commit()

    # 启动集群健康巡检后台任务
    from app.services.health_checker import HealthChecker

    health_checker = HealthChecker(async_session_factory)
    health_checker.start()

    from app.services.summary_job import SummaryJob
    summary_job = SummaryJob(async_session_factory)
    summary_job.start()

    from app.services.schedule_runner import ScheduleRunner
    schedule_runner = ScheduleRunner(async_session_factory)
    schedule_runner.start()

    # ── 启动飞书 WebSocket 长链接 ──
    from app.services.channel_adapters.feishu_ws_client import FeishuWSClient
    feishu_ws_clients: list[FeishuWSClient] = []

    async with async_session_factory() as db:
        from app.models.corridor import HumanHex

        hh_rows = await db.execute(
            select(HumanHex).where(
                HumanHex.channel_type == "feishu",
                HumanHex.deleted_at.is_(None),
            )
        )
        seen_apps: dict[str, FeishuWSClient] = {}
        for hh in hh_rows.scalars().all():
            cfg = hh.channel_config or {}
            if cfg.get("mode") != "websocket":
                continue
            app_id = cfg.get("app_id", "")
            app_secret = cfg.get("app_secret", "")
            if not app_id or not app_secret or app_id in seen_apps:
                continue
            client = FeishuWSClient(
                app_id=app_id,
                app_secret=app_secret,
                encrypt_key=cfg.get("encrypt_key", ""),
                verification_token=cfg.get("verification_token", ""),
            )
            client.start()
            seen_apps[app_id] = client
            feishu_ws_clients.append(client)

    if feishu_ws_clients:
        logger.info("已启动 %d 个飞书 WebSocket 长链接", len(feishu_ws_clients))

    # ── 修复卡死实例状态 ──
    async with async_session_factory() as db:
        from app.models.instance import Instance
        ws_agents = await db.execute(
            select(Instance).where(
                Instance.status.in_(["restarting", "learning"]),
                Instance.deleted_at.is_(None),
            )
        )
        instances = ws_agents.scalars().all()
        for inst in instances:
            inst.status = "running"
            logger.info("修复卡死状态: %s %s -> running", inst.name, inst.status)
        if instances:
            await db.commit()

    logger.info("Agent Tunnel 已就绪，等待实例主动连接")

    # ── Runtime Platform v2 Startup ──────────────────
    _pg_notify_service = None
    _heartbeat_task = None
    _raw_conn = None
    _asyncpg_conn = None
    _pg_notify_channels: list[str] = []
    _queue_consumer_task = None
    try:
        if os.environ.get("OTEL_ENABLED", "").lower() in ("1", "true"):
            from app.services.runtime.telemetry import init_telemetry
            init_telemetry()
            logger.info("Runtime v2: OpenTelemetry 已初始化")

        async with async_session_factory() as _v2_db:
            from app.services.runtime.registries.node_type_registry import NODE_TYPE_REGISTRY
            await NODE_TYPE_REGISTRY.sync_to_db(_v2_db)
            await _v2_db.commit()
            logger.info("Runtime v2: NodeTypeRegistry 已同步到数据库")

        from app.services.runtime.hooks.builtin import register_builtin_hooks
        register_builtin_hooks()
        logger.info("Runtime v2: 内置生命周期钩子已注册")

        from app.services.runtime.pg_notify import PGNotifyService
        _pg_notify_service = PGNotifyService()

        async def _on_topology_changed(channel: str, payload: str):
            from app.api.workspaces import broadcast_event
            from app.services.runtime.route_cache import route_table
            try:
                import json as _json
                data = _json.loads(payload) if payload else {}
                ws_id = data.get("workspace_id", "") if isinstance(data, dict) else str(data)
                if ws_id:
                    route_table.invalidate(ws_id)
                    broadcast_event(ws_id, "topology:changed", {"workspace_id": ws_id})
                else:
                    route_table.invalidate_all()
            except Exception as e:
                logger.warning("_on_topology_changed handler failed: %s (payload=%s)", e, payload[:100] if payload else "")
                route_table.invalidate_all()

        _pg_notify_service.subscribe("topology_changed", _on_topology_changed)

        from app.services.runtime.sse_registry import BACKEND_INSTANCE_ID
        _sse_push_channel = f"sse_push:{BACKEND_INSTANCE_ID}"

        async def _on_sse_push(channel: str, payload: str):
            from app.api.workspaces import _workspace_queues
            try:
                import json as _json
                msg = _json.loads(payload) if payload else {}
                ws_id = msg.get("workspace_id", "")
                event_type = msg.get("event_type", "")
                data = msg.get("data", {})
                if ws_id and event_type:
                    queues = _workspace_queues.get(ws_id, set())
                    for q in queues:
                        q.put_nowait({"event": event_type, "data": data})
            except Exception as e:
                logger.warning("_on_sse_push handler failed: %s", e)

        _pg_notify_service.subscribe(_sse_push_channel, _on_sse_push)

        from app.services.runtime.messaging.queue_consumer import on_queue_notify as _on_queue_notify
        _pg_notify_service.subscribe("message_enqueued", _on_queue_notify)

        _pg_notify_channels = ["topology_changed", _sse_push_channel, "message_enqueued"]
        try:
            _raw_conn = await engine.raw_connection()
            _asyncpg_conn = _raw_conn.connection._connection
            await _pg_notify_service.start_listening(_asyncpg_conn, _pg_notify_channels)
            logger.info(
                "Runtime v2: PG LISTEN/NOTIFY 已启动 (channels=%s, backend=%s)",
                _pg_notify_channels, BACKEND_INSTANCE_ID,
            )
        except Exception as e:
            logger.warning("Runtime v2: PG LISTEN/NOTIFY 启动失败（非致命）: %s", e)
            _raw_conn = None

        from app.services.runtime.failure_recovery import run_heartbeat_scanner
        _heartbeat_task = asyncio.create_task(run_heartbeat_scanner(async_session_factory))
        logger.info("Runtime v2: SSE 心跳扫描已启动")

        from app.services.runtime.messaging.queue_consumer import start_consumer
        _queue_consumer_task = start_consumer(async_session_factory)
        logger.info("Runtime v2: 队列消费者已启动")

        async with async_session_factory() as _mig_db:
            from app.services.runtime.migration import run_full_migration
            migrated = await run_full_migration(_mig_db)
            if any(v > 0 for v in migrated.values()):
                await _mig_db.commit()
                logger.info("Runtime v2: 数据迁移完成 %s", migrated)
    except Exception as e:
        logger.warning("Runtime v2 启动部分失败（非致命）: %s", e)

    _ce_creds = _seed_credentials.get("ce_admin")
    _ee_creds = _seed_credentials.get("ee_admin")
    if _ce_creds:
        _ce_label = "Portal 超管初始账号" if _fg.is_ee else "超管初始账号"
        print(
            "\n"
            "========================================\n"
            f"  {_ce_label}\n"
            f"  账号: {_ce_creds['account']}\n"
            f"  密码: {_ce_creds['password']}\n"
            "  请登录后立即修改密码\n"
            "========================================",
            flush=True,
        )
    if _ee_creds:
        print(
            "\n"
            "========================================\n"
            "  Admin 平台管理员初始账号\n"
            f"  账号: {_ee_creds['account']}\n"
            f"  密码: {_ee_creds['password']}\n"
            "  请登录后立即修改密码\n"
            "========================================",
            flush=True,
        )

    # ── Security Pipeline 初始化 ─────────────────────
    from app.services.security.pipeline import SecurityPipeline
    from app.services.security.loader import create_plugins
    from app.api.security_ws import set_pipeline

    _security_pipeline = SecurityPipeline()
    _security_plugins = await create_plugins([])
    for _sp in _security_plugins:
        _security_pipeline.add_plugin(_sp)
    set_pipeline(_security_pipeline)
    logger.info("Security Pipeline 已初始化 (%d plugins)", _security_pipeline.plugin_count)

    yield

    # ── Security Pipeline 销毁 ────────────────────────
    await _security_pipeline.destroy()
    set_pipeline(None)

    # ── Runtime Platform v2 Shutdown ─────────────────
    try:
        from app.services.runtime.messaging.queue_consumer import stop_consumer
        stop_consumer()

        if _heartbeat_task and not _heartbeat_task.done():
            _heartbeat_task.cancel()
        if _pg_notify_service and _raw_conn:
            try:
                await _pg_notify_service.stop_listening(_asyncpg_conn, _pg_notify_channels)
            except Exception:
                pass
        try:
            async with async_session_factory() as _shutdown_db:
                from app.services.runtime import sse_registry
                await sse_registry.cleanup_backend_connections(_shutdown_db)
                await _shutdown_db.commit()
        except Exception:
            pass
        from app.services.runtime.failure_recovery import shutdown_cleanup
        await shutdown_cleanup(async_session_factory)
        logger.info("Runtime v2: 已清理")
    except Exception as e:
        logger.warning("Runtime v2 关闭部分失败: %s", e)

    # ── Shutdown ─────────────────────────────────────
    for ws_client in feishu_ws_clients:
        ws_client.stop()
    logger.info("Agent Tunnel 连接将随进程退出自动关闭")
    await summary_job.stop()
    await schedule_runner.stop()
    await health_checker.stop()
    await k8s_manager.close_all()
    logger.info("已关闭所有 K8s 连接")
    from app.services import genehub_client
    await genehub_client.close()
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

# ── API Cache-Control ────────────────────────────────
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request as _StarletteRequest
from starlette.responses import Response as _StarletteResponse


class _NoCacheAPIMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: _StarletteRequest, call_next: RequestResponseEndpoint) -> _StarletteResponse:
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


app.add_middleware(_NoCacheAPIMiddleware)

# ── Exception handlers ───────────────────────────────
register_exception_handlers(app)

# ── Routers ──────────────────────────────────────────
app.include_router(api_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1/admin")
app.include_router(webhook_router)

# ── EE 模块自动加载 ─────────────────────────────────
from app.core.feature_gate import feature_gate  # noqa: E402

if feature_gate.is_ee:
    _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    try:
        from ee.backend.router import ee_api_router, ee_admin_router
        app.include_router(ee_api_router, prefix="/api/v1")
        app.include_router(ee_admin_router, prefix="/api/v1/admin")

        from ee.backend.hooks.topology_audit import register_hooks as _register_audit_hooks
        _register_audit_hooks()

        from ee.backend.hooks.operation_audit import register_hooks as _register_op_audit_hooks
        _register_op_audit_hooks()

        from ee.backend.middleware.audit_middleware import AuditMiddleware
        app.add_middleware(AuditMiddleware)

        try:
            from ee.backend.hooks.member_hook import EEMemberHookProvider
            from app.services.member_hooks import register_member_hook
            register_member_hook(EEMemberHookProvider())
        except ImportError:
            pass

        logging.getLogger(__name__).info("EE 模块已加载（含操作审计）")
    except ImportError:
        logging.getLogger(__name__).warning("检测到 ee/ 目录但 EE 模块加载失败，以 CE 模式运行")

if not feature_gate.is_ee:
    from app.services.audit_handler import register_ce_audit_handler
    register_ce_audit_handler()

if settings.DEBUG:
    from app.api.llm_proxy import router as llm_proxy_router
    app.include_router(llm_proxy_router, tags=["LLM 代理（开发模式）"])

# ── Static files (前端 build 产物) ───────────────────
# 生产环境：Vite build 后的 dist 目录会被复制到 static/
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
