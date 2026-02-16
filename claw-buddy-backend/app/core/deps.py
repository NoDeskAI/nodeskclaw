"""FastAPI dependency injection – DB session + RBAC helpers."""

from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, status
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
            detail="用户未加入任何组织",
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
            detail="当前组织不存在或已删除",
        )
    return user, org


async def require_super_admin_dep(
    user=Depends(_get_current_user_dep()),
):
    """仅平台超管可访问，返回 user。"""
    if not user.is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅限平台管理员操作",
        )
    return user


async def require_org_admin(
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    """要求当前用户是所在组织的管理员，返回 (user, org)。"""
    from app.models.org_membership import OrgMembership, OrgRole
    from app.models.organization import Organization

    if user.is_super_admin:
        # 超管天然拥有所有组织的 admin 权限
        if user.current_org_id:
            result = await db.execute(
                select(Organization).where(
                    Organization.id == user.current_org_id,
                    Organization.deleted_at.is_(None),
                )
            )
            org = result.scalar_one_or_none()
            if org:
                return user, org
        raise HTTPException(status_code=400, detail="超管需先选择要操作的组织")

    if user.current_org_id is None:
        raise HTTPException(status_code=400, detail="用户未加入任何组织")

    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.user_id == user.id,
            OrgMembership.org_id == user.current_org_id,
            OrgMembership.deleted_at.is_(None),
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None or membership.role != OrgRole.admin:
        raise HTTPException(status_code=403, detail="仅限组织管理员操作")

    result = await db.execute(
        select(Organization).where(
            Organization.id == user.current_org_id,
            Organization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()
    return user, org


async def require_org_member(
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    """要求当前用户至少是组织成员，返回 (user, org)。"""
    from app.models.org_membership import OrgMembership
    from app.models.organization import Organization

    if user.is_super_admin and user.current_org_id:
        result = await db.execute(
            select(Organization).where(
                Organization.id == user.current_org_id,
                Organization.deleted_at.is_(None),
            )
        )
        org = result.scalar_one_or_none()
        if org:
            return user, org

    if user.current_org_id is None:
        raise HTTPException(status_code=400, detail="用户未加入任何组织")

    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.user_id == user.id,
            OrgMembership.org_id == user.current_org_id,
            OrgMembership.deleted_at.is_(None),
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=403, detail="您不是该组织的成员")

    result = await db.execute(
        select(Organization).where(
            Organization.id == user.current_org_id,
            Organization.deleted_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()
    return user, org
