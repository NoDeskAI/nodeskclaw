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
    ce_creds = await _seed_initial_admin(session_factory)
    ee_creds = None
    if is_ee:
        ee_creds = await _seed_ee_platform_admin(session_factory)
    await _ensure_workspace_schedules(session_factory)
    return {"ce_admin": ce_creds, "ee_admin": ee_creds}


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

        stale = await db.execute(
            select(AdminMembership).where(
                AdminMembership.user_id != admin.id,
                AdminMembership.deleted_at.is_(None),
            )
        )
        stale_records = stale.scalars().all()
        if stale_records:
            stale_ids = [r.id for r in stale_records]
            await db.execute(
                update(AdminMembership)
                .where(AdminMembership.id.in_(stale_ids))
                .values(deleted_at=func.now())
            )
            await db.commit()
            logger.info(
                "种子数据：已清理 %d 条不属于 EE 平台管理员的 AdminMembership 残留记录",
                len(stale_ids),
            )

        if plain_password:
            return {"account": account, "password": plain_password}
        return None


async def _ensure_workspace_schedules(session_factory: async_sessionmaker[AsyncSession]) -> None:
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
                    WorkspaceSchedule.name == "任务巡检",
                    WorkspaceSchedule.deleted_at.is_(None),
                )
            )).scalar_one_or_none()
            if existing is None:
                db.add(WorkspaceSchedule(
                    workspace_id=ws.id,
                    name="任务巡检",
                    cron_expr="0 */4 * * *",
                    message_template="请检查黑板待办任务队列，接取并执行优先级最高的任务。完成后汇报进展。",
                    is_active=True,
                ))
        await db.commit()
        logger.info("种子数据：已为 %d 个工作区检查/补建任务巡检定时器", len(all_ws))
