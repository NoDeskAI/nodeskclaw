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
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.router import admin_router, api_router, webhook_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers

# ── 滚动日志配置 ─────────────────────────────────────
_LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

_app_version = settings.APP_VERSION
_log_formatter = logging.Formatter(
    f"%(asctime)s %(levelname)-5s [{_app_version}] [%(name)s] %(message)s",
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
            f"%(asctime)s %(colored_level)s [{_app_version}] [%(name)s] %(message)s",
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


class _PoolDisconnectFilter(logging.Filter):
    """CancelledError -> single-line WARNING; GC cleanup -> WARNING; real errors untouched."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not record.name.startswith("sqlalchemy.pool"):
            return True
        if record.exc_info and record.exc_info[1]:
            if isinstance(record.exc_info[1], asyncio.CancelledError):
                record.levelno = logging.WARNING
                record.levelname = "WARNING"
                record.msg = "Client disconnect interrupted connection cleanup (CancelledError)"
                record.args = None
                record.exc_info = None
                record.exc_text = None
                return True
        msg = record.getMessage()
        if "garbage collector" in msg and record.levelno >= logging.ERROR:
            record.levelno = logging.WARNING
            record.levelname = "WARNING"
            return True
        return True


_pool_filter = _PoolDisconnectFilter()
_console_handler.addFilter(_pool_filter)
_file_handler.addFilter(_pool_filter)

import warnings  # noqa: E402
from sqlalchemy.exc import SAWarning  # noqa: E402

warnings.filterwarnings(
    "ignore",
    message=r".*garbage collector.*non-checked-in connection.*",
    category=SAWarning,
)

for _uv_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    _uv_logger = logging.getLogger(_uv_name)
    _uv_logger.handlers.clear()
    _uv_logger.propagate = True


class _HealthCheckLogFilter(logging.Filter):
    """Suppress health-check access logs unless configured or response is an error."""

    def filter(self, record: logging.LogRecord) -> bool:
        if settings.LOG_HEALTH_CHECK:
            return True
        msg = record.getMessage()
        if "/api/v1/health" not in msg:
            return True
        try:
            status_code = record.args[-1]
            if isinstance(status_code, int) and status_code >= 400:
                return True
        except (IndexError, TypeError):
            return True
        return False


logging.getLogger("uvicorn.access").addFilter(_HealthCheckLogFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    import logging

    import json

    from sqlalchemy import func, select

    from app.core.deps import async_session_factory, engine
    from app.models.cluster import Cluster, ClusterStatus
    from app.services.k8s.client_manager import k8s_manager

    logger = logging.getLogger(__name__)
    logger.info("NoDeskClaw %s starting (Python %s)", settings.APP_VERSION, sys.version.split()[0])

    # ── EE Model 注册（在 Alembic 迁移之前导入，使其加入 Base.metadata）──
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

    # ── Egress 配置迁移：env vars → system_configs（幂等）──
    from app.models.system_config import SystemConfig
    from app.services import config_service

    egress_seeds = {
        "egress_deny_cidrs": os.environ.get("EGRESS_DENY_CIDRS", "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"),
        "egress_allow_ports": os.environ.get("EGRESS_ALLOW_PORTS", "80,443"),
        "network_policy_ingress_enabled": "true",
        "network_policy_egress_enabled": "true",
        "ingress_allow_cidrs": "",
    }
    async with async_session_factory() as db:
        for _eg_key, _eg_value in egress_seeds.items():
            _eg_row = (await db.execute(
                select(SystemConfig).where(SystemConfig.key == _eg_key, SystemConfig.deleted_at.is_(None))
            )).scalar_one_or_none()
            if _eg_row is None:
                await config_service.set_config(_eg_key, _eg_value, db)
                logger.info("网络策略配置种子: %s = %s", _eg_key, _eg_value)

    # ── 种子数据（幂等，每次启动执行）──
    from app.startup.seed import run_seed, backfill_cluster_org_id, seed_engine_versions
    _seed_credentials = await run_seed(async_session_factory, is_ee=_fg.is_ee)
    await backfill_cluster_org_id(async_session_factory)
    await seed_engine_versions(async_session_factory)

    # ── gene_slugs → template_items 迁移（幂等）──
    async with async_session_factory() as db:
        from app.models.instance_template import InstanceTemplate, TemplateItem

        _tpl_result = await db.execute(
            select(InstanceTemplate).where(
                InstanceTemplate.gene_slugs.isnot(None),
                InstanceTemplate.gene_slugs != "",
                InstanceTemplate.gene_slugs != "[]",
                InstanceTemplate.deleted_at.is_(None),
            )
        )
        _templates_to_migrate = _tpl_result.scalars().all()
        _migrated = 0
        for _tpl in _templates_to_migrate:
            _existing = await db.execute(
                select(func.count()).where(
                    TemplateItem.template_id == _tpl.id,
                    TemplateItem.deleted_at.is_(None),
                )
            )
            if (_existing.scalar() or 0) > 0:
                continue
            try:
                _slugs = json.loads(_tpl.gene_slugs)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(_slugs, list):
                continue
            for _idx, _slug in enumerate(_slugs):
                if isinstance(_slug, str) and _slug:
                    db.add(TemplateItem(
                        template_id=_tpl.id,
                        item_type="gene",
                        item_slug=_slug,
                        sort_order=_idx,
                    ))
            _migrated += 1
        if _migrated:
            await db.commit()
            logger.info("gene_slugs → template_items 迁移完成: %d 个模板", _migrated)

    # ── source_registry 回填（幂等）──
    try:
        async with async_session_factory() as _sr_db:
            from app.models.gene import Gene as _GeneModel
            from sqlalchemy import update as _sa_update

            _sr_count_ext = await _sr_db.execute(
                _sa_update(_GeneModel)
                .where(
                    _GeneModel.source_registry.is_(None),
                    _GeneModel.deleted_at.is_(None),
                    _GeneModel.source.notin_(["manual", "agent"]),
                )
                .values(source_registry="genehub")
            )
            _sr_count_local = await _sr_db.execute(
                _sa_update(_GeneModel)
                .where(
                    _GeneModel.source_registry.is_(None),
                    _GeneModel.deleted_at.is_(None),
                    _GeneModel.source.in_(["manual", "agent"]),
                )
                .values(source_registry="local")
            )
            _sr_total = (_sr_count_ext.rowcount or 0) + (_sr_count_local.rowcount or 0)
            if _sr_total > 0:
                await _sr_db.commit()
                logger.info("source_registry 回填完成: %d 条记录", _sr_total)
    except Exception as _sr_err:
        logger.warning("source_registry 回填跳过（列可能尚未创建）: %s", _sr_err)

    # ── 种子基因导入（幂等，配置驱动）──
    if settings.SEED_GENES:
        try:
            async with async_session_factory() as _seed_db:
                import pathlib
                import json as _seed_json
                from app.models.gene import Gene as _SeedGene, Genome as _SeedGenome
                from app.models.base import not_deleted as _seed_not_deleted

                _seed_dir = pathlib.Path(__file__).parent / "data" / "gene_templates"

                _gene_files = [
                    "mcp_blackboard_tools.json",
                    "mcp_proposals.json",
                    "mcp_gene_discovery.json",
                    "mcp_performance_reader.json",
                    "mcp_topology_awareness.json",
                    "mcp_shared_files.json",
                    "meta_gene_ai_hc.json",
                    "meta_gene_reorg.json",
                    "meta_gene_culture.json",
                    "meta_gene_self_improve.json",
                    "meta_gene_innovation.json",
                    "meta_gene_akr_decomposer.json",
                ]
                _genome_files = [
                    "genome_self_management.json",
                    "genome_ai_employee_basics.json",
                    "workflow_genome_example.json",
                ]

                _seeded_genes = 0
                _updated_genes = 0
                for _fname in _gene_files:
                    _tpl_path = _seed_dir / _fname
                    if not _tpl_path.exists():
                        continue
                    _tpl = _seed_json.loads(_tpl_path.read_text())
                    _slug = _tpl["slug"]

                    _manifest = _tpl.get("manifest", {})
                    if "scripts" in _manifest and isinstance(_manifest["scripts"], list):
                        _scripts_dict = {}
                        _scripts_dir = _seed_dir.parent / "gene_scripts"
                        for _sname in _manifest["scripts"]:
                            _spath = _scripts_dir / _sname
                            if _spath.exists():
                                _scripts_dict[_sname] = _spath.read_text()
                            else:
                                logger.warning("Seed missing script: %s for %s", _sname, _slug)
                        _manifest["scripts"] = _scripts_dict

                    _existing = (await _seed_db.execute(
                        select(_SeedGene).where(_SeedGene.slug == _slug, _seed_not_deleted(_SeedGene))
                    )).scalar_one_or_none()
                    if _existing is None:
                        _seed_db.add(_SeedGene(
                            name=_tpl["name"],
                            slug=_slug,
                            description=_tpl.get("description"),
                            category=_tpl.get("category"),
                            tags=_seed_json.dumps(_tpl.get("tags", []), ensure_ascii=False),
                            source="official",
                            version="1.0.0",
                            manifest=_seed_json.dumps(_manifest, ensure_ascii=False),
                            is_published=True,
                            review_status="approved",
                            source_registry="local",
                        ))
                        _seeded_genes += 1
                    else:
                        _new_manifest = _seed_json.dumps(_manifest, ensure_ascii=False)
                        if _existing.manifest != _new_manifest:
                            _existing.manifest = _new_manifest
                            _updated_genes += 1

                _seeded_genomes = 0
                _updated_genomes = 0
                for _fname in _genome_files:
                    _tpl_path = _seed_dir / _fname
                    if not _tpl_path.exists():
                        continue
                    _tpl = _seed_json.loads(_tpl_path.read_text())
                    _slug = _tpl["slug"]
                    _existing = (await _seed_db.execute(
                        select(_SeedGenome).where(_SeedGenome.slug == _slug, _seed_not_deleted(_SeedGenome))
                    )).scalar_one_or_none()
                    if _existing is None:
                        _seed_db.add(_SeedGenome(
                            name=_tpl["name"],
                            slug=_slug,
                            description=_tpl.get("description"),
                            gene_slugs=_seed_json.dumps(_tpl.get("gene_slugs", []), ensure_ascii=False),
                            config_override=_seed_json.dumps(_tpl.get("config_override", {}), ensure_ascii=False),
                            is_published=True,
                        ))
                        _seeded_genomes += 1
                    else:
                        _new_slugs = _seed_json.dumps(_tpl.get("gene_slugs", []), ensure_ascii=False)
                        _new_override = _seed_json.dumps(_tpl.get("config_override", {}), ensure_ascii=False)
                        _new_desc = _tpl.get("description")
                        if (_existing.gene_slugs != _new_slugs
                                or _existing.config_override != _new_override
                                or _existing.description != _new_desc):
                            _existing.gene_slugs = _new_slugs
                            _existing.config_override = _new_override
                            _existing.description = _new_desc
                            _updated_genomes += 1

                if _seeded_genes or _seeded_genomes or _updated_genes or _updated_genomes:
                    await _seed_db.commit()
                    logger.info(
                        "种子基因导入完成: %d 新增 + %d 更新 gene, %d 新增 + %d 更新 genome",
                        _seeded_genes, _updated_genes, _seeded_genomes, _updated_genomes,
                    )
                else:
                    logger.info("种子基因检查完成，无需导入或更新（均已是最新）")
        except Exception as _seed_err:
            logger.warning("种子基因导入失败: %s", _seed_err)

    # ── 默认工作基因 seed（在 Gene 种子导入之后执行）──
    from app.startup.seed import seed_default_required_genes
    await seed_default_required_genes(async_session_factory)

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
            if not cluster.is_k8s:
                continue
            try:
                from app.services.runtime.registries.compute_registry import require_k8s_client
                await require_k8s_client(cluster)
                logger.info("预热集群连接: %s (%s)", cluster.name, cluster.id)
            except Exception as e:
                logger.warning("预热集群 %s 失败: %s", cluster.name, e)

    # ── 补建缺失的 proxy Ingress（按 proxy_endpoint 配置，不限 CE/EE）──
    from app.startup.proxy_reconcile import reconcile_proxy_ingresses
    await reconcile_proxy_ingresses(async_session_factory)

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
                if not cluster or not cluster.is_k8s or not cluster.credentials_encrypted:
                    continue

                from app.services.k8s.k8s_client import K8sClient
                api_client = await k8s_manager.get_or_create(cluster.id, cluster.credentials_encrypted)
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

    from app.services.instance_health_checker import InstanceHealthChecker

    instance_health_checker = InstanceHealthChecker(async_session_factory)
    instance_health_checker.start()

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
                        try:
                            q.put_nowait({"event": event_type, "data": data})
                        except asyncio.QueueFull:
                            logger.warning("SSE queue full (cross-instance) for workspace %s, dropping %s", ws_id, event_type)
            except Exception as e:
                logger.warning("_on_sse_push handler failed: %s", e)

        _pg_notify_service.subscribe(_sse_push_channel, _on_sse_push)

        from app.services.runtime.messaging.queue_consumer import on_queue_notify as _on_queue_notify
        _pg_notify_service.subscribe("message_enqueued", _on_queue_notify)

        _pg_notify_channels = ["topology_changed", _sse_push_channel, "message_enqueued"]
        try:
            await _pg_notify_service.start_with_reconnect(engine, _pg_notify_channels)
            logger.info(
                "Runtime v2: PG LISTEN/NOTIFY 已启动 (channels=%s, backend=%s)",
                _pg_notify_channels, BACKEND_INSTANCE_ID,
            )
        except Exception as e:
            logger.warning("Runtime v2: PG LISTEN/NOTIFY 启动失败（非致命）: %s", e)


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

    # ── Registry Aggregator 初始化 ────────────────────
    from app.services.registry_adapter import RegistryAdapter
    from app.services import registry_aggregator
    from app.services.local_adapter import LocalAdapter

    _reg_adapters: list[RegistryAdapter] = [
        LocalAdapter(session_factory=async_session_factory),
    ]

    _skill_registries_raw = settings.SKILL_REGISTRIES.strip()
    _external_registry_configs: list[dict] = []
    if _skill_registries_raw:
        try:
            _external_registry_configs = json.loads(_skill_registries_raw)
            if not isinstance(_external_registry_configs, list):
                logger.warning("SKILL_REGISTRIES 不是 JSON 数组，已忽略")
                _external_registry_configs = []
        except json.JSONDecodeError as _jde:
            logger.warning("SKILL_REGISTRIES JSON 解析失败: %s", _jde)

    if not _external_registry_configs and settings.GENEHUB_REGISTRY_URL:
        _external_registry_configs.append({
            "type": "genehub", "id": "genehub",
            "url": settings.GENEHUB_REGISTRY_URL,
            "api_key": settings.GENEHUB_API_KEY,
            "name": "GeneHub",
        })

    for _rc in _external_registry_configs:
        _rtype = _rc.get("type", "")
        _rid = _rc.get("id", _rtype)
        _rurl = _rc.get("url", "")
        _rname = _rc.get("name", _rid)
        _rkey = _rc.get("api_key", "")

        if _rtype == "genehub" and _rurl:
            from app.services.genehub_client import GeneHubAdapter
            _reg_adapters.append(
                GeneHubAdapter(registry_id=_rid, registry_name=_rname, base_url=_rurl, api_key=_rkey)
            )
            logger.info("已注册 GeneHubAdapter: %s (%s)", _rid, _rurl)
        elif _rtype == "clawhub" and _rurl:
            from app.services.clawhub_adapter import ClawHubAdapter
            _reg_adapters.append(
                ClawHubAdapter(registry_id=_rid, registry_name=_rname, base_url=_rurl, api_key=_rkey)
            )
            logger.info("已注册 ClawHubAdapter (stub): %s (%s)", _rid, _rurl)
        else:
            logger.warning("未知 registry type=%s, id=%s, 已跳过", _rtype, _rid)

    registry_aggregator.init(_reg_adapters)
    logger.info("RegistryAggregator 已初始化 (adapters=%s)", [a.registry_id for a in _reg_adapters])

    async def _run_startup_plugin_sync():
        try:
            from app.services.llm_config_service import startup_plugin_sync
            async with async_session_factory() as db:
                await startup_plugin_sync(db)
        except Exception as e:
            logger.warning("startup_plugin_sync 失败（非致命）: %s", e)

    asyncio.create_task(_run_startup_plugin_sync())

    # ── 匿名安装遥测（CE-only，一次性上报到 PostHog）──
    async def _run_telemetry():
        try:
            async with async_session_factory() as db:
                from app.services import telemetry_service
                await telemetry_service.report_installation_once(db)
        except Exception as e:
            logger.warning("遥测上报失败（非致命）: %s", e)

    if _fg.is_ee:
        logger.info("遥测已跳过 (EE 模式)")
    elif not settings.TELEMETRY_ENABLED:
        logger.info("遥测已关闭 (TELEMETRY_ENABLED=false)")
    elif not settings.POSTHOG_API_KEY:
        logger.info("遥测已跳过 (POSTHOG_API_KEY 未配置)")
    else:
        logger.info("遥测启用，将在后台上报匿名安装信息")
        _telemetry_task = asyncio.create_task(_run_telemetry())

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
        if _pg_notify_service:
            try:
                await _pg_notify_service.shutdown()
            except Exception:
                logger.warning("Failed to stop PG NOTIFY listeners", exc_info=True)
        try:
            async with async_session_factory() as _shutdown_db:
                from app.services.runtime import sse_registry
                await sse_registry.cleanup_backend_connections(_shutdown_db)
                await _shutdown_db.commit()
        except Exception:
            logger.warning("Failed to cleanup SSE backend connections", exc_info=True)
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
    await instance_health_checker.stop()
    await health_checker.stop()
    await k8s_manager.close_all()
    logger.info("已关闭所有 K8s 连接")
    await registry_aggregator.close()
    logger.info("RegistryAggregator 已关闭")
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

class _NoCacheAPIMiddleware:
    """Pure ASGI middleware — no BaseHTTPMiddleware task-group wrapping."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            await self.app(scope, receive, send)
            return

        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                ct = headers.get("content-type", "")
                if "text/event-stream" in ct:
                    headers["X-Accel-Buffering"] = "no"
                    headers["Cache-Control"] = "no-cache"
                elif "cache-control" not in headers:
                    headers.append("Cache-Control", "no-store")
            await send(message)

        await self.app(scope, receive, _send)


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
    except Exception:
        logging.getLogger(__name__).exception("EE 模块加载失败，无法以 CE 模式降级运行")
        raise

if not feature_gate.is_ee:
    from app.services.audit_handler import register_ce_audit_handler
    register_ce_audit_handler()

# ── Static files (前端 build 产物) ───────────────────
# 生产环境：Vite build 后的 dist 目录会被复制到 static/
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
