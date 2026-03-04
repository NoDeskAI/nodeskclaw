"""Instance template API routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_org, get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.common import ApiResponse, PaginatedResponse, Pagination
from app.schemas.instance_template import (
    InstanceTemplateCreate,
    InstanceTemplateFromInstance,
    InstanceTemplateInfo,
    InstanceTemplateUpdate,
)
from app.services import instance_template_service as svc

router = APIRouter()


@router.get("/instance-templates", response_model=PaginatedResponse)
async def list_templates(
    keyword: str | None = Query(None),
    featured: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    org_info=Depends(get_current_org),
):
    user, org = org_info
    items, total = await svc.list_templates(
        db, org_id=org.id, keyword=keyword, featured_only=featured, page=page, page_size=page_size,
    )
    return PaginatedResponse(
        data=[item.model_dump(mode="json") for item in items],
        pagination=Pagination(page=page, page_size=page_size, total=total),
    )


@router.get("/instance-templates/featured", response_model=ApiResponse)
async def featured_templates(
    db: AsyncSession = Depends(get_db),
    org_info=Depends(get_current_org),
):
    user, org = org_info
    items, _ = await svc.list_templates(db, org_id=org.id, featured_only=True, page=1, page_size=10)
    return ApiResponse(data=[item.model_dump(mode="json") for item in items])


@router.get("/instance-templates/{template_id}", response_model=ApiResponse)
async def get_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    item = await svc.get_template(db, template_id)
    return ApiResponse(data=item.model_dump(mode="json"))


@router.post("/instance-templates", response_model=ApiResponse)
async def create_template(
    body: InstanceTemplateCreate,
    db: AsyncSession = Depends(get_db),
    org_info=Depends(get_current_org),
):
    user, org = org_info
    item = await svc.create_template(db, body, user_id=user.id, org_id=org.id)
    return ApiResponse(data=item.model_dump(mode="json"))


@router.post("/instance-templates/from-instance/{instance_id}", response_model=ApiResponse)
async def create_from_instance(
    instance_id: str,
    body: InstanceTemplateFromInstance,
    db: AsyncSession = Depends(get_db),
    org_info=Depends(get_current_org),
):
    user, org = org_info
    item = await svc.create_from_instance(db, instance_id, body, user_id=user.id, org_id=org.id)
    return ApiResponse(data=item.model_dump(mode="json"))


@router.put("/instance-templates/{template_id}", response_model=ApiResponse)
async def update_template(
    template_id: str,
    body: InstanceTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    item = await svc.update_template(db, template_id, body)
    return ApiResponse(data=item.model_dump(mode="json"))


@router.delete("/instance-templates/{template_id}", response_model=ApiResponse)
async def delete_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    result = await svc.delete_template(db, template_id)
    return ApiResponse(data=result)
