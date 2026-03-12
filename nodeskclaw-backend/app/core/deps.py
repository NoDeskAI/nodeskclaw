"""FastAPI dependency injection – DB session + RBAC helpers + FeatureGate."""

from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.feature_gate import feature_gate

_connect_args: dict = {"ssl": False}
if settings.DATABASE_NAME_SUFFIX:
    _connect_args["server_settings"] = {"search_path": "nodeskclaw, public"}

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args=_connect_args,
)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session, auto-close on exit."""
    async with async_session_factory() as session:
        yield session


# ── RBAC Dependencies ────────────────────────────────────
# 这些依赖在导入时需要延迟引用 security.get_current_user 以避免循环导入

def _get_current_user_dep():
    """延迟导入 get_current_user 以避免循环依赖。"""
    from app.core.security import get_current_user
    return get_current_user


def _get_current_user_or_agent_dep():
    """延迟导入 get_current_user_or_agent 以避免循环依赖。"""
    from app.core.security import get_current_user_or_agent
    return get_current_user_or_agent


async def get_current_org(
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    """获取当前用户所在组织，返回 (user, organization) 元组。

    CE: 通过 SingleOrgProvider 自动解析默认组织
    EE: 通过 MultiOrgProvider 使用 user.current_org_id
    """
    from app.services.org.factory import get_org_provider

    provider = get_org_provider()
    org = await provider.resolve_org_for_user(user, db)

    if org is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": 40010,
                "message_key": "errors.org.user_has_no_org",
                "message": "用户未加入任何组织",
            },
        )
    return user, org


async def get_current_org_or_agent(
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    """与 get_current_org 相同逻辑，但同时接受 JWT 和 proxy_token（AI 员工）认证。"""
    from app.services.org.factory import get_org_provider

    provider = get_org_provider()
    org = await provider.resolve_org_for_user(user, db)

    if org is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": 40010,
                "message_key": "errors.org.user_has_no_org",
                "message": "用户未加入任何组织",
            },
        )
    return user, org


async def require_super_admin_dep(
    user=Depends(_get_current_user_dep()),
):
    """仅平台超管可访问，返回 user。"""
    if not user.is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": 40310,
                "message_key": "errors.org.super_admin_required",
                "message": "仅限平台管理员操作",
            },
        )
    return user


async def require_org_admin(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    """要求当前用户是所在组织的管理员，返回 (user, org)。"""
    from app.models.org_membership import OrgMembership, OrgRole
    from app.models.organization import Organization

    # 优先从 URL 路径参数中取 org_id，否则用 current_org_id
    path_org_id = request.path_params.get("org_id")
    target_org_id = path_org_id or user.current_org_id

    if user.is_super_admin:
        # 超管天然拥有所有组织的 admin 权限
        if target_org_id:
            result = await db.execute(
                select(Organization).where(
                    Organization.id == target_org_id,
                    Organization.deleted_at.is_(None),
                )
            )
            org = result.scalar_one_or_none()
            if org:
                return user, org
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": 40011,
                "message_key": "errors.org.super_admin_org_required",
                "message": "超管需先选择要操作的组织",
            },
        )

    if target_org_id is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": 40010,
                "message_key": "errors.org.user_has_no_org",
                "message": "用户未加入任何组织",
            },
        )

    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.user_id == user.id,
            OrgMembership.org_id == target_org_id,
            OrgMembership.deleted_at.is_(None),
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None or membership.role != OrgRole.admin:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": 40311,
                "message_key": "errors.org.org_admin_required",
                "message": "仅限组织管理员操作",
            },
        )

    result = await db.execute(
        select(Organization).where(
            Organization.id == target_org_id,
            Organization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()
    return user, org


async def require_org_member(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    """要求当前用户至少是组织成员，返回 (user, org)。"""
    from app.models.org_membership import OrgMembership
    from app.models.organization import Organization

    path_org_id = request.path_params.get("org_id")
    target_org_id = path_org_id or user.current_org_id

    if user.is_super_admin and target_org_id:
        result = await db.execute(
            select(Organization).where(
                Organization.id == target_org_id,
                Organization.deleted_at.is_(None),
            )
        )
        org = result.scalar_one_or_none()
        if org:
            return user, org

    if target_org_id is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": 40010,
                "message_key": "errors.org.user_has_no_org",
                "message": "用户未加入任何组织",
            },
        )

    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.user_id == user.id,
            OrgMembership.org_id == target_org_id,
            OrgMembership.deleted_at.is_(None),
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": 40312,
                "message_key": "errors.org.org_member_required",
                "message": "您不是该组织的成员",
            },
        )

    result = await db.execute(
        select(Organization).where(
            Organization.id == target_org_id,
            Organization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()
    return user, org


# ── 管理平台 RBAC（admin 路由前缀专用） ──────────────────────

def require_org_role(min_role: str):
    """工厂函数：生成要求当前用户在 admin_memberships 中至少拥有 min_role 的依赖。

    用于 admin_router 的 include_router(dependencies=[...])。
    严格要求 AdminMembership，is_super_admin 不再自动放行。
    返回 (user, org)。
    """
    from app.models.org_membership import ADMIN_ROLE_LEVEL

    min_level = ADMIN_ROLE_LEVEL[min_role]

    async def _dependency(
        db: AsyncSession = Depends(get_db),
        user=Depends(_get_current_user_dep()),
    ):
        from app.models.admin_membership import AdminMembership
        from app.models.organization import Organization

        target_org_id = user.current_org_id

        if target_org_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error_code": 40010,
                    "message_key": "errors.org.user_has_no_org",
                    "message": "用户未加入任何组织",
                },
            )

        result = await db.execute(
            select(AdminMembership).where(
                AdminMembership.user_id == user.id,
                AdminMembership.org_id == target_org_id,
                AdminMembership.deleted_at.is_(None),
            )
        )
        admin_membership = result.scalar_one_or_none()

        if admin_membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error_code": 40314,
                    "message_key": "errors.org.no_admin_access",
                    "message": "您没有管理平台访问权限",
                },
            )

        user_level = ADMIN_ROLE_LEVEL.get(admin_membership.role, 0)
        if user_level < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error_code": 40313,
                    "message_key": "errors.org.insufficient_role",
                    "message": f"需要 {min_role} 及以上角色",
                },
            )

        result = await db.execute(
            select(Organization).where(
                Organization.id == target_org_id,
                Organization.deleted_at.is_(None),
            )
        )
        org = result.scalar_one_or_none()
        return user, org

    return _dependency


# ── Edition Dependencies ──────────────────────────────────

def require_ce_edition():
    """仅 CE 版可用，EE 版返回 403。"""
    if feature_gate.edition != "ce":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": 40301,
                "message_key": "errors.settings.ce_only",
                "message": "此功能仅在社区版可用",
            },
        )


# ── Feature Gate Dependencies ─────────────────────────────

def require_feature(feature_id: str):
    """工厂函数：生成要求指定 EE feature 已启用的依赖。

    用法：router = APIRouter(dependencies=[Depends(require_feature("billing"))])
    或在单个端点上：@router.get("/...", dependencies=[Depends(require_feature("billing"))])
    """
    async def _check_feature():
        if not feature_gate.is_enabled(feature_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error_code": 40320,
                    "message_key": "errors.feature.ee_required",
                    "message": f"Feature '{feature_id}' requires Enterprise Edition",
                },
            )
    return _check_feature
