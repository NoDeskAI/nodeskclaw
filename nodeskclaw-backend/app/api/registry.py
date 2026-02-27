"""Registry endpoints: list available image tags."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.registry_service import list_image_tags

router = APIRouter()


@router.get("/tags", response_model=ApiResponse[list[dict]])
async def get_image_tags(
    registry_url: str | None = Query(None, description="可选，覆盖数据库中的镜像仓库地址配置"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """从 Docker Registry 获取可用镜像 Tag 列表。"""
    tags = await list_image_tags(db, registry_url)
    return ApiResponse(data=tags)
