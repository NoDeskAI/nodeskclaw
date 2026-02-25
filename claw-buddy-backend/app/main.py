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
                    {"key": f"clawbuddy-wp-{_secrets_mod.token_hex(32)}", "id": row.id},
                )
            logger.info("自动迁移：已为 instances 表添加 wp_api_key 列并回填")

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

        # 种子基因（幂等）
        import json as _json
        from app.models.gene import Gene, Genome

        _meta_learning_content = (
            "---\n"
            "name: meta-learning\n"
            "description: Agent learning meta-skill that evaluates gene content and decides between direct install or deep learning. Handles social gene recommendations in workspace chat.\n"
            "metadata:\n"
            '  { "openclaw": { "always": true } }\n'
            "---\n\n"
            "# Meta-Learning\n\n"
            "## Learning Ability\n\n"
            "You can learn new skills/genes. When presented with a gene to learn:\n\n"
            "1. Evaluate content complexity and your existing knowledge\n"
            "2. Decide: direct install (simple, already understood) or deep learn (complex, novel)\n"
            "3. If deep learning: study the content, practice with provided scenarios, generate your personalized version\n"
            "4. Self-evaluate understanding (0.0-1.0 score)\n\n"
            "## SKILL.md Frontmatter Standard\n\n"
            "When you deep-learn a gene or create a new skill, your output SKILL.md MUST begin with YAML frontmatter.\n"
            "OpenClaw uses this frontmatter to discover and configure skills.\n\n"
            "### Format\n\n"
            "```yaml\n"
            "---\n"
            "name: skill-name\n"
            "description: One-line description of what the skill does and when to use it.\n"
            "metadata:\n"
            '  { "openclaw": { "always": true } }\n'
            "---\n"
            "```\n\n"
            "### Required fields\n\n"
            "- `name`: kebab-case identifier matching the skill directory name\n"
            "- `description`: concise description including trigger words if user-invocable\n\n"
            "### Optional metadata fields (under metadata.openclaw)\n\n"
            "- `always: true` -- skill is always active regardless of runtime requirements\n"
            '- `requires.bins: ["cmd"]` -- require specific binaries\n'
            '- `requires.env: ["API_KEY"]` -- require specific environment variables\n'
            "- `emoji` -- display emoji for the skill\n\n"
            "### Example\n\n"
            "```yaml\n"
            "---\n"
            "name: code-review\n"
            "description: Systematic code review covering security, performance, and maintainability.\n"
            "metadata:\n"
            '  { "openclaw": { "always": true } }\n'
            "---\n\n"
            "# Code Review\n"
            "(skill content here)\n"
            "```\n\n"
            "### Rules\n\n"
            "- NEVER output a SKILL.md without frontmatter\n"
            "- Set `always: true` for behavioral/personality skills that should always be active\n"
            "- Set `requires` only when the skill depends on external tools or env vars\n\n"
            "## Social Gene Recommendation\n\n"
            "When you join a workspace or during ongoing collaboration:\n\n"
            "1. Analyze the workspace team goals (from workspace description)\n"
            "2. Review the current team members' installed genes and capabilities\n"
            "3. Identify missing capabilities that would benefit the team\n"
            "4. Recommend specific genes to one or more agents (including yourself) via group chat\n"
            "5. Format: '@AgentName I recommend you learn the `gene-slug` gene because [reason based on team goals]'\n\n"
            "## Responding to Recommendations\n\n"
            "When another agent recommends a gene to you in chat:\n\n"
            "1. Evaluate whether the recommendation aligns with your role and team goals\n"
            "2. If relevant, express acceptance and the gene will be auto-installed via the learning channel\n"
            "3. If not relevant, explain why and suggest alternatives\n\n"
            "## Periodic Self-Evaluation\n\n"
            "After learning a gene and using it in practice:\n\n"
            "1. Periodically assess how much the gene improved your capabilities (every ~10 interactions)\n"
            "2. Report self-evaluation scores through the learning channel\n"
            "3. If a gene is no longer useful, recommend removal"
        )

        gene_result = await db.execute(select(Gene).limit(1))
        if gene_result.scalar_one_or_none() is None:
            seed_genes = [
                Gene(
                    name="Meta-Learning", slug="meta-learning",
                    description="赋予 Agent 自主学习能力。安装后 Agent 可以评估基因内容并自主决定直接安装或深度学习，还能识别群聊中的基因推荐消息并自动响应。",
                    short_description="Agent 学习能力基因 - 自主决定学习方式",
                    category="效率", tags=_json.dumps(["能力"]),
                    source="official", icon="GraduationCap", version="1.0.0",
                    manifest=_json.dumps({
                        "skill": {"name": "meta-learning", "content": _meta_learning_content},
                    }),
                    is_featured=True, is_published=True,
                ),
                Gene(
                    name="Meta-Creation", slug="meta-creation",
                    description="赋予 Agent 创造新基因的能力。Agent 可以从工作经验中提炼方法论，生成完整的基因包（SKILL.md + 配置 + 元数据）。",
                    short_description="Agent 创造能力基因 - 从经验中提炼新基因",
                    category="效率", tags=_json.dumps(["能力"]),
                    source="official", icon="Sparkles", version="1.0.0",
                    manifest=_json.dumps({
                        "skill": {"name": "meta-creation", "content": "---\nname: meta-creation\ndescription: Create new genes from work experience. Identify reusable methodologies, structure them as complete gene packages with SKILL.md and metadata.\nmetadata:\n  { \"openclaw\": { \"always\": true } }\n---\n\n# Meta-Creation\n\nYou can create new genes from your work experience. When you accumulate enough expertise in a domain:\n\n1. Identify a reusable methodology or skill\n2. Structure it as a complete gene: SKILL.md content + metadata (tags, category, synergies)\n3. Include learning objectives and scenarios for other agents\n4. Submit for review\n\nYou can also mark gene synergies when you discover that two genes work well together."},
                    }),
                    synergies=_json.dumps(["meta-learning"]),
                    is_featured=True, is_published=True,
                ),
                Gene(
                    name="Code Review", slug="code-review",
                    description="系统化的代码审查方法论，包括安全检查、性能评估、可维护性分析。",
                    short_description="代码审查能力",
                    category="开发", tags=_json.dumps(["能力"]),
                    source="official", icon="FileSearch", version="1.0.0",
                    manifest=_json.dumps({
                        "skill": {"name": "code-review", "content": "---\nname: code-review\ndescription: Systematic code review covering security, performance, maintainability, and best practices. Use when reviewing PRs or auditing codebases.\n---\n\n# Code Review\n\nWhen reviewing code, follow this systematic approach:\n\n1. **Security**: Check for injection, auth bypass, data exposure\n2. **Performance**: Identify N+1 queries, memory leaks, unnecessary computation\n3. **Maintainability**: Assess naming, structure, test coverage\n4. **Best Practices**: Language-specific idioms, design patterns"},
                        "learning": {
                            "objectives": ["掌握系统化代码审查流程", "识别常见安全漏洞"],
                            "scenarios": [{"prompt": "审查一个包含 SQL 拼接的 Python 函数", "context": "Web API 端点", "expected_focus": ["SQL 注入", "参数化查询"]}],
                        },
                    }),
                    synergies=_json.dumps(["security-audit"]),
                    is_featured=True, is_published=True,
                ),
                Gene(
                    name="Analytical Thinking", slug="analytical-thinking",
                    description="培养结构化分析思维，先拆解问题再逐步推理。",
                    short_description="结构化分析思维模式",
                    category="效率", tags=_json.dumps(["性格"]),
                    source="official", icon="Brain", version="1.0.0",
                    manifest=_json.dumps({
                        "skill": {"name": "analytical-thinking", "content": "---\nname: analytical-thinking\ndescription: Structured analytical thinking pattern. Decompose problems, reason step by step, validate conclusions.\nmetadata:\n  { \"openclaw\": { \"always\": true } }\n---\n\n# Analytical Thinking\n\nApproach every problem systematically:\n1. Decompose into sub-problems\n2. Identify assumptions and constraints\n3. Reason step by step\n4. Validate conclusions against evidence\n5. Consider edge cases and failure modes"},
                    }),
                    is_featured=True, is_published=True,
                ),
                Gene(
                    name="Security Audit", slug="security-audit",
                    description="安全审计能力，识别 OWASP Top 10 漏洞，提出修复建议。",
                    short_description="安全审计与漏洞识别",
                    category="安全", tags=_json.dumps(["能力"]),
                    source="official", icon="Shield", version="1.0.0",
                    manifest=_json.dumps({
                        "skill": {"name": "security-audit", "content": "---\nname: security-audit\ndescription: Security audit capability covering OWASP Top 10, auth review, input validation, crypto best practices, and secrets management.\n---\n\n# Security Audit\n\nSystematically audit code and infrastructure for security vulnerabilities:\n\n- OWASP Top 10 checks\n- Authentication and authorization review\n- Input validation and sanitization\n- Cryptographic best practices\n- Secrets management"},
                        "learning": {
                            "objectives": ["掌握 OWASP Top 10 漏洞识别"],
                            "scenarios": [{"prompt": "审计一个 JWT 认证实现", "context": "Node.js Express API", "expected_focus": ["token 验证", "过期处理", "密钥管理"]}],
                        },
                    }),
                    synergies=_json.dumps(["code-review"]),
                    is_published=True,
                ),
                Gene(
                    name="K8s Architecture", slug="k8s-architecture",
                    description="Kubernetes 架构知识，包括核心概念、资源编排、网络模型、存储方案。",
                    short_description="Kubernetes 架构知识体系",
                    category="运维", tags=_json.dumps(["知识"]),
                    source="official", icon="Container", version="1.0.0",
                    manifest=_json.dumps({
                        "skill": {"name": "k8s-architecture", "content": "---\nname: k8s-architecture\ndescription: Kubernetes architecture knowledge covering core concepts, resource orchestration, networking, and storage.\nmetadata:\n  { \"openclaw\": { \"always\": true } }\n---\n\n# K8s Architecture Knowledge\n\nCore Kubernetes concepts:\n- Pod lifecycle, ReplicaSet, Deployment strategies\n- Service types, Ingress controllers, NetworkPolicy\n- PV/PVC, StorageClass, CSI drivers\n- RBAC, ServiceAccount, SecurityContext\n- Helm charts, Kustomize, GitOps"},
                    }),
                    is_published=True,
                ),
            ]
            db.add_all(seed_genes)
            await db.commit()
            logger.info("自动迁移：已种子化 %d 个基因", len(seed_genes))

            seed_genomes = [
                Genome(
                    name="全栈工程师", slug="fullstack-engineer",
                    description="适合全栈开发 Agent 的基因组合",
                    short_description="全栈开发能力组合",
                    icon="Layers",
                    gene_slugs=_json.dumps(["code-review", "analytical-thinking", "security-audit"]),
                    is_featured=True, is_published=True,
                ),
                Genome(
                    name="DevOps 工程师", slug="devops-engineer",
                    description="适合 DevOps/SRE Agent 的基因组合",
                    short_description="DevOps 能力组合",
                    icon="Server",
                    gene_slugs=_json.dumps(["k8s-architecture", "security-audit", "analytical-thinking"]),
                    is_featured=True, is_published=True,
                ),
            ]
            db.add_all(seed_genomes)
            await db.commit()
            logger.info("自动迁移：已种子化 %d 个基因组", len(seed_genomes))

        # 迁移：更新已有 official seed 基因的 manifest（补全 frontmatter）
        _seed_manifests: dict[str, str] = {
            "meta-learning": _json.dumps({"skill": {"name": "meta-learning", "content": _meta_learning_content}}),
            "meta-creation": _json.dumps({"skill": {"name": "meta-creation", "content": "---\nname: meta-creation\ndescription: Create new genes from work experience. Identify reusable methodologies, structure them as complete gene packages with SKILL.md and metadata.\nmetadata:\n  { \"openclaw\": { \"always\": true } }\n---\n\n# Meta-Creation\n\nYou can create new genes from your work experience. When you accumulate enough expertise in a domain:\n\n1. Identify a reusable methodology or skill\n2. Structure it as a complete gene: SKILL.md content + metadata (tags, category, synergies)\n3. Include learning objectives and scenarios for other agents\n4. Submit for review\n\nYou can also mark gene synergies when you discover that two genes work well together."}}),
            "code-review": _json.dumps({"skill": {"name": "code-review", "content": "---\nname: code-review\ndescription: Systematic code review covering security, performance, maintainability, and best practices. Use when reviewing PRs or auditing codebases.\n---\n\n# Code Review\n\nWhen reviewing code, follow this systematic approach:\n\n1. **Security**: Check for injection, auth bypass, data exposure\n2. **Performance**: Identify N+1 queries, memory leaks, unnecessary computation\n3. **Maintainability**: Assess naming, structure, test coverage\n4. **Best Practices**: Language-specific idioms, design patterns"}, "learning": {"objectives": ["\u638c\u63e1\u7cfb\u7edf\u5316\u4ee3\u7801\u5ba1\u67e5\u6d41\u7a0b", "\u8bc6\u522b\u5e38\u89c1\u5b89\u5168\u6f0f\u6d1e"], "scenarios": [{"prompt": "\u5ba1\u67e5\u4e00\u4e2a\u5305\u542b SQL \u62fc\u63a5\u7684 Python \u51fd\u6570", "context": "Web API \u7aef\u70b9", "expected_focus": ["SQL \u6ce8\u5165", "\u53c2\u6570\u5316\u67e5\u8be2"]}]}}),
            "analytical-thinking": _json.dumps({"skill": {"name": "analytical-thinking", "content": "---\nname: analytical-thinking\ndescription: Structured analytical thinking pattern. Decompose problems, reason step by step, validate conclusions.\nmetadata:\n  { \"openclaw\": { \"always\": true } }\n---\n\n# Analytical Thinking\n\nApproach every problem systematically:\n1. Decompose into sub-problems\n2. Identify assumptions and constraints\n3. Reason step by step\n4. Validate conclusions against evidence\n5. Consider edge cases and failure modes"}}),
            "security-audit": _json.dumps({"skill": {"name": "security-audit", "content": "---\nname: security-audit\ndescription: Security audit capability covering OWASP Top 10, auth review, input validation, crypto best practices, and secrets management.\n---\n\n# Security Audit\n\nSystematically audit code and infrastructure for security vulnerabilities:\n\n- OWASP Top 10 checks\n- Authentication and authorization review\n- Input validation and sanitization\n- Cryptographic best practices\n- Secrets management"}, "learning": {"objectives": ["\u638c\u63e1 OWASP Top 10 \u6f0f\u6d1e\u8bc6\u522b"], "scenarios": [{"prompt": "\u5ba1\u8ba1\u4e00\u4e2a JWT \u8ba4\u8bc1\u5b9e\u73b0", "context": "Node.js Express API", "expected_focus": ["token \u9a8c\u8bc1", "\u8fc7\u671f\u5904\u7406", "\u5bc6\u94a5\u7ba1\u7406"]}]}}),
            "k8s-architecture": _json.dumps({"skill": {"name": "k8s-architecture", "content": "---\nname: k8s-architecture\ndescription: Kubernetes architecture knowledge covering core concepts, resource orchestration, networking, and storage.\nmetadata:\n  { \"openclaw\": { \"always\": true } }\n---\n\n# K8s Architecture Knowledge\n\nCore Kubernetes concepts:\n- Pod lifecycle, ReplicaSet, Deployment strategies\n- Service types, Ingress controllers, NetworkPolicy\n- PV/PVC, StorageClass, CSI drivers\n- RBAC, ServiceAccount, SecurityContext\n- Helm charts, Kustomize, GitOps"}}),
        }
        _updated = 0
        for _slug, _new_manifest in _seed_manifests.items():
            _res = await db.execute(
                select(Gene).where(Gene.slug == _slug, Gene.source == "official")
            )
            _gene = _res.scalar_one_or_none()
            if _gene and _gene.manifest != _new_manifest:
                _gene.manifest = _new_manifest
                _updated += 1
        if _updated:
            await db.commit()
            logger.info("自动迁移：已更新 %d 个 seed 基因的 manifest（补全 frontmatter）", _updated)

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
    await sse_listener_manager.disconnect_all()
    logger.info("已关闭所有 SSE 连接")
    await summary_job.stop()
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

if settings.DEBUG:
    from app.api.llm_proxy import router as llm_proxy_router
    app.include_router(llm_proxy_router, tags=["LLM 代理（开发模式）"])

# ── Static files (前端 build 产物) ───────────────────
# 生产环境：Vite build 后的 dist 目录会被复制到 static/
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
