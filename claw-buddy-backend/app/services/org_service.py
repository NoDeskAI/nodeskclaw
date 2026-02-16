"""Organization CRUD + membership management service."""

import logging
import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.models.base import not_deleted
from app.models.org_membership import OrgMembership, OrgRole
from app.models.organization import Organization
from app.models.user import User
from app.schemas.organization import MemberInfo, OrgCreate, OrgInfo, OrgUpdate

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,62}[a-z0-9]$")


async def list_orgs(db: AsyncSession) -> list[OrgInfo]:
    """列出所有组织（超管使用）。"""
    result = await db.execute(
        select(Organization).where(not_deleted(Organization)).order_by(Organization.created_at.desc())
    )
    return [OrgInfo.model_validate(o) for o in result.scalars().all()]


async def get_org(org_id: str, db: AsyncSession) -> Organization:
    """获取组织详情，不存在抛 404。"""
    result = await db.execute(
        select(Organization).where(Organization.id == org_id, not_deleted(Organization))
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise NotFoundError("组织不存在")
    return org


async def create_org(body: OrgCreate, creator: User, db: AsyncSession) -> OrgInfo:
    """创建组织，并把创建者设为 org_admin。"""
    if not _SLUG_RE.match(body.slug):
        raise BadRequestError("slug 格式不合法（小写字母/数字/短横线，3-64 字符）")

    # 唯一性检查
    exists = await db.execute(
        select(Organization).where(Organization.slug == body.slug, not_deleted(Organization))
    )
    if exists.scalar_one_or_none():
        raise ConflictError(f"slug '{body.slug}' 已被使用")

    org = Organization(name=body.name, slug=body.slug, plan=body.plan)
    db.add(org)
    await db.flush()

    # 创建者自动成为组织管理员
    membership = OrgMembership(user_id=creator.id, org_id=org.id, role=OrgRole.admin)
    db.add(membership)

    # 如果创建者还没有当前组织，自动切换
    if creator.current_org_id is None:
        creator.current_org_id = org.id

    await db.commit()
    await db.refresh(org)
    logger.info("创建组织: %s (slug=%s) by user %s", org.name, org.slug, creator.id)
    return OrgInfo.model_validate(org)


async def update_org(org_id: str, body: OrgUpdate, db: AsyncSession) -> OrgInfo:
    """更新组织信息。"""
    org = await get_org(org_id, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(org, field, value)
    await db.commit()
    await db.refresh(org)
    return OrgInfo.model_validate(org)


async def delete_org(org_id: str, db: AsyncSession) -> None:
    """软删除组织。"""
    org = await get_org(org_id, db)
    if org.slug == "default":
        raise ForbiddenError("默认组织不可删除")
    org.soft_delete()
    await db.commit()


# ── 成员管理 ─────────────────────────────────────────────

async def list_members(org_id: str, db: AsyncSession) -> list[MemberInfo]:
    """列出组织成员。"""
    result = await db.execute(
        select(OrgMembership, User)
        .join(User, OrgMembership.user_id == User.id)
        .where(OrgMembership.org_id == org_id, not_deleted(OrgMembership))
    )
    members = []
    for membership, user in result.all():
        members.append(MemberInfo(
            id=membership.id,
            user_id=membership.user_id,
            org_id=membership.org_id,
            role=membership.role,
            user_name=user.name,
            user_email=user.email,
            created_at=membership.created_at,
        ))
    return members


async def add_member(org_id: str, user_id: str, role: str, db: AsyncSession) -> MemberInfo:
    """添加成员到组织。"""
    # 检查用户存在
    user_result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        raise NotFoundError("用户不存在")

    # 检查是否已是成员
    exists = await db.execute(
        select(OrgMembership).where(
            OrgMembership.user_id == user_id,
            OrgMembership.org_id == org_id,
            not_deleted(OrgMembership),
        )
    )
    if exists.scalar_one_or_none():
        raise ConflictError("该用户已是组织成员")

    membership = OrgMembership(user_id=user_id, org_id=org_id, role=role)
    db.add(membership)

    # 如果用户还没有当前组织，自动设置
    if user.current_org_id is None:
        user.current_org_id = org_id

    await db.commit()
    await db.refresh(membership)

    return MemberInfo(
        id=membership.id,
        user_id=membership.user_id,
        org_id=membership.org_id,
        role=membership.role,
        user_name=user.name,
        user_email=user.email,
        created_at=membership.created_at,
    )


async def update_member_role(org_id: str, membership_id: str, role: str, db: AsyncSession) -> MemberInfo:
    """修改成员角色。"""
    result = await db.execute(
        select(OrgMembership, User)
        .join(User, OrgMembership.user_id == User.id)
        .where(
            OrgMembership.id == membership_id,
            OrgMembership.org_id == org_id,
            not_deleted(OrgMembership),
        )
    )
    row = result.first()
    if row is None:
        raise NotFoundError("成员记录不存在")

    membership, user = row
    membership.role = role
    await db.commit()

    return MemberInfo(
        id=membership.id,
        user_id=membership.user_id,
        org_id=membership.org_id,
        role=membership.role,
        user_name=user.name,
        user_email=user.email,
        created_at=membership.created_at,
    )


async def remove_member(org_id: str, membership_id: str, db: AsyncSession) -> None:
    """移除成员（软删除）。"""
    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.id == membership_id,
            OrgMembership.org_id == org_id,
            not_deleted(OrgMembership),
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise NotFoundError("成员记录不存在")

    # 检查是否是最后一个 admin
    admin_count = await db.execute(
        select(func.count()).where(
            OrgMembership.org_id == org_id,
            OrgMembership.role == OrgRole.admin,
            not_deleted(OrgMembership),
        )
    )
    if membership.role == OrgRole.admin and admin_count.scalar_one() <= 1:
        raise ForbiddenError("组织至少需要一个管理员")

    membership.soft_delete()
    await db.commit()


async def switch_org(user: User, org_id: str, db: AsyncSession) -> OrgInfo:
    """切换用户当前组织。"""
    # 检查是否是该组织的成员（超管可切换任意组织）
    if not user.is_super_admin:
        result = await db.execute(
            select(OrgMembership).where(
                OrgMembership.user_id == user.id,
                OrgMembership.org_id == org_id,
                not_deleted(OrgMembership),
            )
        )
        if result.scalar_one_or_none() is None:
            raise ForbiddenError("您不是该组织的成员")

    org = await get_org(org_id, db)
    user.current_org_id = org_id
    await db.commit()
    return OrgInfo.model_validate(org)


async def list_user_orgs(user: User, db: AsyncSession) -> list[OrgInfo]:
    """列出用户所属的所有组织。"""
    if user.is_super_admin:
        return await list_orgs(db)

    result = await db.execute(
        select(Organization)
        .join(OrgMembership, OrgMembership.org_id == Organization.id)
        .where(
            OrgMembership.user_id == user.id,
            not_deleted(OrgMembership),
            not_deleted(Organization),
        )
        .order_by(Organization.created_at.desc())
    )
    return [OrgInfo.model_validate(o) for o in result.scalars().all()]
