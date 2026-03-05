"""OrgProvider 抽象接口 — CE/EE 组织模式差异。

CE (SingleOrgProvider):
  单组织模式。系统只有一个默认组织，所有用户自动归属。
  不需要组织切换、多组织 CRUD。

EE (MultiOrgProvider):
  多组织模式。用户可属于多个组织，通过 current_org_id 切换上下文。
  支持组织创建、OAuth 开通、成员管理。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.models.user import User


class OrgProvider(ABC):

    @abstractmethod
    async def resolve_org_for_user(
        self, user: User, db: AsyncSession,
    ) -> Any:
        """解析用户当前所属组织。

        CE: 返回默认组织（自动创建如不存在）
        EE: 通过 user.current_org_id 查找

        Returns:
            Organization 实例，或 None（EE 模式下用户可能未加入任何组织）
        """

    @abstractmethod
    async def ensure_user_has_org(
        self, user: User, db: AsyncSession,
    ) -> None:
        """确保用户有可用的组织上下文。

        CE: 自动将用户加入默认组织并设置 current_org_id
        EE: 不做自动分配（用户需被邀请或通过 OAuth 加入）
        """

    @abstractmethod
    def is_multi_org(self) -> bool:
        """是否支持多组织。

        CE: False
        EE: True
        """
