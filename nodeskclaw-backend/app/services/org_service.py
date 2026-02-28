"""Organization CRUD + membership management service."""

import logging
import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.models.base import not_deleted
from app.models.oauth_connection import UserOAuthConnection
from app.models.org_membership import OrgMembership, OrgRole
from app.models.org_oauth_binding import OrgOAuthBinding
from app.models.organization import Organization
from app.models.user import User
from app.schemas.organization import MemberInfo, OAuthOrgSetupRequest, OrgCreate, OrgInfo, OrgUpdate

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,62}[a-z0-9]$")


async def list_orgs(db: AsyncSession) -> list[OrgInfo]:
    """列出所有组织（超管使用），附带成员数。"""
    member_count_sub = (
        select(func.count(OrgMembership.id))
        .where(OrgMembership.org_id == Organization.id, not_deleted(OrgMembership))
        .correlate(Organization)
        .scalar_subquery()
        .label("member_count")
    )
    result = await db.execute(
        select(Organization, member_count_sub)
        .where(not_deleted(Organization))
        .order_by(Organization.created_at.desc())
    )
    orgs = []
    for org, count in result.all():
        info = OrgInfo.model_validate(org)
        info.member_count = count or 0
        orgs.append(info)
    return orgs


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


async def oauth_org_setup(
    user: User, body: OAuthOrgSetupRequest, db: AsyncSession,
) -> OrgInfo:
    """OAuth 登录后首次开通组织。

    根据用户的 OAuthConnection 中的 provider_tenant_id 绑定组织。
    并发安全：(provider, provider_tenant_id) 有 unique 约束，
    两个同企业用户同时提交时，后者因 IntegrityError 自动降级为加入已创建的组织。
    """
    from sqlalchemy.exc import IntegrityError

    conn_result = await db.execute(
        select(UserOAuthConnection).where(
            UserOAuthConnection.user_id == user.id,
            UserOAuthConnection.provider == body.provider,
            UserOAuthConnection.deleted_at.is_(None),
        )
    )
    connection = conn_result.scalar_one_or_none()
    if connection is None or not connection.provider_tenant_id:
        raise BadRequestError(
            f"当前用户没有关联 {body.provider} 租户，无法开通组织",
            message_key="errors.org.missing_tenant_key",
        )
    tenant_id = connection.provider_tenant_id

    existing_binding = await db.execute(
        select(OrgOAuthBinding).where(
            OrgOAuthBinding.provider == body.provider,
            OrgOAuthBinding.provider_tenant_id == tenant_id,
            OrgOAuthBinding.deleted_at.is_(None),
        )
    )
    binding = existing_binding.scalar_one_or_none()
    if binding is not None:
        org_result = await db.execute(
            select(Organization).where(Organization.id == binding.org_id, not_deleted(Organization))
        )
        org = org_result.scalar_one()
        await _ensure_membership(user, org, OrgRole.member, body.job_title, db)
        return OrgInfo.model_validate(org)

    if not _SLUG_RE.match(body.slug):
        raise BadRequestError("slug 格式不合法（小写字母/数字/短横线，3-64 字符）")

    slug_exists = await db.execute(
        select(Organization).where(Organization.slug == body.slug, not_deleted(Organization))
    )
    if slug_exists.scalar_one_or_none():
        raise ConflictError(f"slug '{body.slug}' 已被使用")

    org = Organization(name=body.name, slug=body.slug)
    db.add(org)
    await db.flush()

    new_binding = OrgOAuthBinding(
        org_id=org.id, provider=body.provider, provider_tenant_id=tenant_id,
    )
    db.add(new_binding)

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        result = await db.execute(
            select(OrgOAuthBinding).where(
                OrgOAuthBinding.provider == body.provider,
                OrgOAuthBinding.provider_tenant_id == tenant_id,
                OrgOAuthBinding.deleted_at.is_(None),
            )
        )
        existing = result.scalar_one()
        org_result = await db.execute(
            select(Organization).where(Organization.id == existing.org_id, not_deleted(Organization))
        )
        org = org_result.scalar_one()
        await _ensure_membership(user, org, OrgRole.member, body.job_title, db)
        return OrgInfo.model_validate(org)

    membership = OrgMembership(
        user_id=user.id, org_id=org.id, role=OrgRole.admin, job_title=body.job_title,
    )
    db.add(membership)
    user.current_org_id = org.id

    await db.commit()
    await db.refresh(org)
    logger.info(
        "OAuth 开通组织: %s (slug=%s, provider=%s, tenant=%s) by user %s",
        org.name, org.slug, body.provider, tenant_id, user.id,
    )
    return OrgInfo.model_validate(org)


async def feishu_org_setup(
    user: User, body: OAuthOrgSetupRequest, db: AsyncSession,
) -> OrgInfo:
    """向后兼容别名。"""
    if not body.provider:
        body.provider = "feishu"
    return await oauth_org_setup(user, body, db)


async def _ensure_membership(
    user: User, org: Organization, role: str, job_title: str | None, db: AsyncSession,
) -> None:
    """确保用户是组织成员，已存在则跳过。"""
    exists = await db.execute(
        select(OrgMembership).where(
            OrgMembership.user_id == user.id,
            OrgMembership.org_id == org.id,
            not_deleted(OrgMembership),
        )
    )
    if exists.scalar_one_or_none() is None:
        db.add(OrgMembership(
            user_id=user.id, org_id=org.id, role=role, job_title=job_title,
        ))
    user.current_org_id = org.id
    await db.commit()
    await db.refresh(user)


async def update_org(org_id: str, body: OrgUpdate, db: AsyncSession) -> OrgInfo:
    """更新组织信息。"""
    org = await get_org(org_id, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(org, field, value)
    await db.commit()
    await db.refresh(org)
    return OrgInfo.model_validate(org)


async def delete_org(org_id: str, db: AsyncSession) -> None:
    """软删除组织（仍有运行中实例时禁止删除）。"""
    from app.models.instance import Instance, InstanceStatus

    org = await get_org(org_id, db)

    active_statuses = {
        InstanceStatus.running, InstanceStatus.creating,
        InstanceStatus.deploying, InstanceStatus.pending, InstanceStatus.updating,
    }
    result = await db.execute(
        select(func.count()).select_from(Instance).where(
            Instance.org_id == org_id,
            Instance.deleted_at.is_(None),
            Instance.status.in_(active_statuses),
        )
    )
    count = result.scalar() or 0
    if count > 0:
        raise ForbiddenError(f"该组织下仍有 {count} 个活跃实例，请先删除或停止所有实例")

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
            user_avatar_url=user.avatar_url,
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
        user_avatar_url=user.avatar_url,
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
        user_avatar_url=user.avatar_url,
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
    """列出用户所属的所有组织，附带成员数。"""
    if user.is_super_admin:
        return await list_orgs(db)

    member_count_sub = (
        select(func.count(OrgMembership.id))
        .where(OrgMembership.org_id == Organization.id, not_deleted(OrgMembership))
        .correlate(Organization)
        .scalar_subquery()
        .label("member_count")
    )
    result = await db.execute(
        select(Organization, member_count_sub)
        .join(OrgMembership, OrgMembership.org_id == Organization.id)
        .where(
            OrgMembership.user_id == user.id,
            not_deleted(OrgMembership),
            not_deleted(Organization),
        )
        .order_by(Organization.created_at.desc())
    )
    orgs = []
    for org, count in result.all():
        info = OrgInfo.model_validate(org)
        info.member_count = count or 0
        orgs.append(info)
    return orgs
