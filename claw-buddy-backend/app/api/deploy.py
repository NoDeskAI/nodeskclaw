"""Deploy endpoints: precheck, deploy, SSE progress stream."""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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
    """部署预检。"""
    result = await deploy_service.precheck(body, db)
    return ApiResponse(data=result)


@router.post("", response_model=ApiResponse[dict])
async def deploy(
    body: DeployRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行部署：同步创建记录后立即返回，K8s 管道在后台异步执行。"""
    try:
        deploy_id, ctx = await deploy_service.deploy_instance(body, current_user, db)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"实例名称 '{body.name}' 已存在，请更换名称")

    # 后台异步执行 K8s 部署管道（使用独立 DB session）
    task = asyncio.create_task(
        deploy_service.execute_deploy_pipeline(ctx),
        name=f"deploy-{deploy_id}",
    )
    deploy_service.register_deploy_task(deploy_id, task)
    logger.info("部署任务已提交到后台: deploy_id=%s, instance=%s", deploy_id, ctx.name)

    return ApiResponse(data={"deploy_id": deploy_id})


@router.post("/{deploy_id}/cancel", response_model=ApiResponse[dict])
async def cancel_deploy_endpoint(
    deploy_id: str,
    _current_user: User = Depends(get_current_user),
):
    """立即取消部署：杀掉后台协程 + 删除 namespace + 更新 DB。"""
    result = await deploy_service.cancel_deploy(deploy_id)
    logger.info("取消部署: deploy_id=%s, result=%s", deploy_id, result)
    return ApiResponse(data={"deploy_id": deploy_id, "message": result})


@router.get("/progress/{deploy_id}")
async def deploy_progress_stream(deploy_id: str):
    """SSE stream for deploy progress.

    前端拿到 deploy_id 后立即连接此端点；后台管道延迟 0.3 秒后开始推送事件，
    确保 SSE 订阅已建立。超过 5 分钟无事件自动断开防止连接泄漏。
    """

    async def generate():
        timeout = 300  # 5 分钟超时
        async for event in event_bus.subscribe("deploy_progress"):
            if event.data.get("deploy_id") == deploy_id:
                yield event.format()
                if event.data.get("status") in ("success", "failed"):
                    break

    return StreamingResponse(generate(), media_type="text/event-stream")
