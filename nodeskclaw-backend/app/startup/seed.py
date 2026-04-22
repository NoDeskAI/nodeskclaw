"""Idempotent seed data & runtime补建 — runs on every startup."""

import json
import logging
import os
import secrets

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)


async def run_seed(
    session_factory: async_sessionmaker[AsyncSession], *, is_ee: bool = False,
) -> dict[str, dict[str, str] | None]:
    """Run all seed tasks. Returns dict with 'ce_admin' and 'ee_admin' credentials."""
    await _seed_default_org_and_templates(session_factory, is_ee=is_ee)
    await _seed_default_registry_configs(session_factory)
    ce_creds = await _seed_initial_admin(session_factory)
    ee_creds = None
    if is_ee:
        ee_creds = await _seed_ee_platform_admin(session_factory)
    await _ensure_workspace_schedules(session_factory)
    return {"ce_admin": ce_creds, "ee_admin": ee_creds}


DEFAULT_REGISTRY_CONFIGS: dict[str, str] = {
    "image_registry": "nodesk-center-cn-beijing.cr.volces.com/public/deskclaw-openclaw",
    "image_registry_nanobot": "nodesk-center-cn-beijing.cr.volces.com/public/deskclaw-nanobot",
}


async def _seed_default_registry_configs(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Seed default image registry URLs so tag listing works out-of-the-box.

    Only inserts when a key does NOT exist at all.  If the admin deliberately
    cleared a value (row exists, value=None), we leave it untouched.
    """
    from app.models.system_config import SystemConfig

    async with session_factory() as db:
        seeded = 0
        for key, default_value in DEFAULT_REGISTRY_CONFIGS.items():
            row = (await db.execute(
                select(SystemConfig).where(
                    SystemConfig.key == key,
                    SystemConfig.deleted_at.is_(None),
                )
            )).scalar_one_or_none()
            if row is None:
                db.add(SystemConfig(key=key, value=default_value))
                seeded += 1
        if seeded:
            await db.commit()
            logger.info("种子数据：已内置 %d 条默认镜像仓库配置", seeded)


async def _seed_initial_admin(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, str] | None:
    account = settings.INIT_ADMIN_ACCOUNT.strip()
    if not account:
        return None

    from app.models.org_membership import OrgMembership, OrgRole
    from app.models.organization import Organization
    from app.models.user import User, UserRole
    from app.services.auth_service import _hash_password

    async with session_factory() as db:
        result = await db.execute(
            select(User).where(User.username == account, User.deleted_at.is_(None))
        )
        admin = result.scalar_one_or_none()

        plain_password: str | None = None

        if admin is not None and not admin.email:
            admin.email = "admin@deskclaw.com"
            await db.commit()

        if admin is None:
            plain_password = secrets.token_urlsafe(9)
            admin = User(
                name="Admin",
                username=account,
                email="admin@deskclaw.com",
                role=UserRole.admin,
                is_super_admin=True,
                is_active=True,
                must_change_password=True,
                password_hash=_hash_password(plain_password),
            )
            db.add(admin)
            await db.flush()

            org_result = await db.execute(
                select(Organization).where(Organization.deleted_at.is_(None)).limit(1)
            )
            default_org = org_result.scalar_one_or_none()
            if default_org is not None:
                admin.current_org_id = default_org.id
                db.add(OrgMembership(
                    user_id=admin.id, org_id=default_org.id, role=OrgRole.admin,
                ))

            await db.commit()
            logger.info("种子数据：已创建 CE 超管用户 [%s]", account)

        elif settings.RESET_ADMIN_PASSWORD:
            plain_password = secrets.token_urlsafe(9)
            admin.password_hash = _hash_password(plain_password)
            admin.must_change_password = True
            await db.commit()
            logger.info("种子数据：已重置超管 [%s] 密码（RESET_ADMIN_PASSWORD=True）", account)

        elif admin.must_change_password:
            plain_password = secrets.token_urlsafe(9)
            admin.password_hash = _hash_password(plain_password)
            await db.commit()
            logger.info("种子数据：超管 [%s] 尚未改密，已重新生成随机密码", account)

        if plain_password:
            return {"account": account, "password": plain_password}
        return None


async def _seed_default_org_and_templates(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    is_ee: bool,
) -> None:
    async with session_factory() as db:
        from app.models.org_membership import OrgMembership, OrgRole
        from app.models.organization import Organization
        from app.models.user import User

        org_result = await db.execute(
            select(Organization).where(Organization.deleted_at.is_(None))
        )
        default_org = org_result.scalars().first()

        if default_org is None:
            import uuid
            default_org_id = str(uuid.uuid4())
            default_org = Organization(
                id=default_org_id,
                name="Default Organization",
                slug="default",
                plan="pro",
                max_instances=50,
                max_cpu_total="200",
                max_mem_total="400Gi",
                max_storage_total="2000Gi",
            )
            db.add(default_org)
            await db.flush()

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
            logger.info("种子数据：已创建默认组织并迁移现有数据")

        if is_ee:
            try:
                from ee.backend.seed import seed_plans
                await seed_plans(db)
            except ImportError:
                pass

        from app.models.workspace_template import WorkspaceTemplate
        preset_names = ["软件研发团队", "内容工作室", "研究实验室", "自媒体内容工作室"]
        preset_files = ["software_team.json", "content_studio.json", "research_lab.json", "content_media_studio.json"]
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
            path = os.path.join(os.path.dirname(__file__), "..", "presets", "workspace_templates", pfile)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                t = WorkspaceTemplate(
                    id=str(__import__("uuid").uuid4()),
                    name=data.get("name", pname),
                    description=data.get("description", ""),
                    is_preset=True,
                    topology_snapshot=data.get("topology_snapshot", {}),
                    blackboard_snapshot=data.get("blackboard_snapshot", {}),
                    gene_assignments=data.get("gene_assignments", []),
                    agent_specs=data.get("agent_specs", []),
                    human_specs=data.get("human_specs", []),
                    created_by=None,
                )
                db.add(t)
        await db.commit()
        logger.info("种子数据：预设办公室模板已就绪")


async def _seed_ee_platform_admin(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, str] | None:
    """Create the EE Admin platform administrator (separate from CE Portal admin)."""
    account = settings.INIT_EE_ADMIN_ACCOUNT.strip()
    if not account:
        return None

    if account == settings.INIT_ADMIN_ACCOUNT.strip():
        logger.warning(
            "INIT_EE_ADMIN_ACCOUNT \u4e0e INIT_ADMIN_ACCOUNT \u76f8\u540c\uff08%s\uff09\uff0c\u8df3\u8fc7 EE \u7ba1\u7406\u5458\u521b\u5efa",
            account,
        )
        return None

    from app.models.admin_membership import AdminMembership
    from app.models.org_membership import OrgMembership, OrgRole
    from app.models.organization import Organization
    from app.models.user import User, UserRole
    from app.services.auth_service import _hash_password

    async with session_factory() as db:
        result = await db.execute(
            select(User).where(User.username == account, User.deleted_at.is_(None))
        )
        admin = result.scalar_one_or_none()

        plain_password: str | None = None

        if admin is None:
            plain_password = secrets.token_urlsafe(9)
            admin = User(
                name="DeskClaw Admin",
                username=account,
                email="deskclaw-admin@deskclaw.com",
                role=UserRole.admin,
                is_super_admin=True,
                is_active=True,
                must_change_password=True,
                password_hash=_hash_password(plain_password),
            )
            db.add(admin)
            await db.flush()

            org_result = await db.execute(
                select(Organization).where(Organization.deleted_at.is_(None)).limit(1)
            )
            default_org = org_result.scalar_one_or_none()
            if default_org is not None:
                admin.current_org_id = default_org.id
                db.add(OrgMembership(
                    user_id=admin.id, org_id=default_org.id, role=OrgRole.admin,
                ))
                db.add(AdminMembership(
                    user_id=admin.id, org_id=default_org.id, role="admin",
                ))

            await db.commit()
            logger.info("\u79cd\u5b50\u6570\u636e\uff1a\u5df2\u521b\u5efa EE \u5e73\u53f0\u7ba1\u7406\u5458 [%s]", account)

        elif settings.RESET_EE_ADMIN_PASSWORD:
            plain_password = secrets.token_urlsafe(9)
            admin.password_hash = _hash_password(plain_password)
            admin.must_change_password = True
            await db.commit()
            logger.info(
                "\u79cd\u5b50\u6570\u636e\uff1a\u5df2\u91cd\u7f6e EE \u5e73\u53f0\u7ba1\u7406\u5458 [%s] \u5bc6\u7801\uff08RESET_EE_ADMIN_PASSWORD=True\uff09",
                account,
            )

        elif admin.must_change_password:
            plain_password = secrets.token_urlsafe(9)
            admin.password_hash = _hash_password(plain_password)
            await db.commit()
            logger.info(
                "\u79cd\u5b50\u6570\u636e\uff1aEE \u5e73\u53f0\u7ba1\u7406\u5458 [%s] \u5c1a\u672a\u6539\u5bc6\uff0c\u5df2\u91cd\u65b0\u751f\u6210\u968f\u673a\u5bc6\u7801",
                account,
            )

        if admin.current_org_id is None:
            org_result = await db.execute(
                select(Organization).where(Organization.deleted_at.is_(None)).limit(1)
            )
            default_org = org_result.scalar_one_or_none()
            if default_org is not None:
                admin.current_org_id = default_org.id
                existing_om = await db.execute(
                    select(OrgMembership).where(
                        OrgMembership.user_id == admin.id,
                        OrgMembership.org_id == default_org.id,
                        OrgMembership.deleted_at.is_(None),
                    )
                )
                if existing_om.scalar_one_or_none() is None:
                    db.add(OrgMembership(
                        user_id=admin.id, org_id=default_org.id, role=OrgRole.admin,
                    ))
                await db.commit()
                logger.info("\u79cd\u5b50\u6570\u636e\uff1a\u4e3a EE \u5e73\u53f0\u7ba1\u7406\u5458\u8865\u5efa\u7ec4\u7ec7\u5173\u8054")

        if admin.current_org_id is not None:
            existing_am = await db.execute(
                select(AdminMembership).where(
                    AdminMembership.user_id == admin.id,
                    AdminMembership.org_id == admin.current_org_id,
                    AdminMembership.deleted_at.is_(None),
                )
            )
            if existing_am.scalar_one_or_none() is None:
                db.add(AdminMembership(
                    user_id=admin.id, org_id=admin.current_org_id, role="admin",
                ))
                await db.commit()
                logger.info("\u79cd\u5b50\u6570\u636e\uff1a\u4e3a EE \u5e73\u53f0\u7ba1\u7406\u5458\u8865\u5efa AdminMembership")

        if plain_password:
            return {"account": account, "password": plain_password}
        return None


DEFAULT_REQUIRED_GENE_SLUGS: list[str] = [
    "nodeskclaw-blackboard-tools",
    "nodeskclaw-topology-awareness",
    "nodeskclaw-performance-reader",
    "nodeskclaw-proposals",
    "nodeskclaw-gene-discovery",
    "nodeskclaw-shared-files",
    "akr-decomposer",
]


async def seed_default_required_genes(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """为没有任何默认工作基因的组织补建 ai-employee-basics 基因组。

    保护逻辑：仅当组织的 OrgRequiredGene 记录数为 0 时才填充。
    管理员已手动配置过（即使只配了 1 个）的组织不受影响。
    """
    from app.models.gene import Gene
    from app.models.org_required_gene import OrgRequiredGene
    from app.models.organization import Organization

    async with session_factory() as db:
        gene_rows = (await db.execute(
            select(Gene.id, Gene.slug).where(
                Gene.slug.in_(DEFAULT_REQUIRED_GENE_SLUGS),
                Gene.org_id.is_(None),
                Gene.deleted_at.is_(None),
            )
        )).all()
        slug_to_id = {row.slug: row.id for row in gene_rows}

        missing_slugs = set(DEFAULT_REQUIRED_GENE_SLUGS) - slug_to_id.keys()
        if missing_slugs:
            logger.warning("默认工作基因 seed 跳过缺失的 slug: %s", missing_slugs)

        if not slug_to_id:
            logger.warning("默认工作基因 seed 跳过：genes 表中未找到任何目标基因")
            return

        orgs = (await db.execute(
            select(Organization).where(Organization.deleted_at.is_(None))
        )).scalars().all()

        seeded_orgs = 0
        for org in orgs:
            count = (await db.execute(
                select(func.count()).select_from(OrgRequiredGene).where(
                    OrgRequiredGene.org_id == org.id,
                    OrgRequiredGene.deleted_at.is_(None),
                )
            )).scalar_one()

            if count > 0:
                continue

            for slug, gene_id in slug_to_id.items():
                db.add(OrgRequiredGene(org_id=org.id, gene_id=gene_id))
            seeded_orgs += 1

        if seeded_orgs:
            await db.commit()
            logger.info(
                "默认工作基因 seed 完成：为 %d 个组织添加了 %d 个默认基因",
                seeded_orgs, len(slug_to_id),
            )
        else:
            logger.info("默认工作基因检查完成，所有组织已有配置")


async def _ensure_workspace_schedules(session_factory: async_sessionmaker[AsyncSession]) -> None:
    from app.services.workspace_defaults import (
        DEFAULT_WORKSPACE_SCHEDULE_MESSAGE,
        DEFAULT_WORKSPACE_SCHEDULE_NAME,
        LEGACY_WORKSPACE_SCHEDULE_NAMES,
    )

    async with session_factory() as db:
        from app.models.workspace import Workspace
        from app.models.workspace_schedule import WorkspaceSchedule

        all_ws = (await db.execute(
            select(Workspace).where(Workspace.deleted_at.is_(None))
        )).scalars().all()

        for ws in all_ws:
            existing = (await db.execute(
                select(WorkspaceSchedule).where(
                    WorkspaceSchedule.workspace_id == ws.id,
                    WorkspaceSchedule.name.in_(LEGACY_WORKSPACE_SCHEDULE_NAMES),
                    WorkspaceSchedule.deleted_at.is_(None),
                ).order_by(WorkspaceSchedule.created_at.desc())
            )).scalars().first()
            if existing is None:
                db.add(WorkspaceSchedule(
                    workspace_id=ws.id,
                    name=DEFAULT_WORKSPACE_SCHEDULE_NAME,
                    cron_expr="0 */4 * * *",
                    message_template=DEFAULT_WORKSPACE_SCHEDULE_MESSAGE,
                    is_active=False,
                ))
        await db.commit()
        logger.info("种子数据：已为 %d 个工作区检查/补建定时巡检定时器", len(all_ws))


async def seed_engine_versions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Populate EngineVersion from existing Instance records on first run.

    Only runs when the table is empty — does not overwrite admin choices.
    """
    from app.models.engine_version import EngineVersion
    from app.models.instance import Instance

    async with session_factory() as db:
        count = (await db.execute(
            select(func.count()).select_from(EngineVersion).where(
                EngineVersion.deleted_at.is_(None),
            )
        )).scalar_one()
        if count > 0:
            return

        rows = (await db.execute(
            select(Instance.runtime, Instance.image_version)
            .where(
                Instance.image_version.isnot(None),
                Instance.image_version != "",
                Instance.deleted_at.is_(None),
            )
            .distinct()
        )).all()

        if not rows:
            return

        def _version_key(v: str) -> tuple[int, ...]:
            try:
                return tuple(int(x) for x in v.lstrip("v").split("."))
            except ValueError:
                return (0,)

        by_runtime: dict[str, list[tuple[str, str]]] = {}
        for runtime, image_version in rows:
            rt = runtime or "openclaw"
            by_runtime.setdefault(rt, []).append((image_version, image_version))

        for rt, versions in by_runtime.items():
            versions.sort(key=lambda x: _version_key(x[0]), reverse=True)
            for idx, (image_tag, _) in enumerate(versions):
                stripped = image_tag.lstrip("v") if image_tag.startswith("v") else image_tag
                db.add(EngineVersion(
                    runtime=rt,
                    version=stripped,
                    image_tag=image_tag,
                    status="published",
                    is_default=(idx == 0),
                ))

        await db.commit()
        total = sum(len(v) for v in by_runtime.values())
        logger.info("种子数据：从现有实例导入 %d 个引擎版本到版本目录", total)


async def backfill_cluster_org_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """为 org_id 为空的活跃集群回填组织 ID（幂等）。

    仅当系统中只有一个活跃组织时自动回填；多组织场景打 WARNING 跳过。
    """
    from app.models.cluster import Cluster
    from app.models.organization import Organization

    async with session_factory() as db:
        orphan_result = await db.execute(
            select(func.count()).select_from(Cluster).where(
                Cluster.org_id.is_(None),
                Cluster.deleted_at.is_(None),
            )
        )
        orphan_count = orphan_result.scalar_one()
        if orphan_count == 0:
            return

        org_result = await db.execute(
            select(Organization).where(Organization.deleted_at.is_(None))
        )
        orgs = org_result.scalars().all()

        if len(orgs) == 0:
            logger.warning("集群 org_id 回填跳过：系统中无活跃组织")
            return

        if len(orgs) > 1:
            logger.warning(
                "集群 org_id 回填跳过：系统中有 %d 个活跃组织，需管理员手动分配 %d 个无组织集群",
                len(orgs), orphan_count,
            )
            return

        default_org = orgs[0]
        await db.execute(
            update(Cluster)
            .where(Cluster.org_id.is_(None), Cluster.deleted_at.is_(None))
            .values(org_id=default_org.id)
        )
        await db.commit()
        logger.info("集群 org_id 回填完成：%d 个集群已关联到组织 %s", orphan_count, default_org.name)
