"""Deploy endpoints: precheck, deploy, SSE progress stream."""

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.deploy import DeployProgress, DeployRequest, PrecheckResult
from app.services import deploy_service
from app.services.k8s.event_bus import event_bus

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
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行部署（异步，通过 SSE 推送进度）。"""
    deploy_id = await deploy_service.deploy_instance(body, current_user, db)
    return ApiResponse(data={"deploy_id": deploy_id})


@router.get("/progress/{deploy_id}")
async def deploy_progress_stream(deploy_id: str):
    """SSE stream for deploy progress."""

    async def generate():
        async for event in event_bus.subscribe("deploy_progress"):
            if event.data.get("deploy_id") == deploy_id:
                yield event.format()
                if event.data.get("status") in ("success", "failed"):
                    break

    return StreamingResponse(generate(), media_type="text/event-stream")
