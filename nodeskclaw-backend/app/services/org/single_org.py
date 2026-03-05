"""SingleOrgProvider — CE 单组织模式。

系统维护一个唯一的默认组织，所有用户自动归属。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.org.provider import OrgProvider

if TYPE_CHECKING:
    from app.models.user import User

logger = logging.getLogger(__name__)

DEFAULT_ORG_SLUG = "default"
DEFAULT_ORG_NAME = "Default Organization"


class SingleOrgProvider(OrgProvider):

    async def resolve_org_for_user(
        self, user: User, db: AsyncSession,
    ) -> Any:
        from app.models.organization import Organization

        if user.current_org_id:
            result = await db.execute(
                select(Organization).where(
                    Organization.id == user.current_org_id,
                    Organization.deleted_at.is_(None),
                )
            )
            org = result.scalar_one_or_none()
            if org:
                return org

        return await self._get_or_create_default(db)

    async def ensure_user_has_org(
        self, user: User, db: AsyncSession,
    ) -> None:
        org = await self._get_or_create_default(db)

        from app.models.base import not_deleted
        from app.models.org_membership import OrgMembership, OrgRole

        result = await db.execute(
            select(OrgMembership).where(
                OrgMembership.user_id == user.id,
                OrgMembership.org_id == org.id,
                not_deleted(OrgMembership),
            )
        )
        if not result.scalar_one_or_none():
            db.add(OrgMembership(
                user_id=user.id, org_id=org.id, role=OrgRole.admin,
            ))
            logger.info("CE 模式：自动将用户 %s 加入默认组织", user.id)

        user.current_org_id = org.id
        await db.commit()

    def is_multi_org(self) -> bool:
        return False

    async def _get_or_create_default(self, db: AsyncSession) -> Any:
        from app.models.organization import Organization

        result = await db.execute(
            select(Organization).where(
                Organization.slug == DEFAULT_ORG_SLUG,
                Organization.deleted_at.is_(None),
            )
        )
        org = result.scalar_one_or_none()
        if org:
            return org

        org = Organization(
            name=DEFAULT_ORG_NAME,
            slug=DEFAULT_ORG_SLUG,
            is_active=True,
        )
        db.add(org)
        await db.commit()
        await db.refresh(org)
        logger.info("CE 模式：自动创建默认组织 id=%s", org.id)
        return org
