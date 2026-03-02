"""Portal enterprise file browsing endpoints — read-only."""

import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_org_admin
from app.schemas.common import ApiResponse
from app.services import enterprise_file_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/agents", response_model=ApiResponse)
async def list_agents(
    auth: tuple = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    user, org = auth
    data = await enterprise_file_service.list_browsable_agents(org.id, db)
    return ApiResponse(data=data)


@router.get("/agents/{instance_id}/files", response_model=ApiResponse)
async def list_files(
    instance_id: str,
    path: str = Query(default=".openclaw", alias="path"),
    auth: tuple = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    user, org = auth
    data = await enterprise_file_service.list_files(instance_id, path, org.id, db)
    return ApiResponse(data=data)


@router.get("/agents/{instance_id}/files/content", response_model=ApiResponse)
async def read_file_content(
    instance_id: str,
    path: str = Query(..., alias="path"),
    auth: tuple = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    user, org = auth
    data = await enterprise_file_service.read_file_content(instance_id, path, org.id, db)
    return ApiResponse(data=data)


@router.get("/agents/{instance_id}/files/download")
async def download_file(
    instance_id: str,
    path: str = Query(..., alias="path"),
    auth: tuple = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    user, org = auth
    content, filename = await enterprise_file_service.download_file(
        instance_id, path, org.id, db
    )
    return PlainTextResponse(
        content=content,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
