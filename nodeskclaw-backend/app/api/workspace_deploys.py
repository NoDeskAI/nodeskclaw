"""Workspace batch deploy from template — status and SSE progress."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_org, get_db
from app.models.base import not_deleted
from app.models.workspace import Workspace
from app.models.workspace_deploy import WorkspaceDeploy
from app.services.k8s.event_bus import event_bus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["办公室模板部署"])


def _org_id(org) -> str:
    return org.id if hasattr(org, "id") else org.get("org_id", "")


def _ok(data=None, message: str = "success"):
    return {"code": 0, "message": message, "data": data}


@router.get("/deploys/active")
async def list_active_deploys(
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    oid = _org_id(org)
    r = await db.execute(
        select(WorkspaceDeploy, Workspace.name)
        .outerjoin(
            Workspace,
            (Workspace.id == WorkspaceDeploy.workspace_id) & (Workspace.deleted_at.is_(None)),
        )
        .where(
            WorkspaceDeploy.org_id == oid,
            WorkspaceDeploy.created_by == user.id,
            WorkspaceDeploy.status.in_(("pending", "deploying")),
            not_deleted(WorkspaceDeploy),
        )
        .order_by(WorkspaceDeploy.created_at.desc())
    )
    rows = []
    for wd, ws_name in r.all():
        rows.append({
            "id": wd.id,
            "workspace_id": wd.workspace_id,
            "workspace_name": ws_name or "",
            "template_id": wd.template_id,
            "status": wd.status,
            "total_agents": wd.total_agents,
            "completed_agents": wd.completed_agents,
            "failed_agents": wd.failed_agents,
        })
    return _ok(rows)


@router.get("/deploys/{deploy_id}")
async def get_workspace_deploy(
    deploy_id: str,
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    oid = _org_id(org)
    r = await db.execute(
        select(WorkspaceDeploy, Workspace.name)
        .outerjoin(
            Workspace,
            (Workspace.id == WorkspaceDeploy.workspace_id) & (Workspace.deleted_at.is_(None)),
        )
        .where(
            WorkspaceDeploy.id == deploy_id,
            WorkspaceDeploy.org_id == oid,
            WorkspaceDeploy.created_by == user.id,
            not_deleted(WorkspaceDeploy),
        )
    )
    row = r.first()
    if not row:
        raise HTTPException(status_code=404, detail="部署记录不存在")
    wd, ws_name = row
    return _ok({
        "id": wd.id,
        "workspace_id": wd.workspace_id,
        "workspace_name": ws_name or "",
        "template_id": wd.template_id,
        "status": wd.status,
        "total_agents": wd.total_agents,
        "completed_agents": wd.completed_agents,
        "failed_agents": wd.failed_agents,
        "progress_detail": wd.progress_detail,
        "config_snapshot": wd.config_snapshot,
        "created_at": wd.created_at.isoformat() if wd.created_at else None,
    })


@router.get("/deploys/{deploy_id}/progress")
async def workspace_deploy_progress_stream(
    deploy_id: str,
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    oid = _org_id(org)
    r = await db.execute(
        select(WorkspaceDeploy.id).where(
            WorkspaceDeploy.id == deploy_id,
            WorkspaceDeploy.org_id == oid,
            WorkspaceDeploy.created_by == user.id,
            not_deleted(WorkspaceDeploy),
        )
    )
    if not r.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="部署记录不存在")

    async def generate():
        async for ev in event_bus.subscribe("workspace_deploy_progress"):
            if ev.data.get("workspace_deploy_id") != deploy_id:
                continue
            yield ev.format()
            evt = ev.data.get("event")
            if evt == "complete":
                break

    return StreamingResponse(generate(), media_type="text/event-stream")
