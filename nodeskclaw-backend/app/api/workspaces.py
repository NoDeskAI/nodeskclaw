"""Workspace API — CRUD, Agent management, Blackboard, Context, Members, Chat, SSE."""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Coroutine

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import hooks
from app.core.deps import async_session_factory, get_current_org, get_db
from app.models.instance import Instance
from app.models.workspace_agent import WorkspaceAgent
from app.schemas.workspace import (
    AddAgentRequest,
    BlackboardSectionPatch,
    BlackboardUpdate,
    ChatMessageRequest,
    DecorationUpdate,
    ObjectiveCreate,
    ObjectiveUpdate,
    TaskCreate,
    TaskUpdate,
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


def _get_current_user_or_agent_dep():
    from app.core.security import get_current_user_or_agent
    return get_current_user_or_agent


# ── Workspace CRUD ───────────────────────────────────

@router.post("")
async def create_workspace(
    data: WorkspaceCreate,
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    ws = await workspace_service.create_workspace(db, org.id, user.id, data)
    await hooks.emit("operation_audit", action="workspace.created", target_type="workspace", target_id=getattr(ws, "id", "") or "", actor_id=user.id, org_id=org.id)
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
    await hooks.emit("operation_audit", action="workspace.updated", target_type="workspace", target_id=workspace_id, actor_id=user.id)
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
    await hooks.emit("operation_audit", action="workspace.deleted", target_type="workspace", target_id=workspace_id, actor_id=user.id)
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
    await hooks.emit("operation_audit", action="workspace.agent_added", target_type="workspace", target_id=workspace_id, actor_id=user.id, details={"instance_id": data.instance_id})
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
    await hooks.emit("operation_audit", action="workspace.agent_updated", target_type="workspace", target_id=workspace_id, actor_id=user.id, details={"instance_id": instance_id})
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
    await hooks.emit("operation_audit", action="workspace.agent_removed", target_type="workspace", target_id=workspace_id, actor_id=user.id, details={"instance_id": instance_id})
    return _ok(message="已移除")


# ── Blackboard ───────────────────────────────────────

@router.get("/{workspace_id}/blackboard")
async def get_blackboard(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
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
    user=Depends(_get_current_user_or_agent_dep()),
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


async def _notify_agents_task_done(workspace_id: str, task_title: str):
    """Send system message to workspace agents when a task completes."""
    try:
        from app.services import corridor_router
        from app.services.collaboration_service import send_system_message_to_agents
        from app.models.base import not_deleted

        async with async_session_factory() as db:
            has_topo = await corridor_router.has_any_connections(workspace_id, db)
            if has_topo:
                audience = await corridor_router.get_blackboard_audience(workspace_id, db)
                agent_ids = [ep.entity_id for ep in audience if ep.endpoint_type == "agent"]
            else:
                agents_q = await db.execute(
                    sa_select(Instance.id)
                    .join(
                        WorkspaceAgent,
                        (WorkspaceAgent.instance_id == Instance.id)
                        & (WorkspaceAgent.deleted_at.is_(None)),
                    )
                    .where(
                        WorkspaceAgent.workspace_id == workspace_id,
                        Instance.status == "running",
                        Instance.deleted_at.is_(None),
                    )
                )
                agent_ids = [r[0] for r in agents_q.all()]

            if agent_ids:
                message = f"任务「{task_title}」已完成，请检查黑板是否有新的待办任务。"
                await send_system_message_to_agents(workspace_id, agent_ids, message, db)
    except Exception as e:
        logger.warning("通知 Agent 任务完成失败: %s", e)


# ── Tasks ────────────────────────────────────────────

@router.get("/{workspace_id}/blackboard/tasks")
async def list_tasks(
    workspace_id: str,
    status: str | None = Query(None),
    exclude_archived: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    await wm_service.check_workspace_member(workspace_id, user, db)
    tasks = await workspace_service.list_tasks(db, workspace_id, status, exclude_archived)
    return _ok([t.model_dump(mode="json") for t in tasks])


@router.post("/{workspace_id}/blackboard/tasks")
async def create_task(
    workspace_id: str,
    data: TaskCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "edit_blackboard", db)
    task = await workspace_service.create_task(db, workspace_id, data)
    broadcast_event(workspace_id, "task:created", task.model_dump(mode="json"))
    return _ok(task.model_dump(mode="json"))


@router.put("/{workspace_id}/blackboard/tasks/{task_id}")
async def update_task(
    workspace_id: str,
    task_id: str,
    data: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "edit_blackboard", db)
    result = await workspace_service.update_task(db, workspace_id, task_id, data)
    if result is None:
        raise _error(404, 40434, "errors.workspace.task_not_found", "任务不存在")
    task_info, status_changed, old_status, new_status = result
    broadcast_event(workspace_id, "task:updated", task_info.model_dump(mode="json"))
    if status_changed:
        broadcast_event(workspace_id, "task:status_changed", {
            "task_id": task_id,
            "title": task_info.title,
            "old_status": old_status,
            "new_status": new_status,
        })
        if new_status == "done":
            _fire_task(_notify_agents_task_done(workspace_id, task_info.title))
    return _ok(task_info.model_dump(mode="json"))


@router.post("/{workspace_id}/blackboard/tasks/{task_id}/archive")
async def archive_task(
    workspace_id: str,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "edit_blackboard", db)
    task = await workspace_service.archive_task(db, workspace_id, task_id)
    if task is None:
        raise _error(404, 40434, "errors.workspace.task_not_found", "任务不存在")
    broadcast_event(workspace_id, "task:archived", task.model_dump(mode="json"))
    return _ok(task.model_dump(mode="json"))


# ── Objectives ───────────────────────────────────────

@router.get("/{workspace_id}/blackboard/objectives")
async def list_objectives(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    await wm_service.check_workspace_member(workspace_id, user, db)
    objs = await workspace_service.list_objectives(db, workspace_id)
    return _ok([o.model_dump(mode="json") for o in objs])


@router.post("/{workspace_id}/blackboard/objectives")
async def create_objective(
    workspace_id: str,
    data: ObjectiveCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "edit_blackboard", db)
    obj = await workspace_service.create_objective(db, workspace_id, data, user.id)
    broadcast_event(workspace_id, "objective:created", obj.model_dump(mode="json"))
    return _ok(obj.model_dump(mode="json"))


@router.put("/{workspace_id}/blackboard/objectives/{objective_id}")
async def update_objective(
    workspace_id: str,
    objective_id: str,
    data: ObjectiveUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "edit_blackboard", db)
    obj = await workspace_service.update_objective(db, workspace_id, objective_id, data)
    if obj is None:
        raise _error(404, 40435, "errors.workspace.objective_not_found", "目标不存在")
    broadcast_event(workspace_id, "objective:updated", obj.model_dump(mode="json"))
    return _ok(obj.model_dump(mode="json"))


# ── Performance ──────────────────────────────────────

@router.get("/{workspace_id}/performance")
async def get_performance(
    workspace_id: str,
    instance_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    """Agent/team performance aggregated from workspace_tasks."""
    await wm_service.check_workspace_member(workspace_id, user, db)
    from app.models.workspace_task import WorkspaceTask

    base_q = sa_select(WorkspaceTask).where(
        WorkspaceTask.workspace_id == workspace_id,
        WorkspaceTask.deleted_at.is_(None),
    )

    if instance_id:
        base_q = base_q.where(WorkspaceTask.assignee_instance_id == instance_id)

    rows = (await db.execute(base_q)).scalars().all()

    total = len(rows)
    done = sum(1 for t in rows if t.status in ("done", "archived"))
    completion_rate = done / total if total > 0 else 0.0
    total_value = sum(t.actual_value or 0 for t in rows if t.status in ("done", "archived"))
    total_tokens = sum(t.token_cost or 0 for t in rows)
    roi = total_value / total_tokens * 1000 if total_tokens > 0 else 0.0

    return _ok({
        "instance_id": instance_id,
        "total_tasks": total,
        "completed_tasks": done,
        "task_completion_rate": round(completion_rate, 4),
        "total_value_created": round(total_value, 2),
        "total_token_cost": total_tokens,
        "roi_per_1k_tokens": round(roi, 4),
    })


@router.post("/{workspace_id}/performance/collect")
async def collect_performance(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    """Aggregate per-agent performance stats from workspace_tasks."""
    await wm_service.check_workspace_member(workspace_id, user, db)
    from app.models.workspace_task import WorkspaceTask

    rows = (await db.execute(
        sa_select(WorkspaceTask).where(
            WorkspaceTask.workspace_id == workspace_id,
            WorkspaceTask.deleted_at.is_(None),
        )
    )).scalars().all()

    agent_stats: dict[str, dict] = {}
    for t in rows:
        aid = t.assignee_instance_id or "unassigned"
        if aid not in agent_stats:
            agent_stats[aid] = {"total": 0, "done": 0, "value": 0.0, "tokens": 0}
        agent_stats[aid]["total"] += 1
        if t.status in ("done", "archived"):
            agent_stats[aid]["done"] += 1
            agent_stats[aid]["value"] += t.actual_value or 0
        agent_stats[aid]["tokens"] += t.token_cost or 0

    result = []
    for aid, s in agent_stats.items():
        rate = s["done"] / s["total"] if s["total"] > 0 else 0.0
        roi = s["value"] / s["tokens"] * 1000 if s["tokens"] > 0 else 0.0
        result.append({
            "instance_id": aid,
            "total_tasks": s["total"],
            "completed_tasks": s["done"],
            "task_completion_rate": round(rate, 4),
            "total_value_created": round(s["value"], 2),
            "total_token_cost": s["tokens"],
            "roi_per_1k_tokens": round(roi, 4),
        })

    return _ok(result)


@router.post("/{workspace_id}/performance/attribute-tokens")
async def attribute_tokens_to_tasks(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    """Attribute LLM token usage to in_progress/done tasks based on instance_id time window."""
    await wm_service.check_workspace_access(workspace_id, user, "edit_blackboard", db)
    from app.models.workspace_task import WorkspaceTask
    from app.models.llm_usage_log import LlmUsageLog

    tasks_q = await db.execute(
        sa_select(WorkspaceTask).where(
            WorkspaceTask.workspace_id == workspace_id,
            WorkspaceTask.status.in_(["in_progress", "done", "archived"]),
            WorkspaceTask.assignee_instance_id.isnot(None),
            WorkspaceTask.deleted_at.is_(None),
        )
    )
    tasks = tasks_q.scalars().all()

    updated = 0
    for task in tasks:
        q = sa_select(
            func.coalesce(func.sum(LlmUsageLog.total_tokens), 0)
        ).where(
            LlmUsageLog.instance_id == task.assignee_instance_id,
            LlmUsageLog.created_at >= task.created_at,
        )
        if task.completed_at:
            q = q.where(LlmUsageLog.created_at <= task.completed_at)
        result = await db.execute(q)
        total = int(result.scalar())
        if total > 0 and task.token_cost != total:
            task.token_cost = total
            updated += 1

    await db.commit()
    return _ok({"updated_tasks": updated})


# ── Decoration ───────────────────────────────────────

@router.get("/{workspace_id}/decoration")
async def get_decoration(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    await wm_service.check_workspace_member(workspace_id, user, db)
    from app.models.workspace import Workspace
    ws = (await db.execute(
        sa_select(Workspace).where(Workspace.id == workspace_id, Workspace.deleted_at.is_(None))
    )).scalar_one_or_none()
    if ws is None:
        raise _error(404, 40401, "errors.workspace.not_found", "办公室不存在")
    config = ws.decoration_config or {}
    hexes = config.get("hexes", {})
    return _ok({"hexes": hexes})


@router.put("/{workspace_id}/decoration")
async def update_decoration(
    workspace_id: str,
    data: DecorationUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "manage_settings", db)
    from app.models.workspace import Workspace
    ws = (await db.execute(
        sa_select(Workspace).where(Workspace.id == workspace_id, Workspace.deleted_at.is_(None))
    )).scalar_one_or_none()
    if ws is None:
        raise _error(404, 40401, "errors.workspace.not_found", "办公室不存在")

    new_config = {"hexes": {k: v.model_dump() for k, v in (data.hexes or {}).items()}}
    ws.decoration_config = new_config
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(ws, "decoration_config")
    await db.commit()
    await db.refresh(ws)
    return _ok({"hexes": new_config["hexes"]})


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
    user=Depends(_get_current_user_or_agent_dep()),
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
    await hooks.emit("operation_audit", action="workspace.member_added", target_type="workspace", target_id=workspace_id, actor_id=user.id, details={"member_user_id": data.user_id})
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
    await hooks.emit("operation_audit", action="workspace.member_updated", target_type="workspace", target_id=workspace_id, actor_id=user.id, details={"member_user_id": user_id})
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
    await hooks.emit("operation_audit", action="workspace.member_removed", target_type="workspace", target_id=workspace_id, actor_id=user.id, details={"member_user_id": user_id})
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

MAX_UPLOAD_SIZE = 20 * 1024 * 1024


@router.post("/{workspace_id}/files/upload")
async def upload_workspace_file(
    workspace_id: str,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    """Upload a file to a workspace (multipart/form-data)."""
    from app.services import storage_service
    from app.models.workspace_file import WorkspaceFile

    if not storage_service.is_configured():
        raise _error(503, 50301, "errors.storage.not_configured", "TOS 对象存储未配置")

    await wm_service.check_workspace_access(workspace_id, user, "send_chat", db)

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise _error(400, 40002, "errors.file.too_large", "文件大小超过限制（最大 20MB）")

    tos_key = await storage_service.upload_file(
        file_content=content,
        filename=file.filename or "unnamed",
        content_type=file.content_type or "application/octet-stream",
        workspace_id=workspace_id,
    )

    wf = WorkspaceFile(
        workspace_id=workspace_id,
        uploader_id=user.id,
        original_name=file.filename or "unnamed",
        file_size=len(content),
        content_type=file.content_type or "application/octet-stream",
        tos_key=tos_key,
    )
    db.add(wf)
    await db.commit()
    await db.refresh(wf)

    return _ok({
        "id": wf.id,
        "name": wf.original_name,
        "size": wf.file_size,
        "content_type": wf.content_type,
    })


@router.get("/{workspace_id}/files/{file_id}/url")
async def get_file_presigned_url(
    workspace_id: str,
    file_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    """Get a presigned download URL for a workspace file."""
    from app.services import storage_service
    from app.models.workspace_file import WorkspaceFile

    if not storage_service.is_configured():
        raise _error(503, 50301, "errors.storage.not_configured", "TOS 对象存储未配置")

    await wm_service.check_workspace_member(workspace_id, user, db)

    result = await db.execute(
        sa_select(WorkspaceFile).where(
            WorkspaceFile.id == file_id,
            WorkspaceFile.workspace_id == workspace_id,
            WorkspaceFile.deleted_at.is_(None),
        )
    )
    wf = result.scalar_one_or_none()
    if wf is None:
        raise _error(404, 40431, "errors.file.not_found", "文件不存在")

    try:
        url = await storage_service.get_presigned_url(wf.tos_key, expires=900)
    except Exception:
        logger.warning("生成文件 %s presigned URL 失败", wf.original_name, exc_info=True)
        raise _error(502, 50201, "errors.storage.presign_failed", "生成文件下载链接失败，请稍后重试")
    return _ok({"url": url, "expires_in": 900})


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

    attachments_meta: list[dict] | None = None
    attachment_files: list = []
    if data.file_ids:
        from app.models.workspace_file import WorkspaceFile

        result = await db.execute(
            sa_select(WorkspaceFile).where(
                WorkspaceFile.id.in_(data.file_ids),
                WorkspaceFile.workspace_id == workspace_id,
                WorkspaceFile.deleted_at.is_(None),
            )
        )
        attachment_files = list(result.scalars().all())
        if attachment_files:
            attachments_meta = [
                {
                    "id": f.id, "name": f.original_name,
                    "size": f.file_size, "content_type": f.content_type,
                }
                for f in attachment_files
            ]

    await msg_service.record_message(
        db,
        workspace_id=workspace_id,
        sender_type="user",
        sender_id=user.id,
        sender_name=user.name,
        content=data.message,
        attachments=attachments_meta,
    )

    attachments_with_urls: list[dict] = []
    if attachment_files:
        from app.services import storage_service
        for f in attachment_files:
            try:
                url = await storage_service.get_presigned_url(f.tos_key, expires=3600)
                attachments_with_urls.append({
                    "id": f.id, "name": f.original_name,
                    "size": f.file_size, "content_type": f.content_type,
                    "url": url,
                })
            except Exception:
                logger.warning(
                    "workspace_chat: 生成文件 %s presigned URL 失败",
                    f.original_name, exc_info=True,
                )

    from app.services.runtime.messaging.bus import message_bus
    from app.services.runtime.messaging.ingestion.portal import build_portal_envelope

    envelope = build_portal_envelope(
        workspace_id=workspace_id,
        user_id=user.id,
        user_name=user.name,
        content=data.message,
        mentions=data.mentions,
        attachments=attachments_with_urls or None,
    )

    async def _publish_via_bus():
        async with async_session_factory() as bus_db:
            result = await message_bus.publish(envelope, db=bus_db)
            await bus_db.commit()
            if result.error:
                logger.error("workspace_chat: MessageBus error: %s", result.error)
            return result

    _fire_task(_publish_via_bus())

    return _ok({"status": "broadcasting"})


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
            "attachments": m.attachments,
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
    wa_check = await db.execute(
        sa_select(WorkspaceAgent).where(
            WorkspaceAgent.workspace_id == workspace_id,
            WorkspaceAgent.instance_id == instance_id,
            WorkspaceAgent.deleted_at.is_(None),
        )
    )
    if wa_check.scalar_one_or_none() is None:
        raise _error(404, 40432, "errors.workspace.agent_not_in_workspace", "AI 员工不在该办公室中")
    inst = (await db.execute(sa_select(Instance).where(Instance.id == instance_id, Instance.deleted_at.is_(None)))).scalar_one_or_none()
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
        workspace_id=workspace_id,
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

    asyncio.ensure_future(_cross_instance_push(workspace_id, event_type, data))


async def _cross_instance_push(workspace_id: str, event_type: str, data: dict):
    """Forward SSE events to other backend instances via PG NOTIFY."""
    try:
        from app.core.deps import async_session_factory
        from app.services.runtime.pg_notify import PGNotifyService
        from app.services.runtime.sse_registry import (
            BACKEND_INSTANCE_ID,
            get_remote_instances_for_workspace,
        )

        async with async_session_factory() as db:
            remote_ids = await get_remote_instances_for_workspace(db, workspace_id)
            if not remote_ids:
                return

            payload = {
                "workspace_id": workspace_id,
                "event_type": event_type,
                "data": data,
            }
            for inst_id in remote_ids:
                await PGNotifyService.notify_sse_push(db, inst_id, payload)
            await db.commit()
    except Exception as e:
        logger.warning("Cross-instance SSE push failed: %s", e)


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

    import uuid as _uuid
    conn_id = str(_uuid.uuid4())
    try:
        from app.services.runtime import sse_registry
        await sse_registry.register_connection(
            db,
            connection_id=conn_id,
            instance_id=conn_id,
            target_type="workspace",
            target_id=workspace_id,
            workspace_id=workspace_id,
        )
        await db.commit()
    except Exception as e:
        logger.warning("Failed to register SSE connection: %s", e)

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
            try:
                from app.core.deps import async_session_factory
                from app.services.runtime import sse_registry
                async with async_session_factory() as cleanup_db:
                    await sse_registry.unregister_connection(cleanup_db, conn_id)
                    await cleanup_db.commit()
            except Exception:
                pass

    return StreamingResponse(stream(), media_type="text/event-stream")


async def _build_agent_status_snapshot(workspace_id: str, db: AsyncSession) -> dict | None:
    """Build a snapshot of all agents' SSE connection status for the workspace."""
    from app.services.sse_listener import sse_listener_manager

    result = await db.execute(
        sa_select(WorkspaceAgent.instance_id).where(
            WorkspaceAgent.workspace_id == workspace_id,
            WorkspaceAgent.deleted_at.is_(None),
        )
    )
    instance_ids = [r[0] for r in result.all()]
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

async def _get_running_agents(db: AsyncSession, workspace_id: str) -> list[tuple[Instance, WorkspaceAgent]]:
    result = await db.execute(
        sa_select(Instance, WorkspaceAgent)
        .join(
            WorkspaceAgent,
            (WorkspaceAgent.instance_id == Instance.id) & (WorkspaceAgent.deleted_at.is_(None)),
        )
        .where(
            WorkspaceAgent.workspace_id == workspace_id,
            Instance.status == "running",
            Instance.deleted_at.is_(None),
        )
    )
    return list(result.all())


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
    attachments: list[dict] | None = None,
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
        workspace_id=workspace_id,
    )

    if mentions and len(mentions) > 0:
        is_mentioned = instance_id in mentions
        if is_mentioned:
            context_prompt += "\n[重要] 用户在消息中 @提及了你，请务必回复。\n"
        else:
            context_prompt += "\n[提示] 用户没有 @提及你。如果消息与你无关，请回复 NO_REPLY。\n"

    user_content = f"[{user_name}]: {user_message}"
    if attachments:
        file_lines = []
        for att in attachments:
            size_kb = att["size"] // 1024
            file_lines.append(f"- {att['name']} ({size_kb}KB, {att['content_type']}): {att['url']}")
        user_content += "\n\n附件:\n" + "\n".join(file_lines)

    messages = [
        {"role": "system", "content": context_prompt},
        {"role": "user", "content": user_content},
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


# ── Maintenance ──────────────────────────────────────

@router.post("/maintenance/repair-channel-accounts")
async def repair_channel_accounts(
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    """Repair channel account apiUrl and ensure 'default' account for all workspace instances."""
    if not user.is_super_admin:
        raise HTTPException(status_code=403, detail={
            "error_code": 40310,
            "message_key": "errors.org.super_admin_required",
            "message": "仅限平台管理员操作",
        })
    from app.services import llm_config_service
    result = await llm_config_service.repair_channel_account_urls(db)
    return _ok(result)


@router.post("/maintenance/refresh-gene-skills")
async def refresh_gene_skills(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    """Refresh SKILL.md on all instances that have the specified genes installed."""
    if not user.is_super_admin:
        raise HTTPException(status_code=403, detail={
            "error_code": 40310,
            "message_key": "errors.org.super_admin_required",
            "message": "仅限平台管理员操作",
        })
    gene_slugs = body.get("gene_slugs", [])
    if not gene_slugs or not isinstance(gene_slugs, list):
        raise HTTPException(status_code=400, detail={
            "error_code": 40001,
            "message_key": "errors.validation.invalid_params",
            "message": "gene_slugs 为必填的字符串数组",
        })
    from app.services import gene_service
    result = await gene_service.refresh_gene_skills(db, gene_slugs)
    return _ok(result)
