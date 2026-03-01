"""FastAPI application entry point."""

import logging
import os
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

# 文件日志：10MB 单文件，保留 5 个历史文件（共 ~60MB）
_file_handler = RotatingFileHandler(
    os.path.join(_LOG_DIR, "nodeskclaw.log"),
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
    from app.utils.oauth_providers.feishu import FeishuProvider
    from app.utils.oauth_providers.registry import register_provider

    logger = logging.getLogger(__name__)

    # ── Startup ──────────────────────────────────────
    register_provider(FeishuProvider())

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

        # 迁移 3: 将 instances.storage_size 默认值改为 80Gi（条件执行，避免滚动更新锁竞争）
        _def_check = await conn.execute(text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'instances' AND column_name = 'storage_size'"
        ))
        _def_row = _def_check.first()
        if _def_row and "'80Gi'" not in str(_def_row[0] or ""):
            await conn.execute(text(
                "ALTER TABLE instances ALTER COLUMN storage_size SET DEFAULT '80Gi'"
            ))
            logger.info("自动迁移：已将 instances.storage_size 默认值改为 80Gi")

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

        # ── 迁移 6: 邮箱/手机/密码登录字段 ──────────────

        # 6a: feishu_uid 改为可空
        col = await conn.execute(text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'feishu_uid'"
        ))
        row = col.first()
        if row and row[0] == 'NO':
            await conn.execute(text("ALTER TABLE users ALTER COLUMN feishu_uid DROP NOT NULL"))
            logger.info("自动迁移：feishu_uid 改为可空")

        # 6b: phone 列
        col = await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'phone'"
        ))
        if col.first() is None:
            await conn.execute(text(
                "ALTER TABLE users ADD COLUMN phone VARCHAR(32) UNIQUE"
            ))
            logger.info("自动迁移：已为 users 表添加 phone 列")

        # 6c: password_hash 列
        col = await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'password_hash'"
        ))
        if col.first() is None:
            await conn.execute(text(
                "ALTER TABLE users ADD COLUMN password_hash VARCHAR(256)"
            ))
            logger.info("自动迁移：已为 users 表添加 password_hash 列")

        # ── 迁移 7: organizations 表新增 max_storage_total ──
        col = await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'organizations' AND column_name = 'max_storage_total'"
        ))
        if col.first() is None:
            await conn.execute(text(
                "ALTER TABLE organizations ADD COLUMN max_storage_total VARCHAR(16) NOT NULL DEFAULT '500Gi'"
            ))
            logger.info("自动迁移：已为 organizations 表添加 max_storage_total 列")

        # ── 迁移 8: instances 表新增 workspace_id / hex_position / agent_display_name ──
        col = await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'instances' AND column_name = 'workspace_id'"
        ))
        if col.first() is None:
            await conn.execute(text(
                "ALTER TABLE instances ADD COLUMN workspace_id VARCHAR(36) "
                "REFERENCES workspaces(id) ON DELETE SET NULL"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_instances_workspace_id ON instances(workspace_id)"
            ))
            await conn.execute(text(
                "ALTER TABLE instances ADD COLUMN hex_position_q INTEGER NOT NULL DEFAULT 0"
            ))
            await conn.execute(text(
                "ALTER TABLE instances ADD COLUMN hex_position_r INTEGER NOT NULL DEFAULT 0"
            ))
            await conn.execute(text(
                "ALTER TABLE instances ADD COLUMN agent_display_name VARCHAR(64)"
            ))
            logger.info("自动迁移：已为 instances 表添加 workspace 相关字段")

        # ── 迁移 10: instances 表新增 slug 列 + 回填 + 唯一索引替换 ──
        slug_col = await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'instances' AND column_name = 'slug'"
        ))
        if slug_col.first() is None:
            await conn.execute(text(
                "ALTER TABLE instances ADD COLUMN slug VARCHAR(128) NOT NULL DEFAULT ''"
            ))
            await conn.execute(text(
                "UPDATE instances SET slug = LOWER(REGEXP_REPLACE("
                "  REGEXP_REPLACE(name, '[^a-zA-Z0-9-]', '-', 'g'), "
                "  '-{2,}', '-', 'g'"
                "))"
            ))
            await conn.execute(text(
                "UPDATE instances SET slug = TRIM(BOTH '-' FROM slug)"
            ))
            await conn.execute(text(
                "UPDATE instances SET slug = 'instance' WHERE slug = '' OR slug IS NULL"
            ))
            logger.info("自动迁移：已为 instances 表添加 slug 列并回填数据")

        old_name_idx = await conn.execute(text(
            "SELECT 1 FROM pg_indexes WHERE tablename = 'instances' AND indexname = 'uq_instances_name_active'"
        ))
        if old_name_idx.first() is not None:
            await conn.execute(text("DROP INDEX uq_instances_name_active"))
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_instances_slug_org_active "
                "ON instances (slug, org_id) WHERE deleted_at IS NULL"
            ))
            logger.info("自动迁移：已将 instances 唯一索引从 name 替换为 (slug, org_id)")

        # 6d: email 加 unique（如果还没有）
        idx = await conn.execute(text(
            "SELECT 1 FROM pg_indexes WHERE tablename = 'users' AND indexname = 'uq_users_email'"
        ))
        if idx.first() is None:
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email ON users(email) WHERE email IS NOT NULL AND deleted_at IS NULL"
            ))
            logger.info("自动迁移：已为 users.email 添加 partial unique index")

        # ── 迁移 11: LLM Key 管理相关表 + instances.proxy_token ──
        col = await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'instances' AND column_name = 'proxy_token'"
        ))
        if col.first() is None:
            await conn.execute(text(
                "ALTER TABLE instances ADD COLUMN proxy_token VARCHAR(64)"
            ))
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_instances_proxy_token "
                "ON instances (proxy_token) WHERE proxy_token IS NOT NULL"
            ))
            logger.info("自动迁移：已为 instances 表添加 proxy_token 列和唯一索引")

        for tbl in ("org_llm_keys", "user_llm_keys", "user_llm_configs", "llm_usage_logs"):
            exists = await conn.execute(text(
                "SELECT 1 FROM information_schema.tables WHERE table_name = :t"
            ), {"t": tbl})
            if exists.first() is None:
                needs_create = True
                break
        else:
            needs_create = False

        if needs_create:
            from app.models.llm_usage_log import LlmUsageLog
            from app.models.org_llm_key import OrgLlmKey
            from app.models.user_llm_config import UserLlmConfig
            from app.models.user_llm_key import UserLlmKey
            for model in (OrgLlmKey, UserLlmKey, UserLlmConfig, LlmUsageLog):
                await conn.run_sync(model.__table__.create, checkfirst=True)
            logger.info("自动迁移：已创建 LLM 相关表 (org_llm_keys, user_llm_keys, user_llm_configs, llm_usage_logs)")

        # 回填 proxy_token: 从 env_vars JSON 提取 OPENCLAW_GATEWAY_TOKEN
        rows = await conn.execute(text(
            "SELECT id, env_vars FROM instances WHERE proxy_token IS NULL AND env_vars IS NOT NULL AND deleted_at IS NULL"
        ))
        import json as _json
        for row in rows:
            try:
                env = _json.loads(row.env_vars) if isinstance(row.env_vars, str) else row.env_vars
                token = env.get("OPENCLAW_GATEWAY_TOKEN")
                if token:
                    await conn.execute(text(
                        "UPDATE instances SET proxy_token = :token WHERE id = :id"
                    ), {"token": token, "id": row.id})
            except Exception:
                pass
        logger.info("自动迁移：已回填 instances.proxy_token")

        # ── 迁移 12: user_llm_configs 新增 selected_models 列 ──
        col = await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'user_llm_configs' AND column_name = 'selected_models'"
        ))
        if col.first() is None:
            tbl_exists = await conn.execute(text(
                "SELECT 1 FROM information_schema.tables WHERE table_name = 'user_llm_configs'"
            ))
            if tbl_exists.first() is not None:
                await conn.execute(text(
                    "ALTER TABLE user_llm_configs ADD COLUMN selected_models JSONB"
                ))
                logger.info("自动迁移：已为 user_llm_configs 表添加 selected_models 列")

        # ── 迁移 13: instances 新增 wp_api_key 列 + 回填 ──
        col = await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'instances' AND column_name = 'wp_api_key'"
        ))
        if col.first() is None:
            await conn.execute(text(
                "ALTER TABLE instances ADD COLUMN wp_api_key VARCHAR(96)"
            ))
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_instances_wp_api_key "
                "ON instances (wp_api_key) WHERE wp_api_key IS NOT NULL"
            ))
            import secrets as _secrets_mod
            rows = await conn.execute(text(
                "SELECT id FROM instances WHERE wp_api_key IS NULL AND deleted_at IS NULL"
            ))
            for row in rows:
                await conn.execute(
                    text("UPDATE instances SET wp_api_key = :key WHERE id = :id"),
                    {"key": f"nodeskclaw-wp-{_secrets_mod.token_hex(32)}", "id": row.id},
                )
            logger.info("自动迁移：已为 instances 表添加 wp_api_key 列并回填")

        # ── 迁移 14: workspace_members 新增 hex / channel / display 列 ──
        col = await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'workspace_members' AND column_name = 'hex_q'"
        ))
        if col.first() is None:
            await conn.execute(text(
                "ALTER TABLE workspace_members "
                "ADD COLUMN hex_q INTEGER, "
                "ADD COLUMN hex_r INTEGER, "
                "ADD COLUMN channel_type VARCHAR(20), "
                "ADD COLUMN channel_config JSON, "
                "ADD COLUMN display_color VARCHAR(20) DEFAULT '#f59e0b'"
            ))
            logger.info("自动迁移：已为 workspace_members 表添加 hex_q/hex_r/channel_type/channel_config/display_color 列")

        # ── 迁移 15: workspace_templates 表 schema 统一 ──
        tbl = await conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'workspace_templates'"
        ))
        if tbl.first() is not None:
            is_preset_col = await conn.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'workspace_templates' AND column_name = 'is_preset'"
            ))
            if is_preset_col.first() is None:
                await conn.execute(text(
                    "ALTER TABLE workspace_templates ADD COLUMN is_preset BOOLEAN NOT NULL DEFAULT false"
                ))
                logger.info("自动迁移：已为 workspace_templates 表添加 is_preset 列")
            bb_snap_col = await conn.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'workspace_templates' AND column_name = 'blackboard_snapshot'"
            ))
            if bb_snap_col.first() is None:
                await conn.execute(text(
                    "ALTER TABLE workspace_templates ADD COLUMN blackboard_snapshot JSONB DEFAULT '{}'"
                ))
                bb_tmpl_col = await conn.execute(text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = 'workspace_templates' AND column_name = 'blackboard_template'"
                ))
                if bb_tmpl_col.first() is not None:
                    await conn.execute(text(
                        "UPDATE workspace_templates SET blackboard_snapshot = COALESCE(blackboard_template, '{}')"
                    ))
                logger.info("自动迁移：已为 workspace_templates 表添加 blackboard_snapshot 列")
            is_public_col = await conn.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'workspace_templates' AND column_name = 'is_public'"
            ))
            if is_public_col.first() is None:
                await conn.execute(text(
                    "ALTER TABLE workspace_templates ADD COLUMN is_public BOOLEAN NOT NULL DEFAULT false"
                ))
                logger.info("自动迁移：已为 workspace_templates 表添加 is_public 列")

        # ── 迁移 16: human_hexes 表（人类工位独立存储，支持多次放置） ──
        hh_tbl = await conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'human_hexes'"
        ))
        if hh_tbl.first() is None:
            await conn.execute(text(
                "CREATE TABLE human_hexes ("
                "  id VARCHAR(36) PRIMARY KEY,"
                "  workspace_id VARCHAR(36) NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,"
                "  user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
                "  hex_q INTEGER NOT NULL,"
                "  hex_r INTEGER NOT NULL,"
                "  display_color VARCHAR(20) NOT NULL DEFAULT '#f59e0b',"
                "  created_by VARCHAR(36),"
                "  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
                "  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
                "  deleted_at TIMESTAMPTZ,"
                "  CONSTRAINT uq_human_hex_pos UNIQUE (workspace_id, hex_q, hex_r)"
                ")"
            ))
            await conn.execute(text("CREATE INDEX ix_human_hexes_workspace_id ON human_hexes (workspace_id)"))
            await conn.execute(text("CREATE INDEX ix_human_hexes_user_id ON human_hexes (user_id)"))
            migrated = await conn.execute(text(
                "INSERT INTO human_hexes (id, workspace_id, user_id, hex_q, hex_r, display_color, created_at, updated_at)"
                " SELECT gen_random_uuid()::text, workspace_id, user_id, hex_q, hex_r,"
                "   COALESCE(display_color, '#f59e0b'), created_at, updated_at"
                " FROM workspace_members WHERE hex_q IS NOT NULL AND deleted_at IS NULL"
            ))
            logger.info("自动迁移：已创建 human_hexes 表并迁移 %d 条数据", migrated.rowcount)

        # ── 迁移 17: human_hexes 新增 channel_type / channel_config 列 ──
        hh_ch_col = await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'human_hexes' AND column_name = 'channel_type'"
        ))
        if hh_ch_col.first() is None:
            await conn.execute(text(
                "ALTER TABLE human_hexes "
                "ADD COLUMN channel_type VARCHAR(20), "
                "ADD COLUMN channel_config JSON"
            ))
            migrated_ch = await conn.execute(text(
                "UPDATE human_hexes hh SET channel_type = wm.channel_type, channel_config = wm.channel_config"
                " FROM workspace_members wm"
                " WHERE hh.user_id = wm.user_id AND hh.workspace_id = wm.workspace_id"
                " AND wm.channel_type IS NOT NULL AND wm.deleted_at IS NULL AND hh.deleted_at IS NULL"
            ))
            logger.info("自动迁移：human_hexes 新增 channel 列并迁移 %d 条数据", migrated_ch.rowcount)

        # ── 迁移 18: blackboards 新增 content 列（Markdown 化重构） ──
        bb_content_col = await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'blackboards' AND column_name = 'content'"
        ))
        if bb_content_col.first() is None:
            await conn.execute(text(
                "ALTER TABLE blackboards ADD COLUMN content TEXT NOT NULL DEFAULT ''"
            ))
            logger.info("自动迁移：已为 blackboards 表添加 content 列")

        # ── 迁移 18b: 将旧黑板字段数据搬迁到 content（幂等，动态检测现存列） ──
        import json as _json

        _old_col_names = ("objectives", "tasks", "manual_notes", "auto_summary")
        _existing_old = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'blackboards' AND column_name = ANY(:cols)"
        ), {"cols": list(_old_col_names)})
        _found_cols = {r[0] for r in _existing_old.fetchall()}

        if _found_cols:
            _select_cols = ", ".join(
                f"{c}" if c in _found_cols else f"NULL AS {c}"
                for c in _old_col_names
            )
            rows = await conn.execute(text(
                f"SELECT id, {_select_cols} FROM blackboards WHERE content = ''"
            ))
            migrated_count = 0
            for row in rows.fetchall():
                bb_id, obj_raw, tasks_raw, notes, summary = row
                sections: list[str] = []
                if obj_raw:
                    obj = _json.loads(obj_raw) if isinstance(obj_raw, str) else obj_raw
                    if isinstance(obj, list) and obj:
                        lines = ["## 目标", ""]
                        for o in obj:
                            if isinstance(o, dict):
                                lines.append(f"- {o.get('title', '')}")
                                for kr in (o.get("key_results") or []):
                                    if isinstance(kr, dict):
                                        lines.append(f"  - {kr.get('desc', '')}")
                            elif isinstance(o, str):
                                lines.append(f"- {o}")
                        sections.append("\n".join(lines))
                if tasks_raw:
                    tsk = _json.loads(tasks_raw) if isinstance(tasks_raw, str) else tasks_raw
                    if isinstance(tsk, list) and tsk:
                        lines = ["## 任务", ""]
                        for t in tsk:
                            if not isinstance(t, dict):
                                continue
                            check = "x" if t.get("status") == "done" else " "
                            lines.append(f"- [{check}] {t.get('title', '')} ({t.get('status', 'todo')})")
                        sections.append("\n".join(lines))
                if notes and str(notes).strip():
                    sections.append(f"## 笔记\n\n{notes.strip()}")
                if summary and str(summary).strip():
                    sections.append(f"## 自动摘要\n\n{summary.strip()}")
                md = "\n\n".join(sections)
                if md:
                    await conn.execute(
                        text("UPDATE blackboards SET content = :c WHERE id = :id"),
                        {"c": md, "id": bb_id},
                    )
                    migrated_count += 1
            if migrated_count:
                logger.info("自动迁移：已将 %d 个黑板的旧数据转换为 Markdown content", migrated_count)

        # ── 迁移 19: clusters 表新增 ingress_class 列 ──
        col = await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'clusters' AND column_name = 'ingress_class'"
        ))
        if col.first() is None:
            await conn.execute(text(
                "ALTER TABLE clusters ADD COLUMN ingress_class VARCHAR(32) NOT NULL DEFAULT 'nginx'"
            ))
            logger.info("自动迁移：已为 clusters 表添加 ingress_class 列")

        # ── 迁移 20: clusters 表新增 proxy_endpoint 列（多集群网关代理） ──
        col = await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'clusters' AND column_name = 'proxy_endpoint'"
        ))
        if col.first() is None:
            await conn.execute(text(
                "ALTER TABLE clusters ADD COLUMN proxy_endpoint VARCHAR(512)"
            ))
            logger.info("自动迁移：已为 clusters 表添加 proxy_endpoint 列")

        # ── 迁移 21: 飞书租户绑定字段 ──
        # 迁移 22 会将 feishu_tenant_key 搬迁到 user_oauth_connections / org_oauth_bindings 后删除，
        # 所以如果 22 已执行（user_oauth_connections 表存在），21a/21b 的列不需要再添加。
        _oauth_tbl = await conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'user_oauth_connections'"
        ))
        _skip_21_feishu = _oauth_tbl.first() is not None

        if not _skip_21_feishu:
            # 21a: organizations.feishu_tenant_key
            col = await conn.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'organizations' AND column_name = 'feishu_tenant_key'"
            ))
            if col.first() is None:
                await conn.execute(text(
                    "ALTER TABLE organizations ADD COLUMN feishu_tenant_key VARCHAR(128)"
                ))
                await conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_organizations_feishu_tenant_key "
                    "ON organizations (feishu_tenant_key) WHERE feishu_tenant_key IS NOT NULL"
                ))
                logger.info("自动迁移：已为 organizations 表添加 feishu_tenant_key 列")

            # 21b: users.feishu_tenant_key
            col = await conn.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'users' AND column_name = 'feishu_tenant_key'"
            ))
            if col.first() is None:
                await conn.execute(text(
                    "ALTER TABLE users ADD COLUMN feishu_tenant_key VARCHAR(128)"
                ))
                logger.info("自动迁移：已为 users 表添加 feishu_tenant_key 列")

        # 21c: org_memberships.job_title（独立字段，不受迁移 22 影响）
        col = await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'org_memberships' AND column_name = 'job_title'"
        ))
        if col.first() is None:
            await conn.execute(text(
                "ALTER TABLE org_memberships ADD COLUMN job_title VARCHAR(32)"
            ))
            logger.info("自动迁移：已为 org_memberships 表添加 job_title 列")

        # ── 迁移 22: OAuth 通用架构（新表 + 数据搬迁 + 删旧列） ──
        # 22a: 创建 user_oauth_connections 表（create_all 已处理，但幂等检查）
        tbl = await conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'user_oauth_connections'"
        ))
        if tbl.first() is None:
            await conn.execute(text("""
                CREATE TABLE user_oauth_connections (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
                    provider VARCHAR(32) NOT NULL,
                    provider_user_id VARCHAR(128) NOT NULL,
                    provider_tenant_id VARCHAR(128),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    deleted_at TIMESTAMPTZ,
                    CONSTRAINT uq_oauth_provider_user UNIQUE (provider, provider_user_id)
                )
            """))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_user_oauth_connections_provider "
                "ON user_oauth_connections (provider)"
            ))
            logger.info("自动迁移：已创建 user_oauth_connections 表")

        # 22b: 创建 org_oauth_bindings 表
        tbl = await conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'org_oauth_bindings'"
        ))
        if tbl.first() is None:
            await conn.execute(text("""
                CREATE TABLE org_oauth_bindings (
                    id VARCHAR(36) PRIMARY KEY,
                    org_id VARCHAR(36) NOT NULL REFERENCES organizations(id),
                    provider VARCHAR(32) NOT NULL,
                    provider_tenant_id VARCHAR(128) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    deleted_at TIMESTAMPTZ,
                    CONSTRAINT uq_oauth_provider_tenant UNIQUE (provider, provider_tenant_id)
                )
            """))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_org_oauth_bindings_provider "
                "ON org_oauth_bindings (provider)"
            ))
            logger.info("自动迁移：已创建 org_oauth_bindings 表")

        # 22c: 搬迁 users.feishu_uid → user_oauth_connections
        col = await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'feishu_uid'"
        ))
        if col.first() is not None:
            await conn.execute(text("""
                INSERT INTO user_oauth_connections (id, user_id, provider, provider_user_id, provider_tenant_id)
                SELECT gen_random_uuid()::text, u.id, 'feishu', u.feishu_uid, u.feishu_tenant_key
                FROM users u
                WHERE u.feishu_uid IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM user_oauth_connections c
                    WHERE c.provider = 'feishu' AND c.provider_user_id = u.feishu_uid
                  )
            """))
            logger.info("自动迁移：已搬迁 feishu_uid 数据到 user_oauth_connections")
            await conn.execute(text("ALTER TABLE users DROP COLUMN feishu_uid"))
            logger.info("自动迁移：已删除 users.feishu_uid 列")

        # 22d: 搬迁 organizations.feishu_tenant_key → org_oauth_bindings
        col = await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'organizations' AND column_name = 'feishu_tenant_key'"
        ))
        if col.first() is not None:
            await conn.execute(text("""
                INSERT INTO org_oauth_bindings (id, org_id, provider, provider_tenant_id)
                SELECT gen_random_uuid()::text, o.id, 'feishu', o.feishu_tenant_key
                FROM organizations o
                WHERE o.feishu_tenant_key IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM org_oauth_bindings b
                    WHERE b.provider = 'feishu' AND b.provider_tenant_id = o.feishu_tenant_key
                  )
            """))
            logger.info("自动迁移：已搬迁 feishu_tenant_key 数据到 org_oauth_bindings")
            await conn.execute(text("ALTER TABLE organizations DROP COLUMN feishu_tenant_key"))
            logger.info("自动迁移：已删除 organizations.feishu_tenant_key 列")

        # 22e: 删除 users.feishu_tenant_key（数据已在 user_oauth_connections.provider_tenant_id）
        col = await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'feishu_tenant_key'"
        ))
        if col.first() is not None:
            await conn.execute(text("ALTER TABLE users DROP COLUMN feishu_tenant_key"))
            logger.info("自动迁移：已删除 users.feishu_tenant_key 列")

    # ── 迁移 5e: 种子数据（默认组织 + 套餐 + 数据归属） ──
    async with async_session_factory() as db:
        from app.models.org_membership import OrgMembership, OrgRole
        from app.models.organization import Organization
        from app.models.plan import Plan
        from app.models.user import User

        # 检查是否已有组织（幂等）
        org_result = await db.execute(
            select(Organization).where(Organization.slug.in_(["default", "nodesk-ai"]))
        )
        default_org = org_result.scalar_one_or_none()

        if default_org is None:
            import uuid
            default_org_id = str(uuid.uuid4())
            default_org = Organization(
                id=default_org_id,
                name="NoDesk AI",
                slug="nodesk-ai",
                plan="pro",
                max_instances=50,
                max_cpu_total="200",
                max_mem_total="400Gi",
                max_storage_total="2000Gi",
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

        # 种子预设工作区模板（幂等）
        from app.models.workspace_template import WorkspaceTemplate
        import json as _json
        preset_names = ["软件研发团队", "内容工作室", "研究实验室"]
        preset_files = ["software_team.json", "content_studio.json", "research_lab.json"]
        for pname, pfile in zip(preset_names, preset_files):
            exists = await db.execute(
                select(WorkspaceTemplate).where(
                    WorkspaceTemplate.name == pname,
                    WorkspaceTemplate.is_preset.is_(True),
                    WorkspaceTemplate.deleted_at.is_(None),
                ).limit(1)
            )
            if exists.scalar_one_or_none():
                continue
            path = os.path.join(os.path.dirname(__file__), "presets", "workspace_templates", pfile)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    data = _json.load(f)
                t = WorkspaceTemplate(
                    id=str(__import__("uuid").uuid4()),
                    name=data.get("name", pname),
                    description=data.get("description", ""),
                    is_preset=True,
                    topology_snapshot=data.get("topology_snapshot", {}),
                    blackboard_snapshot=data.get("blackboard_snapshot", {}),
                    gene_assignments=data.get("gene_assignments", []),
                    created_by=None,
                )
                db.add(t)
        await db.commit()
        logger.info("自动迁移：已种子化预设工作区模板")

        # 默认基因/基因组改为一次性 SQL 回填；启动流程不再自动写入

    # ── 迁移 23: 为 super_admin 用户创建 AdminMembership 记录 ──
    async with async_session_factory() as db:
        from app.models.admin_membership import AdminMembership
        from app.models.user import User

        super_admins = await db.execute(
            select(User).where(
                User.is_super_admin.is_(True),
                User.current_org_id.isnot(None),
                User.deleted_at.is_(None),
            )
        )
        for u in super_admins.scalars().all():
            existing = await db.execute(
                select(AdminMembership).where(
                    AdminMembership.user_id == u.id,
                    AdminMembership.org_id == u.current_org_id,
                    AdminMembership.deleted_at.is_(None),
                )
            )
            if existing.scalar_one_or_none() is None:
                db.add(AdminMembership(user_id=u.id, org_id=u.current_org_id, role="admin"))
                logger.info("自动迁移：为超管用户 %s 创建 AdminMembership(admin)", u.name)
        await db.commit()

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

    # ── 迁移 9: 为每个组织创建默认工作区并迁移现有实例 ──
    async with async_session_factory() as db:
        from app.models.blackboard import Blackboard
        from app.models.instance import Instance
        from app.models.org_membership import OrgMembership
        from app.models.organization import Organization
        from app.models.workspace import Workspace
        from app.models.workspace_member import WorkspaceMember

        orgs_result = await db.execute(
            select(Organization).where(Organization.deleted_at.is_(None))
        )
        for org in orgs_result.scalars().all():
            ws_exists = await db.execute(
                select(Workspace).where(
                    Workspace.org_id == org.id,
                    Workspace.deleted_at.is_(None),
                ).limit(1)
            )
            if ws_exists.scalar_one_or_none():
                continue

            orphan_check = await db.execute(
                select(Instance).where(
                    Instance.org_id == org.id,
                    Instance.workspace_id.is_(None),
                    Instance.deleted_at.is_(None),
                ).limit(1)
            )
            if orphan_check.scalar_one_or_none() is None:
                continue

            first_member_result = await db.execute(
                select(OrgMembership).where(
                    OrgMembership.org_id == org.id
                ).limit(1)
            )
            first_member = first_member_result.scalar_one_or_none()

            import uuid
            ws = Workspace(
                id=str(uuid.uuid4()),
                org_id=org.id,
                name="默认工作区",
                description="自动创建的默认工作区",
                created_by=first_member.user_id if first_member else "system",
            )
            db.add(ws)
            await db.flush()

            bb = Blackboard(workspace_id=ws.id)
            db.add(bb)

            if first_member:
                owner = WorkspaceMember(
                    workspace_id=ws.id,
                    user_id=first_member.user_id,
                    role="owner",
                )
                db.add(owner)

            orphans = await db.execute(
                select(Instance).where(
                    Instance.org_id == org.id,
                    Instance.workspace_id.is_(None),
                    Instance.deleted_at.is_(None),
                )
            )
            idx = 0
            directions = [(0, -1), (-1, 0), (-1, 1), (0, 1), (1, 0), (1, -1)]
            for inst in orphans.scalars().all():
                inst.workspace_id = ws.id
                # spiral position
                positions: list[tuple[int, int]] = []
                q, r, ring = 1, 0, 1
                while len(positions) <= idx:
                    for dq, dr in directions:
                        for _ in range(ring):
                            if len(positions) > idx:
                                break
                            positions.append((q, r))
                            q += dq; r += dr
                    ring += 1; q += 1
                inst.hex_position_q, inst.hex_position_r = positions[idx]
                inst.agent_display_name = inst.name
                idx += 1

            await db.commit()
            logger.info("自动迁移：已为组织 %s 创建默认工作区并迁移 %d 个实例", org.name, idx)

    # ── 迁移 10: instances 表添加 llm_providers (实例级 LLM 配置隔离) ──
    async with engine.begin() as conn:
        col = (await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='instances' AND column_name='llm_providers'"
        ))).first()
        if col is None:
            await conn.execute(text(
                "ALTER TABLE instances ADD COLUMN llm_providers JSONB"
            ))
            logger.info("自动迁移：已为 instances 表添加 llm_providers 列")

        col = (await conn.execute(text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'instances' AND column_name = 'agent_theme_color'"
        ))).first()
        if col is None:
            await conn.execute(text(
                "ALTER TABLE instances ADD COLUMN agent_theme_color VARCHAR(7)"
            ))
            logger.info("自动迁移：已为 instances 表添加 agent_theme_color 列")

    # ── 迁移 24: 为已有实例补建 InstanceMember 记录 ──
    async with engine.begin() as conn:
        await conn.execute(text("""
            INSERT INTO instance_members (id, instance_id, user_id, role, created_at, updated_at)
            SELECT gen_random_uuid()::text, id, created_by, 'admin', now(), now()
            FROM instances
            WHERE deleted_at IS NULL AND created_by IS NOT NULL
            AND id NOT IN (SELECT instance_id FROM instance_members WHERE deleted_at IS NULL)
        """))
        affected = conn.info.get("rowcount", 0)
        logger.info("迁移 24：为已有实例补建 InstanceMember 记录，影响 %s 行", affected)

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

    # ── 恢复工作区 SSE 连接 ──
    from app.services.sse_listener import sse_listener_manager

    async with async_session_factory() as db:
        from app.models.instance import Instance
        ws_agents = await db.execute(
            select(Instance).where(
                Instance.workspace_id.isnot(None),
                Instance.status.in_(["running", "restarting", "learning"]),
                Instance.ingress_domain.isnot(None),
                Instance.deleted_at.is_(None),
            )
        )
        instances = ws_agents.scalars().all()

        for inst in instances:
            if inst.status in ("restarting", "learning"):
                inst.status = "running"
                logger.info("修复卡死状态: %s %s -> running", inst.name, inst.status)
        if instances:
            await db.commit()

        for inst in instances:
            await sse_listener_manager.connect(
                inst.id, inst.ingress_domain,
                workspace_id=inst.workspace_id,
                delay=10,
            )
    logger.info(
        "已恢复 %d 个工作区 SSE 连接",
        len(sse_listener_manager.connected_instances),
    )

    yield

    # ── Shutdown ─────────────────────────────────────
    for ws_client in feishu_ws_clients:
        ws_client.stop()
    await sse_listener_manager.disconnect_all()
    logger.info("已关闭所有 SSE 连接")
    await summary_job.stop()
    await schedule_runner.stop()
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
app.include_router(admin_router, prefix="/api/v1/admin")
app.include_router(webhook_router)

if settings.DEBUG:
    from app.api.llm_proxy import router as llm_proxy_router
    app.include_router(llm_proxy_router, tags=["LLM 代理（开发模式）"])

# ── Static files (前端 build 产物) ───────────────────
# 生产环境：Vite build 后的 dist 目录会被复制到 static/
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
