"""Portal deploy endpoints."""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import hooks
from app.core.deps import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.deploy import DeployProgress, DeployRequest, PrecheckResult
from app.services import deploy_service
from app.services.k8s.event_bus import event_bus

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/precheck", response_model=ApiResponse[PrecheckResult])
async def precheck(
    body: DeployRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    result = await deploy_service.precheck(body, db)
    return ApiResponse(data=result)


@router.post("", response_model=ApiResponse[dict])
async def deploy(
    body: DeployRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    effective_org_id = body.org_id or current_user.current_org_id
    if not effective_org_id:
        raise HTTPException(status_code=400, detail="缺少目标组织，无法部署")
    try:
        deploy_id, ctx = await deploy_service.deploy_instance(
            body, current_user, db, org_id=effective_org_id
        )
    except IntegrityError:
        await db.rollback()
        slug_display = body.slug or body.name
        raise HTTPException(status_code=409, detail=f"实例标识 '{slug_display}' 已存在，请更换标识")

    await hooks.emit("operation_audit", action="deploy.started", target_type="instance", target_id=ctx.instance_id, actor_id=current_user.id, org_id=effective_org_id, details={"deploy_id": deploy_id, "slug": body.slug or body.name, "source": "portal"})
    task = asyncio.create_task(
        deploy_service.execute_deploy_pipeline(ctx),
        name=f"deploy-{deploy_id}",
    )
    deploy_service.register_deploy_task(deploy_id, task)
    logger.info("部署任务已提交到后台: deploy_id=%s, instance=%s", deploy_id, ctx.name)

    return ApiResponse(data={"deploy_id": deploy_id, "instance_id": ctx.instance_id})


@router.post("/{deploy_id}/cancel", response_model=ApiResponse[dict])
async def cancel_deploy_endpoint(
    deploy_id: str,
    _current_user: User = Depends(get_current_user),
):
    result = await deploy_service.cancel_deploy(deploy_id)
    await hooks.emit("operation_audit", action="deploy.cancelled", target_type="instance", target_id=deploy_id, actor_id=_current_user.id, details={"deploy_id": deploy_id, "source": "portal"})
    logger.info("取消部署: deploy_id=%s, result=%s", deploy_id, result)
    return ApiResponse(data={"deploy_id": deploy_id, "message": result})


@router.get("/progress/{deploy_id}")
async def deploy_progress_stream(deploy_id: str):
    async def generate():
        async for event in event_bus.subscribe("deploy_progress"):
            if event.data.get("deploy_id") == deploy_id:
                yield event.format()
                if event.data.get("status") in ("success", "failed"):
                    break

    return StreamingResponse(generate(), media_type="text/event-stream")
