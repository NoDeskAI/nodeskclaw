"""Portal instance file management endpoints — read & write (instance admin only)."""

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.security import get_current_user
from app.models.instance_member import InstanceRole
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services import enterprise_file_service, instance_member_service

logger = logging.getLogger(__name__)

router = APIRouter()


class WriteFileRequest(BaseModel):
    path: str
    content: str


@router.get("/{instance_id}/files", response_model=ApiResponse)
async def list_files(
    instance_id: str,
    path: str = Query(default="", alias="path"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await instance_member_service.check_instance_access(
        instance_id, current_user, InstanceRole.admin, db
    )
    data = await enterprise_file_service.list_files_for_instance(instance_id, path, db)
    return ApiResponse(data=data)


@router.get("/{instance_id}/files/content", response_model=ApiResponse)
async def read_file_content(
    instance_id: str,
    path: str = Query(..., alias="path"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await instance_member_service.check_instance_access(
        instance_id, current_user, InstanceRole.admin, db
    )
    data = await enterprise_file_service.read_file_for_instance(instance_id, path, db)
    return ApiResponse(data=data)


@router.put("/{instance_id}/files/content", response_model=ApiResponse)
async def write_file_content(
    instance_id: str,
    body: WriteFileRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await instance_member_service.check_instance_access(
        instance_id, current_user, InstanceRole.admin, db
    )
    data = await enterprise_file_service.write_file_content(
        instance_id, body.path, body.content, db
    )
    return ApiResponse(data=data)


@router.get("/{instance_id}/files/download")
async def download_file(
    instance_id: str,
    path: str = Query(..., alias="path"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await instance_member_service.check_instance_access(
        instance_id, current_user, InstanceRole.admin, db
    )
    raw_bytes, filename, mime_type = await enterprise_file_service.download_file_for_instance(
        instance_id, path, db
    )
    filename_encoded = quote(filename, safe="")
    return Response(
        content=raw_bytes,
        media_type=mime_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename_encoded}",
            "Content-Length": str(len(raw_bytes)),
        },
    )
