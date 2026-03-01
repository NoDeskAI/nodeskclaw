"""Instance member service: permission checks, list filtering, member CRUD."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.models.base import not_deleted
from app.models.instance import Instance
from app.models.instance_member import INSTANCE_ROLE_LEVEL, InstanceMember, InstanceRole
from app.models.org_membership import OrgMembership, OrgRole
from app.models.user import User

logger = logging.getLogger(__name__)


async def _get_org_role(user_id: str, org_id: str, db: AsyncSession) -> str | None:
    result = await db.execute(
        select(OrgMembership.role).where(
            OrgMembership.user_id == user_id,
            OrgMembership.org_id == org_id,
            not_deleted(OrgMembership),
        )
    )
    return result.scalar_one_or_none()


async def check_instance_access(
    instance_id: str,
    user: User,
    min_role: InstanceRole,
    db: AsyncSession,
) -> InstanceMember | None:
    """Check that *user* has at least *min_role* on the instance.

    Returns the InstanceMember row when permission comes from membership,
    or None when bypassed by org-admin status.
    Raises ForbiddenError / NotFoundError.
    """
    instance = (await db.execute(
        select(Instance).where(Instance.id == instance_id, not_deleted(Instance))
    )).scalar_one_or_none()
    if not instance:
        raise NotFoundError("实例不存在", "errors.instance.not_found")

    if instance.org_id:
        org_role = await _get_org_role(user.id, instance.org_id, db)
        if org_role == OrgRole.admin:
            return None

    member = (await db.execute(
        select(InstanceMember).where(
            InstanceMember.instance_id == instance_id,
            InstanceMember.user_id == user.id,
            not_deleted(InstanceMember),
        )
    )).scalar_one_or_none()

    if not member:
        raise ForbiddenError("您没有该实例的访问权限", "errors.instance.no_access")

    if INSTANCE_ROLE_LEVEL.get(member.role, 0) < INSTANCE_ROLE_LEVEL[min_role]:
        raise ForbiddenError("权限不足", "errors.instance.insufficient_role")

    return member


async def get_user_instance_role(
    instance_id: str, user: User, db: AsyncSession
) -> str | None:
    """Return the effective role string for user on instance, or None."""
    instance = (await db.execute(
        select(Instance).where(Instance.id == instance_id, not_deleted(Instance))
    )).scalar_one_or_none()
    if not instance:
        return None

    if instance.org_id:
        org_role = await _get_org_role(user.id, instance.org_id, db)
        if org_role == OrgRole.admin:
            return InstanceRole.admin

    member = (await db.execute(
        select(InstanceMember).where(
            InstanceMember.instance_id == instance_id,
            InstanceMember.user_id == user.id,
            not_deleted(InstanceMember),
        )
    )).scalar_one_or_none()
    return member.role if member else None


def apply_accessible_filter(query, user_id: str, org_id: str | None, db: AsyncSession):
    """Add a WHERE clause so only instances the user can access are returned.

    Org admins see everything in the org; others only see instances they are
    a member of.
    """
    org_admin_subq = (
        select(OrgMembership.user_id)
        .where(
            OrgMembership.user_id == user_id,
            OrgMembership.role == OrgRole.admin,
            not_deleted(OrgMembership),
            *([OrgMembership.org_id == org_id] if org_id else []),
        )
        .exists()
    )

    member_subq = (
        select(InstanceMember.instance_id)
        .where(
            InstanceMember.user_id == user_id,
            not_deleted(InstanceMember),
        )
    )

    from sqlalchemy import case, or_
    query = query.where(
        or_(
            org_admin_subq,
            Instance.id.in_(member_subq),
        )
    )
    return query


async def list_members(
    instance_id: str, db: AsyncSession
) -> list[dict]:
    result = await db.execute(
        select(InstanceMember, User)
        .join(User, InstanceMember.user_id == User.id)
        .where(
            InstanceMember.instance_id == instance_id,
            not_deleted(InstanceMember),
            not_deleted(User),
        )
        .order_by(InstanceMember.created_at.asc())
    )
    return [
        {
            "id": m.id,
            "instance_id": m.instance_id,
            "user_id": m.user_id,
            "role": m.role,
            "user_name": u.name,
            "user_email": u.email,
            "user_avatar_url": u.avatar_url,
            "created_at": m.created_at,
        }
        for m, u in result.all()
    ]


async def add_member(
    instance_id: str,
    user_id: str,
    role: str,
    db: AsyncSession,
) -> dict:
    if role not in INSTANCE_ROLE_LEVEL:
        raise BadRequestError(f"无效的角色: {role}", "errors.instance.invalid_role")

    instance = (await db.execute(
        select(Instance).where(Instance.id == instance_id, not_deleted(Instance))
    )).scalar_one_or_none()
    if not instance:
        raise NotFoundError("实例不存在", "errors.instance.not_found")

    target_user = (await db.execute(
        select(User).where(User.id == user_id, not_deleted(User))
    )).scalar_one_or_none()
    if not target_user:
        raise NotFoundError("用户不存在", "errors.instance.user_not_found")

    if instance.org_id:
        org_membership = (await db.execute(
            select(OrgMembership).where(
                OrgMembership.user_id == user_id,
                OrgMembership.org_id == instance.org_id,
                not_deleted(OrgMembership),
            )
        )).scalar_one_or_none()
        if not org_membership:
            raise BadRequestError(
                "目标用户不属于该实例所在的组织",
                "errors.instance.user_not_in_org",
            )

    existing = (await db.execute(
        select(InstanceMember).where(
            InstanceMember.instance_id == instance_id,
            InstanceMember.user_id == user_id,
            not_deleted(InstanceMember),
        )
    )).scalar_one_or_none()
    if existing:
        raise ConflictError("该用户已是实例成员", "errors.instance.member_already_exists")

    member = InstanceMember(
        instance_id=instance_id,
        user_id=user_id,
        role=role,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)

    return {
        "id": member.id,
        "instance_id": member.instance_id,
        "user_id": member.user_id,
        "role": member.role,
        "user_name": target_user.name,
        "user_email": target_user.email,
        "user_avatar_url": target_user.avatar_url,
        "created_at": member.created_at,
    }


async def update_member(
    instance_id: str,
    member_id: str,
    role: str,
    db: AsyncSession,
) -> dict:
    if role not in INSTANCE_ROLE_LEVEL:
        raise BadRequestError(f"无效的角色: {role}", "errors.instance.invalid_role")

    member = (await db.execute(
        select(InstanceMember).where(
            InstanceMember.id == member_id,
            InstanceMember.instance_id == instance_id,
            not_deleted(InstanceMember),
        )
    )).scalar_one_or_none()
    if not member:
        raise NotFoundError("成员不存在", "errors.instance.member_not_found")

    member.role = role
    await db.commit()
    await db.refresh(member)

    user = (await db.execute(select(User).where(User.id == member.user_id))).scalar_one()
    return {
        "id": member.id,
        "instance_id": member.instance_id,
        "user_id": member.user_id,
        "role": member.role,
        "user_name": user.name,
        "user_email": user.email,
        "user_avatar_url": user.avatar_url,
        "created_at": member.created_at,
    }


async def remove_member(
    instance_id: str,
    member_id: str,
    current_user_id: str,
    db: AsyncSession,
) -> None:
    member = (await db.execute(
        select(InstanceMember).where(
            InstanceMember.id == member_id,
            InstanceMember.instance_id == instance_id,
            not_deleted(InstanceMember),
        )
    )).scalar_one_or_none()
    if not member:
        raise NotFoundError("成员不存在", "errors.instance.member_not_found")

    if member.user_id == current_user_id:
        raise BadRequestError("不能移除自己", "errors.instance.cannot_remove_self")

    member.soft_delete()
    await db.commit()


async def search_org_users(
    instance_id: str,
    org_id: str,
    query_str: str,
    db: AsyncSession,
) -> list[dict]:
    """Search org members who are NOT already instance members."""
    existing_member_ids = (
        select(InstanceMember.user_id)
        .where(
            InstanceMember.instance_id == instance_id,
            not_deleted(InstanceMember),
        )
    )

    stmt = (
        select(User)
        .join(OrgMembership, OrgMembership.user_id == User.id)
        .where(
            OrgMembership.org_id == org_id,
            not_deleted(OrgMembership),
            not_deleted(User),
            User.id.notin_(existing_member_ids),
        )
    )

    if query_str and query_str.strip():
        pattern = f"%{query_str.strip()}%"
        from sqlalchemy import or_
        stmt = stmt.where(or_(User.name.ilike(pattern), User.email.ilike(pattern)))

    stmt = stmt.limit(20)
    result = await db.execute(stmt)
    return [
        {
            "user_id": u.id,
            "name": u.name,
            "email": u.email,
            "avatar_url": u.avatar_url,
        }
        for u in result.scalars().all()
    ]
