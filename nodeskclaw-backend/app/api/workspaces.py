"""Workspace API — CRUD, Agent management, Blackboard, Context, Members, Chat, SSE."""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Coroutine

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import async_session_factory, get_current_org, get_db
from app.models.instance import Instance
from app.schemas.workspace import (
    AddAgentRequest,
    BlackboardSectionPatch,
    BlackboardUpdate,
    ChatMessageRequest,
    UpdateAgentRequest,
    WorkspaceChatRequest,
    WorkspaceCreate,
    WorkspaceMemberAdd,
    WorkspaceMemberUpdate,
    WorkspaceUpdate,
)
from app.services import workspace_service
from app.services import workspace_message_service as msg_service
from app.services import workspace_member_service as wm_service

logger = logging.getLogger(__name__)
router = APIRouter()

_background_tasks: set[asyncio.Task] = set()


def _fire_task(coro: Coroutine) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def _ok(data=None, message: str = "success"):
    return {"code": 0, "message": message, "data": data}


def _error(status_code: int, error_code: int, message_key: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error_code": error_code,
            "message_key": message_key,
            "message": message,
        },
    )


# ── helpers ──────────────────────────────────────────

def _get_current_user_dep():
    from app.core.security import get_current_user
    return get_current_user


def _get_current_user_from_query_dep():
    from app.core.security import get_current_user_from_query
    return get_current_user_from_query


# ── Workspace CRUD ───────────────────────────────────

@router.post("")
async def create_workspace(
    data: WorkspaceCreate,
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    ws = await workspace_service.create_workspace(db, org.id, user.id, data)
    return _ok(ws.model_dump(mode="json"))


@router.get("")
async def list_workspaces(
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    items = await workspace_service.list_workspaces(db, org.id, user_id=user.id)
    return _ok([i.model_dump(mode="json") for i in items])


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    await wm_service.check_workspace_member(workspace_id, user, db)
    ws = await workspace_service.get_workspace(db, workspace_id)
    if ws is None:
        raise _error(404, 40430, "errors.workspace.not_found", "办公室不存在")
    return _ok(ws.model_dump(mode="json"))


@router.put("/{workspace_id}")
async def update_workspace(
    workspace_id: str,
    data: WorkspaceUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "manage_settings", db)
    ws = await workspace_service.update_workspace(db, workspace_id, data)
    if ws is None:
        raise _error(404, 40430, "errors.workspace.not_found", "办公室不存在")
    return _ok(ws.model_dump(mode="json"))


@router.delete("/{workspace_id}")
async def delete_workspace(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "delete_workspace", db)
    try:
        ok = await workspace_service.delete_workspace(db, workspace_id)
    except ValueError as e:
        raise _error(400, 40030, "errors.workspace.delete_invalid", str(e))
    if not ok:
        raise _error(404, 40430, "errors.workspace.not_found", "办公室不存在")
    return _ok(message="已删除")


# ── Agent Management ─────────────────────────────────

@router.post("/{workspace_id}/agents")
async def add_agent(
    workspace_id: str,
    data: AddAgentRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "manage_agents", db)
    try:
        agent = await workspace_service.add_agent(db, workspace_id, data, user.id)
    except ValueError as e:
        raise _error(400, 40031, "errors.workspace.add_agent_invalid", str(e))
    return _ok(agent.model_dump(mode="json"))


@router.get("/{workspace_id}/check-agent-genes")
async def check_agent_genes(
    workspace_id: str,
    instance_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "manage_agents", db)

    from app.models.workspace import Workspace
    from app.models.gene import Gene, InstanceGene, InstanceGeneStatus
    from app.models.org_required_gene import OrgRequiredGene
    from app.models.base import not_deleted
    from app.core.config import settings

    ws = (await db.execute(
        sa_select(Workspace).where(Workspace.id == workspace_id, not_deleted(Workspace))
    )).scalar_one_or_none()
    if not ws:
        raise _error(404, 40430, "errors.workspace.not_found", "办公室不存在")

    required_rows = (await db.execute(
        sa_select(OrgRequiredGene, Gene)
        .join(Gene, OrgRequiredGene.gene_id == Gene.id)
        .where(
            OrgRequiredGene.org_id == ws.org_id,
            not_deleted(OrgRequiredGene),
            not_deleted(Gene),
        )
    )).all()

    if not required_rows:
        return _ok({"missing_genes": [], "all_installed": True, "genehub_web_url": settings.GENEHUB_WEB_URL})

    installed_result = await db.execute(
        sa_select(Gene.slug).join(InstanceGene, InstanceGene.gene_id == Gene.id).where(
            InstanceGene.instance_id == instance_id,
            InstanceGene.status == InstanceGeneStatus.installed,
            not_deleted(InstanceGene),
        )
    )
    installed_slugs = {row[0] for row in installed_result.all()}

    missing = []
    for rg, gene in required_rows:
        if gene.slug not in installed_slugs:
            missing.append({
                "id": rg.id,
                "gene_id": gene.id,
                "gene_name": gene.name,
                "gene_slug": gene.slug,
                "gene_short_description": gene.short_description,
                "gene_icon": gene.icon,
                "gene_category": gene.category,
            })

    return _ok({
        "missing_genes": missing,
        "all_installed": len(missing) == 0,
        "genehub_web_url": settings.GENEHUB_WEB_URL,
    })


@router.put("/{workspace_id}/agents/{instance_id}")
async def update_agent(
    workspace_id: str,
    instance_id: str,
    data: UpdateAgentRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "manage_agents", db)
    agent = await workspace_service.update_agent(db, workspace_id, instance_id, data)
    if agent is None:
        raise _error(404, 40431, "errors.workspace.agent_not_found", "AI 员工不存在")
    return _ok(agent.model_dump(mode="json"))


@router.delete("/{workspace_id}/agents/{instance_id}")
async def remove_agent(
    workspace_id: str,
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "manage_agents", db)
    ok = await workspace_service.remove_agent(db, workspace_id, instance_id)
    if not ok:
        raise _error(404, 40432, "errors.workspace.agent_not_in_workspace", "AI 员工不在该办公室中")
    return _ok(message="已移除")


# ── Blackboard ───────────────────────────────────────

@router.get("/{workspace_id}/blackboard")
async def get_blackboard(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    await wm_service.check_workspace_member(workspace_id, user, db)
    bb = await workspace_service.get_blackboard(db, workspace_id)
    if bb is None:
        raise _error(404, 40433, "errors.workspace.blackboard_not_found", "黑板不存在")
    return _ok(bb.model_dump(mode="json"))


@router.put("/{workspace_id}/blackboard")
async def update_blackboard(
    workspace_id: str,
    data: BlackboardUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "edit_blackboard", db)
    bb = await workspace_service.update_blackboard(db, workspace_id, data)
    if bb is None:
        raise _error(404, 40433, "errors.workspace.blackboard_not_found", "黑板不存在")
    return _ok(bb.model_dump(mode="json"))


@router.patch("/{workspace_id}/blackboard/sections")
async def patch_blackboard_section(
    workspace_id: str,
    data: BlackboardSectionPatch,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "edit_blackboard", db)
    bb = await workspace_service.patch_blackboard_section(db, workspace_id, data)
    if bb is None:
        raise _error(404, 40433, "errors.workspace.blackboard_not_found", "黑板不存在")
    return _ok(bb.model_dump(mode="json"))


# ── Workspace Schedules ──────────────────────────────

@router.get("/{workspace_id}/schedules")
async def list_schedules(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    await wm_service.check_workspace_member(workspace_id, user, db)
    from app.models.workspace_schedule import WorkspaceSchedule
    from app.services.schedule_runner import PRESET_TEMPLATES
    result = await db.execute(
        sa_select(WorkspaceSchedule).where(
            WorkspaceSchedule.workspace_id == workspace_id,
            WorkspaceSchedule.deleted_at.is_(None),
        )
    )
    items = [
        {"id": s.id, "workspace_id": s.workspace_id, "name": s.name,
         "cron_expr": s.cron_expr, "message_template": s.message_template,
         "is_active": s.is_active, "created_at": s.created_at}
        for s in result.scalars().all()
    ]
    return _ok({"schedules": items, "presets": PRESET_TEMPLATES})


@router.post("/{workspace_id}/schedules")
async def create_schedule(
    workspace_id: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "manage_settings", db)
    import uuid
    from app.models.workspace_schedule import WorkspaceSchedule
    schedule = WorkspaceSchedule(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        name=data.get("name", ""),
        cron_expr=data.get("cron_expr", ""),
        message_template=data.get("message_template", ""),
        is_active=data.get("is_active", True),
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return _ok({
        "id": schedule.id, "name": schedule.name,
        "cron_expr": schedule.cron_expr, "message_template": schedule.message_template,
        "is_active": schedule.is_active,
    })


@router.put("/{workspace_id}/schedules/{schedule_id}")
async def update_schedule(
    workspace_id: str, schedule_id: str, data: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "manage_settings", db)
    from app.models.workspace_schedule import WorkspaceSchedule
    result = await db.execute(
        sa_select(WorkspaceSchedule).where(
            WorkspaceSchedule.id == schedule_id,
            WorkspaceSchedule.workspace_id == workspace_id,
            WorkspaceSchedule.deleted_at.is_(None),
        )
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise _error(404, 40434, "errors.schedule.not_found", "定时器不存在")
    for field in ("name", "cron_expr", "message_template", "is_active"):
        if field in data:
            setattr(schedule, field, data[field])
    await db.commit()
    return _ok({"id": schedule.id, "name": schedule.name, "is_active": schedule.is_active})


@router.delete("/{workspace_id}/schedules/{schedule_id}")
async def delete_schedule(
    workspace_id: str, schedule_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "manage_settings", db)
    from app.models.workspace_schedule import WorkspaceSchedule
    result = await db.execute(
        sa_select(WorkspaceSchedule).where(
            WorkspaceSchedule.id == schedule_id,
            WorkspaceSchedule.workspace_id == workspace_id,
            WorkspaceSchedule.deleted_at.is_(None),
        )
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        raise _error(404, 40434, "errors.schedule.not_found", "定时器不存在")
    schedule.soft_delete()
    await db.commit()
    return _ok(message="deleted")


# ── Workspace Members ────────────────────────────────

@router.get("/{workspace_id}/members")
async def list_members(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    await wm_service.check_workspace_member(workspace_id, user, db)
    members = await workspace_service.list_workspace_members(db, workspace_id)
    return _ok([m.model_dump(mode="json") for m in members])


@router.post("/{workspace_id}/members")
async def add_member(
    workspace_id: str,
    data: WorkspaceMemberAdd,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "manage_members", db)
    try:
        member = await workspace_service.add_workspace_member(
            db, workspace_id, data.user_id,
            permissions=data.permissions,
            is_admin=data.is_admin,
        )
    except ValueError as e:
        raise _error(400, 40032, "errors.workspace.add_member_invalid", str(e))
    return _ok(member.model_dump(mode="json"))


@router.put("/{workspace_id}/members/{user_id}")
async def update_member(
    workspace_id: str,
    user_id: str,
    data: WorkspaceMemberUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "manage_members", db)
    ok = await workspace_service.update_workspace_member_permissions(
        db, workspace_id, user_id,
        permissions=data.permissions,
        is_admin=data.is_admin,
    )
    if not ok:
        raise _error(404, 40434, "errors.workspace.member_not_found", "成员不存在")
    return _ok(message="已更新")


@router.delete("/{workspace_id}/members/{user_id}")
async def remove_member(
    workspace_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "manage_members", db)
    ok = await workspace_service.remove_workspace_member(
        db, workspace_id, user_id, operator_name=user.name,
    )
    if not ok:
        raise _error(404, 40434, "errors.workspace.member_not_found", "成员不存在")
    return _ok(message="已移除")


# ── Permissions ──────────────────────────────────────

@router.get("/{workspace_id}/my-permissions")
async def get_my_permissions(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    perms = await wm_service.get_my_permissions(workspace_id, user, db)
    return _ok(perms)


@router.get("/{workspace_id}/search-users")
async def search_users(
    workspace_id: str,
    q: str = Query(default=""),
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    await wm_service.check_workspace_access(workspace_id, user, "manage_members", db)
    results = await wm_service.search_org_users(workspace_id, org.id, q, db)
    return _ok(results)


# ── Group Chat (Broadcast) ───────────────────────────

@router.post("/{workspace_id}/chat")
async def workspace_chat(
    workspace_id: str,
    data: WorkspaceChatRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    """Workspace-level group chat: broadcast user message to all agents."""
    await wm_service.check_workspace_access(workspace_id, user, "send_chat", db)
    ws_info = await workspace_service.get_workspace(db, workspace_id)
    if ws_info is None:
        raise _error(404, 40430, "errors.workspace.not_found", "办公室不存在")

    await msg_service.record_message(
        db,
        workspace_id=workspace_id,
        sender_type="user",
        sender_id=user.id,
        sender_name=user.name,
        content=data.message,
    )

    running_agents = await _get_running_agents(db, workspace_id)
    if not running_agents:
        logger.warning("workspace_chat: workspace=%s 没有运行中的 Agent", workspace_id)
        _broadcast_system_info(workspace_id, "办公室内没有运行中的 AI 员工")
        return _ok({"status": "no_agents"})

    from app.services import corridor_router
    has_topo = await corridor_router.has_any_connections(workspace_id, db)

    human_endpoints: list = []

    if has_topo:
        audience = await corridor_router.get_blackboard_audience(workspace_id, db)
        reachable_ids = {ep.entity_id for ep in audience if ep.endpoint_type == "agent"}
        human_endpoints = [ep for ep in audience if ep.endpoint_type == "human"]
        target_agents = [a for a in running_agents if a.id in reachable_ids]
        excluded = [a for a in running_agents if a.id not in reachable_ids]
        if excluded:
            repaired = False
            for agent in excluded:
                if agent.hex_position_q is not None:
                    connected = await corridor_router.auto_connect_hex(
                        workspace_id, agent.hex_position_q, agent.hex_position_r or 0, user.id, db,
                    )
                    if connected:
                        logger.info(
                            "workspace_chat: 自动补连 Agent %s 到 %d 个邻居",
                            agent.agent_display_name or agent.name, len(connected),
                        )
                        repaired = True
            if repaired:
                await db.commit()
                audience = await corridor_router.get_blackboard_audience(workspace_id, db)
                reachable_ids = {ep.entity_id for ep in audience if ep.endpoint_type == "agent"}
                human_endpoints = [ep for ep in audience if ep.endpoint_type == "human"]
                target_agents = [a for a in running_agents if a.id in reachable_ids]
                excluded = [a for a in running_agents if a.id not in reachable_ids]
            if excluded:
                excluded_names = [a.agent_display_name or a.name for a in excluded]
                logger.warning(
                    "workspace_chat: workspace=%s 拓扑过滤排除了 %d 个 Agent: %s",
                    workspace_id, len(excluded), excluded_names,
                )
    else:
        target_agents = running_agents

    if not target_agents:
        logger.warning(
            "workspace_chat: workspace=%s has_topo=%s, 没有可达的运行中 AI 员工 (running=%d)",
            workspace_id, has_topo, len(running_agents),
        )
        _broadcast_system_info(workspace_id, "没有可达的运行中 AI 员工")
        return _ok({"status": "no_reachable_agents"})

    members = _build_members_list(ws_info, user)
    recent_messages = await msg_service.get_recent_messages(db, workspace_id)

    for inst in target_agents:
        _fire_task(
            _stream_agent_response(
                workspace_id=workspace_id,
                instance=inst,
                members=members,
                recent_messages=recent_messages,
                user_name=user.name,
                user_message=data.message,
                ws_name=ws_info.name,
                mentions=data.mentions,
            )
        )

    if human_endpoints:
        from app.services.collaboration_service import deliver_to_human
        for ep in human_endpoints:
            _fire_task(deliver_to_human(
                workspace_id=workspace_id,
                human_hex_id=ep.entity_id,
                source_name=user.name,
                message=data.message,
            ))

    return _ok({"status": "broadcasting", "agent_count": len(target_agents), "human_count": len(human_endpoints)})


class SystemMessageRequest(BaseModel):
    content: str


@router.post("/{workspace_id}/system-message")
async def post_system_message(
    workspace_id: str,
    data: SystemMessageRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    """Persist a system message (slash command result, etc.) without triggering agent responses."""
    await wm_service.check_workspace_access(workspace_id, user, "send_chat", db)
    msg = await msg_service.record_message(
        db,
        workspace_id=workspace_id,
        sender_type="system",
        sender_id=user.id,
        sender_name=user.name,
        content=data.content,
        message_type="system",
    )
    broadcast_event(workspace_id, "system:info", {
        "id": msg.id,
        "sender_type": "system",
        "sender_id": user.id,
        "sender_name": user.name,
        "content": data.content,
        "message_type": "system",
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    })
    return _ok({"id": msg.id})


@router.get("/{workspace_id}/messages")
async def list_workspace_messages(
    workspace_id: str,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    """List recent workspace messages for chat history."""
    await wm_service.check_workspace_member(workspace_id, user, db)
    messages = await msg_service.get_recent_messages(db, workspace_id, limit)
    return _ok([
        {
            "id": m.id,
            "workspace_id": m.workspace_id,
            "sender_type": m.sender_type,
            "sender_id": m.sender_id,
            "sender_name": m.sender_name,
            "content": m.content,
            "message_type": m.message_type,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ])


@router.get("/{workspace_id}/collaboration-timeline")
async def list_collaboration_timeline(
    workspace_id: str,
    limit: int = Query(default=100, le=500),
    since: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    """List all collaboration messages in a workspace as a timeline."""
    await wm_service.check_workspace_member(workspace_id, user, db)
    from datetime import datetime as dt
    since_dt = dt.fromisoformat(since) if since else None
    messages = await msg_service.get_collaboration_timeline(
        db, workspace_id, limit, since_dt,
    )
    return _ok([
        {
            "id": m.id,
            "workspace_id": m.workspace_id,
            "sender_type": m.sender_type,
            "sender_id": m.sender_id,
            "sender_name": m.sender_name,
            "content": m.content,
            "message_type": m.message_type,
            "target_instance_id": m.target_instance_id,
            "depth": m.depth,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ])


@router.get("/{workspace_id}/agents/{instance_id}/collaboration-messages")
async def list_agent_collaboration_messages(
    workspace_id: str,
    instance_id: str,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    """List collaboration messages sent to or from a specific agent."""
    await wm_service.check_workspace_member(workspace_id, user, db)
    messages = await msg_service.get_agent_collaboration_messages(
        db, workspace_id, instance_id, limit,
    )
    return _ok([
        {
            "id": m.id,
            "workspace_id": m.workspace_id,
            "sender_type": m.sender_type,
            "sender_id": m.sender_id,
            "sender_name": m.sender_name,
            "content": m.content,
            "message_type": m.message_type,
            "target_instance_id": m.target_instance_id,
            "depth": m.depth,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ])


# ── Legacy Chat Proxy (deprecated) ──────────────────

@router.post("/{workspace_id}/agents/{instance_id}/chat")
async def agent_chat(
    workspace_id: str,
    instance_id: str,
    data: ChatMessageRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    """Single-agent chat (deprecated, use workspace_chat instead)."""
    await wm_service.check_workspace_access(workspace_id, user, "send_chat", db)
    result = await db.execute(
        sa_select(Instance).where(
            Instance.id == instance_id,
            Instance.workspace_id == workspace_id,
            Instance.deleted_at.is_(None),
        )
    )
    inst = result.scalar_one_or_none()
    if inst is None:
        raise _error(404, 40432, "errors.workspace.agent_not_in_workspace", "AI 员工不在该办公室中")

    ws_info = await workspace_service.get_workspace(db, workspace_id)
    recent_messages = await msg_service.get_recent_messages(db, workspace_id)
    members = _build_members_list(ws_info, user)

    agent_name = inst.agent_display_name or inst.name
    context_prompt = msg_service.build_context_prompt(
        workspace_name=ws_info.name if ws_info else "Unknown",
        agent_display_name=agent_name,
        current_instance_id=instance_id,
        members=members,
        recent_messages=recent_messages,
    )

    messages = [
        {"role": "system", "content": context_prompt},
        {"role": "user", "content": data.message},
    ]

    base_url, token = _get_instance_connection(inst)
    if not base_url or not token:
        raise _error(400, 40033, "errors.workspace.agent_connection_missing", "AI 员工实例缺少访问地址或 Token")

    async def stream():
        full_response = ""
        async with httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(verify=False, local_address="0.0.0.0"),
            timeout=120,
        ) as client:
            async with client.stream(
                "POST",
                f"{base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "X-OpenClaw-Session-Key": f"workspace:{workspace_id}",
                },
                json={"model": "gpt-4", "messages": messages, "stream": True},
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        chunk_data = line[6:]
                        if chunk_data == "[DONE]":
                            yield "data: [DONE]\n\n"
                            break
                        try:
                            chunk = json.loads(chunk_data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response += content
                                yield f"data: {json.dumps({'content': content})}\n\n"
                        except json.JSONDecodeError:
                            pass

        if full_response and not msg_service.is_no_reply(full_response):
            async with async_session_factory() as save_db:
                await msg_service.record_message(
                    save_db,
                    workspace_id=workspace_id,
                    sender_type="agent",
                    sender_id=instance_id,
                    sender_name=agent_name,
                    content=full_response,
                )

    return StreamingResponse(stream(), media_type="text/event-stream")


# ── SSE Event Stream ─────────────────────────────────

_workspace_queues: dict[str, set[asyncio.Queue]] = {}


def broadcast_event(workspace_id: str, event_type: str, data: dict):
    queues = _workspace_queues.get(workspace_id, set())
    for q in queues:
        q.put_nowait({"event": event_type, "data": data})


def _broadcast_system_info(workspace_id: str, content: str) -> None:
    """Broadcast a system:info event with full fields expected by the frontend."""
    broadcast_event(workspace_id, "system:info", {
        "id": f"sys-{int(time.time() * 1000)}",
        "sender_type": "system",
        "sender_id": "system",
        "sender_name": "System",
        "content": content,
        "message_type": "system",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


@router.get("/{workspace_id}/events")
async def workspace_events(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_from_query_dep()),
):
    await wm_service.check_workspace_member(workspace_id, user, db)

    snapshot = await _build_agent_status_snapshot(workspace_id, db)

    queue: asyncio.Queue = asyncio.Queue()
    if workspace_id not in _workspace_queues:
        _workspace_queues[workspace_id] = set()
    _workspace_queues[workspace_id].add(queue)

    async def stream():
        try:
            yield f"data: {json.dumps({'event': 'connected'})}\n\n"
            if snapshot:
                yield f"event: agent:status_snapshot\ndata: {json.dumps(snapshot)}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"event: {msg['event']}\ndata: {json.dumps(msg['data'])}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _workspace_queues.get(workspace_id, set()).discard(queue)

    return StreamingResponse(stream(), media_type="text/event-stream")


async def _build_agent_status_snapshot(workspace_id: str, db: AsyncSession) -> dict | None:
    """Build a snapshot of all agents' SSE connection status for the workspace."""
    from app.services.sse_listener import sse_listener_manager

    result = await db.execute(
        sa_select(Instance.id).where(
            Instance.workspace_id == workspace_id,
            Instance.deleted_at.is_(None),
        )
    )
    instance_ids = result.scalars().all()
    if not instance_ids:
        return None

    healthy = sse_listener_manager.healthy_instances
    return {
        "agents": [
            {"instance_id": iid, "sse_connected": iid in healthy}
            for iid in instance_ids
        ],
    }


# ── SSE Token ────────────────────────────────────────

@router.post("/sse-token")
async def create_sse_token(
    user=Depends(_get_current_user_dep()),
):
    from app.core.security import create_access_token
    token = create_access_token(
        subject=user.id,
        extra_claims={"scope": "sse"},
        expires_delta=timedelta(minutes=5),
    )
    return _ok({"sse_token": token, "expires_in": 300})


# ── Private helpers ──────────────────────────────────

async def _get_running_agents(db: AsyncSession, workspace_id: str) -> list[Instance]:
    result = await db.execute(
        sa_select(Instance).where(
            Instance.workspace_id == workspace_id,
            Instance.status == "running",
            Instance.deleted_at.is_(None),
        )
    )
    return list(result.scalars().all())


def _get_instance_connection(inst: Instance) -> tuple[str, str]:
    env_vars = json.loads(inst.env_vars or "{}")
    token = env_vars.get("OPENCLAW_GATEWAY_TOKEN", "")
    domain = inst.ingress_domain or ""
    base_url = f"https://{domain}" if domain else ""
    return base_url, token


def _build_members_list(ws_info, user) -> list[dict]:
    members = []
    if ws_info and ws_info.agents:
        for a in ws_info.agents:
            members.append({
                "type": "AI 员工",
                "name": a.display_name or a.name,
                "id": a.instance_id,
            })
    members.append({"type": "User", "name": user.name, "id": user.id})
    return members


NO_REPLY_BUFFER_SIZE = 20


async def _stream_agent_response(
    *,
    workspace_id: str,
    instance: Instance,
    members: list[dict],
    recent_messages: list,
    user_name: str,
    user_message: str,
    ws_name: str,
    mentions: list[str] | None = None,
):
    """Stream a single agent's response and relay via SSE broadcast.

    Buffers initial characters to detect NO_REPLY before pushing to frontend.
    Each agent runs in its own asyncio.Task so they execute in parallel.
    """
    agent_name = instance.agent_display_name or instance.name
    instance_id = instance.id

    context_prompt = msg_service.build_context_prompt(
        workspace_name=ws_name,
        agent_display_name=agent_name,
        current_instance_id=instance_id,
        members=members,
        recent_messages=recent_messages,
    )

    if mentions and len(mentions) > 0:
        is_mentioned = instance_id in mentions
        if is_mentioned:
            context_prompt += "\n[重要] 用户在消息中 @提及了你，请务必回复。\n"
        else:
            context_prompt += "\n[提示] 用户没有 @提及你。如果消息与你无关，请回复 NO_REPLY。\n"

    messages = [
        {"role": "system", "content": context_prompt},
        {"role": "user", "content": f"[{user_name}]: {user_message}"},
    ]

    base_url, token = _get_instance_connection(instance)
    if not base_url or not token:
        logger.warning("Agent %s (%s) 缺少连接信息，跳过", agent_name, instance_id)
        return

    broadcast_event(workspace_id, "agent:typing", {
        "instance_id": instance_id,
        "agent_name": agent_name,
    })

    buffer = ""
    flushed = False
    full_response = ""

    try:
        async with httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(verify=False, local_address="0.0.0.0"),
            timeout=120,
        ) as client:
            async with client.stream(
                "POST",
                f"{base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "X-OpenClaw-Session-Key": f"workspace:{workspace_id}",
                },
                json={"model": "gpt-4", "messages": messages, "stream": True},
            ) as resp:
                if resp.status_code != 200:
                    logger.error(
                        "Agent %s API returned %d, expected 200",
                        agent_name, resp.status_code,
                    )
                    broadcast_event(workspace_id, "agent:done", {
                        "instance_id": instance_id,
                        "agent_name": agent_name,
                    })
                    return
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    chunk_data = line[6:]
                    if chunk_data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(chunk_data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                    except json.JSONDecodeError:
                        continue
                    if not content:
                        continue

                    full_response += content

                    if not flushed:
                        buffer += content
                        if len(buffer) > NO_REPLY_BUFFER_SIZE:
                            if msg_service.is_no_reply(buffer.strip()):
                                logger.info("Agent %s replied NO_REPLY, discarding", agent_name)
                                broadcast_event(workspace_id, "agent:done", {
                                    "instance_id": instance_id,
                                    "agent_name": agent_name,
                                })
                                return
                            broadcast_event(workspace_id, "agent:chunk", {
                                "instance_id": instance_id,
                                "agent_name": agent_name,
                                "content": buffer,
                            })
                            flushed = True
                    else:
                        broadcast_event(workspace_id, "agent:chunk", {
                            "instance_id": instance_id,
                            "agent_name": agent_name,
                            "content": content,
                        })
    except Exception as e:
        logger.error("Agent %s streaming failed: %s", agent_name, e)
        broadcast_event(workspace_id, "agent:error", {
            "instance_id": instance_id,
            "agent_name": agent_name,
            "error": str(e),
        })
        return

    if not flushed and buffer:
        if msg_service.is_no_reply(buffer.strip()):
            logger.info("Agent %s replied NO_REPLY (short response), discarding", agent_name)
            broadcast_event(workspace_id, "agent:done", {
                "instance_id": instance_id,
                "agent_name": agent_name,
            })
            return
        broadcast_event(workspace_id, "agent:chunk", {
            "instance_id": instance_id,
            "agent_name": agent_name,
            "content": buffer,
        })

    if full_response and not msg_service.is_no_reply(full_response.strip()):
        broadcast_event(workspace_id, "agent:done", {
            "instance_id": instance_id,
            "agent_name": agent_name,
            "full_content": full_response,
        })

        async with async_session_factory() as save_db:
            await msg_service.record_message(
                save_db,
                workspace_id=workspace_id,
                sender_type="agent",
                sender_id=instance_id,
                sender_name=agent_name,
                content=full_response,
            )
    else:
        broadcast_event(workspace_id, "agent:done", {
            "instance_id": instance_id,
            "agent_name": agent_name,
        })
