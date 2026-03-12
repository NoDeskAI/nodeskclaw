"""Member management Hook + Role Provider — CE defaults, EE overrides.

MemberHookProvider: blocking hooks (before_invite can abort via exception).
Unlike app.core.hooks (fire-and-forget audit events that swallow exceptions),
before_invite MUST propagate exceptions to abort the invitation flow.

RoleProvider: pluggable role list for invitation/role-change UIs.
CE returns [admin, member]; EE can extend with custom roles.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ── MemberHookProvider ────────────────────────────────────


@runtime_checkable
class MemberHookProvider(Protocol):

    async def before_invite(self, org_id: str, emails: list[str], role: str) -> None:
        """Called before creating invitations. Raise HTTPException to abort."""
        ...

    async def on_member_joined(self, org_id: str, user_id: str, role: str) -> None:
        """Called after a user joins an organization."""
        ...

    async def on_member_removed(self, org_id: str, user_id: str) -> None:
        """Called after a member is removed from an organization."""
        ...


class NoopMemberHookProvider:
    """CE default: all hooks are no-ops."""

    async def before_invite(self, org_id: str, emails: list[str], role: str) -> None:
        pass

    async def on_member_joined(self, org_id: str, user_id: str, role: str) -> None:
        pass

    async def on_member_removed(self, org_id: str, user_id: str) -> None:
        pass


_member_hook: MemberHookProvider = NoopMemberHookProvider()


def register_member_hook(provider: MemberHookProvider) -> None:
    global _member_hook
    _member_hook = provider
    logger.info("MemberHookProvider registered: %s", type(provider).__name__)


def get_member_hook() -> MemberHookProvider:
    return _member_hook


# ── RoleProvider ──────────────────────────────────────────


@runtime_checkable
class RoleProvider(Protocol):

    def get_roles(self, org_id: str) -> list[dict]:
        """Return list of {"id": ..., "name_key": ...} role definitions."""
        ...


class DefaultRoleProvider:
    """CE default: admin + member."""

    def get_roles(self, org_id: str) -> list[dict]:
        return [
            {"id": "admin", "name_key": "orgMembers.roleAdmin"},
            {"id": "member", "name_key": "orgMembers.roleMember"},
        ]


_role_provider: RoleProvider = DefaultRoleProvider()


def register_role_provider(provider: RoleProvider) -> None:
    global _role_provider
    _role_provider = provider
    logger.info("RoleProvider registered: %s", type(provider).__name__)


def get_role_provider() -> RoleProvider:
    return _role_provider
