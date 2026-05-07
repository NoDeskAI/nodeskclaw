"""Workspace access helpers for user and runtime agent actors."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace_agent import WorkspaceAgent
from app.services import workspace_member_service as wm_service


def get_current_agent_id() -> str | None:
    from app.core.security import get_auth_actor

    actor = get_auth_actor()
    if actor is None or actor.actor_type != "agent":
        return None
    return actor.actor_id


async def require_agent_in_workspace(
    workspace_id: str,
    instance_id: str,
    db: AsyncSession,
) -> None:
    result = await db.execute(
        select(WorkspaceAgent.id)
        .where(
            WorkspaceAgent.workspace_id == workspace_id,
            WorkspaceAgent.instance_id == instance_id,
            WorkspaceAgent.deleted_at.is_(None),
        )
        .limit(1)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": 40306,
                "message_key": "errors.workspace.agent_not_in_workspace",
                "message": "AI 员工不在该办公室中",
            },
        )


async def require_workspace_actor_member(
    workspace_id: str,
    user,
    db: AsyncSession,
) -> str | None:
    agent_id = get_current_agent_id()
    if agent_id is not None:
        await require_agent_in_workspace(workspace_id, agent_id, db)
        return agent_id
    await wm_service.check_workspace_member(workspace_id, user, db)
    return None


async def require_workspace_actor_access(
    workspace_id: str,
    user,
    permission: str,
    db: AsyncSession,
) -> str | None:
    agent_id = get_current_agent_id()
    if agent_id is not None:
        await require_agent_in_workspace(workspace_id, agent_id, db)
        return agent_id
    await wm_service.check_workspace_access(workspace_id, user, permission, db)
    return None
