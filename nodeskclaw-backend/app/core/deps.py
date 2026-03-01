"""FastAPI dependency injection – DB session + RBAC helpers."""

from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"ssl": False},  # 火山云 RDS 内网不需要 SSL
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


async def get_current_org(
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    """获取当前用户所在组织，返回 (user, organization) 元组。"""
    from app.models.organization import Organization

    if user.current_org_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": 40010,
                "message_key": "errors.org.user_has_no_org",
                "message": "用户未加入任何组织",
            },
        )

    result = await db.execute(
        select(Organization).where(
            Organization.id == user.current_org_id,
            Organization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": 40410,
                "message_key": "errors.org.current_org_not_found",
                "message": "当前组织不存在或已删除",
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
    """工厂函数：生成要求当前用户在其组织中至少拥有 min_role 的依赖。

    用于 admin_router 的 include_router(dependencies=[...])，
    super_admin 自动放行。返回 (user, org)。
    """
    from app.models.org_membership import ROLE_LEVEL, OrgRole

    min_level = ROLE_LEVEL[OrgRole(min_role)]

    async def _dependency(
        db: AsyncSession = Depends(get_db),
        user=Depends(_get_current_user_dep()),
    ):
        from app.models.org_membership import OrgMembership
        from app.models.organization import Organization

        target_org_id = user.current_org_id

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
                status_code=status.HTTP_400_BAD_REQUEST,
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
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error_code": 40312,
                    "message_key": "errors.org.org_member_required",
                    "message": "您不是该组织的成员",
                },
            )

        user_level = ROLE_LEVEL.get(OrgRole(membership.role), 0)
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
