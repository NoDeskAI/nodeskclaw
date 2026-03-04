"""Workspace member service: permission checks, member search."""

import logging

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.base import not_deleted
from app.models.org_membership import OrgMembership, OrgRole
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import (
    WORKSPACE_PERMISSIONS,
    WorkspaceMember,
)

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


async def _get_workspace_org_id(workspace_id: str, db: AsyncSession) -> str | None:
    result = await db.execute(
        select(Workspace.org_id).where(
            Workspace.id == workspace_id,
            not_deleted(Workspace),
        )
    )
    return result.scalar_one_or_none()


async def check_workspace_access(
    workspace_id: str,
    user: User,
    required_permission: str,
    db: AsyncSession,
) -> WorkspaceMember | None:
    """Check that *user* has *required_permission* on the workspace.

    Returns the WorkspaceMember row, or None when bypassed by org-admin.
    Raises ForbiddenError / NotFoundError.
    """
    org_id = await _get_workspace_org_id(workspace_id, db)
    if org_id is None:
        raise NotFoundError("办公室不存在", "errors.workspace.not_found")

    org_role = await _get_org_role(user.id, org_id, db)
    if org_role == OrgRole.admin:
        return None

    member = (await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
            not_deleted(WorkspaceMember),
        )
    )).scalar_one_or_none()

    if not member:
        raise ForbiddenError("您不是该办公室的成员", "errors.workspace.no_access")

    if member.is_admin:
        return member

    perms = member.permissions or []
    if required_permission not in perms:
        raise ForbiddenError("权限不足", "errors.workspace.insufficient_permission")

    return member


async def check_workspace_member(
    workspace_id: str,
    user: User,
    db: AsyncSession,
) -> WorkspaceMember | None:
    """Check that *user* is a member of the workspace (read-only access).

    Returns the WorkspaceMember row, or None when bypassed by org-admin.
    Raises ForbiddenError.
    """
    org_id = await _get_workspace_org_id(workspace_id, db)
    if org_id is None:
        raise NotFoundError("办公室不存在", "errors.workspace.not_found")

    org_role = await _get_org_role(user.id, org_id, db)
    if org_role == OrgRole.admin:
        return None

    member = (await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
            not_deleted(WorkspaceMember),
        )
    )).scalar_one_or_none()

    if not member:
        raise ForbiddenError("您不是该办公室的成员", "errors.workspace.no_access")

    return member


async def get_my_permissions(
    workspace_id: str,
    user: User,
    db: AsyncSession,
) -> dict:
    """Return the current user's permissions and admin status for the workspace."""
    org_id = await _get_workspace_org_id(workspace_id, db)
    if org_id is None:
        raise NotFoundError("办公室不存在", "errors.workspace.not_found")

    org_role = await _get_org_role(user.id, org_id, db)
    if org_role == OrgRole.admin:
        return {
            "is_admin": True,
            "is_org_admin": True,
            "permissions": list(WORKSPACE_PERMISSIONS),
        }

    member = (await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
            not_deleted(WorkspaceMember),
        )
    )).scalar_one_or_none()

    if not member:
        raise ForbiddenError("您不是该办公室的成员", "errors.workspace.no_access")

    if member.is_admin:
        return {
            "is_admin": True,
            "is_org_admin": False,
            "permissions": list(WORKSPACE_PERMISSIONS),
        }

    return {
        "is_admin": False,
        "is_org_admin": False,
        "permissions": member.permissions or [],
    }


async def search_org_users(
    workspace_id: str,
    org_id: str,
    query_str: str,
    db: AsyncSession,
) -> list[dict]:
    """Search org members who are NOT already workspace members."""
    existing_member_ids = (
        select(WorkspaceMember.user_id)
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            not_deleted(WorkspaceMember),
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
