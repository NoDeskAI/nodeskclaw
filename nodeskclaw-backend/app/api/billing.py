"""Billing & plan endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_org_admin, require_org_member
from app.models.organization import Organization
from app.models.user import User
from app.schemas.billing import OrgUsage, PlanInfo, UpgradeRequest
from app.schemas.common import ApiResponse
from app.schemas.organization import OrgInfo
from app.services import billing_service

router = APIRouter()


@router.get("/plans", response_model=ApiResponse[list[PlanInfo]])
async def list_plans(
    db: AsyncSession = Depends(get_db),
    _org_ctx: tuple[User, Organization] = Depends(require_org_member),
):
    """列出所有可用套餐。"""
    data = await billing_service.list_plans(db)
    return ApiResponse(data=data)


@router.get("/current", response_model=ApiResponse[OrgInfo])
async def get_current_plan(
    org_ctx: tuple[User, Organization] = Depends(require_org_member),
):
    """获取当前组织的套餐信息。"""
    _, org = org_ctx
    return ApiResponse(data=OrgInfo.model_validate(org))


@router.get("/usage", response_model=ApiResponse[OrgUsage])
async def get_usage(
    db: AsyncSession = Depends(get_db),
    org_ctx: tuple[User, Organization] = Depends(require_org_member),
):
    """获取当前组织资源使用量。"""
    _, org = org_ctx
    data = await billing_service.get_org_usage(org, db)
    return ApiResponse(data=data)


@router.post("/upgrade", response_model=ApiResponse[OrgInfo])
async def upgrade_plan(
    body: UpgradeRequest,
    db: AsyncSession = Depends(get_db),
    org_ctx: tuple[User, Organization] = Depends(require_org_admin),
):
    """升级套餐（组织管理员+）。"""
    _, org = org_ctx
    updated_org = await billing_service.upgrade_org_plan(org, body.plan_name, db)
    return ApiResponse(data=OrgInfo.model_validate(updated_org))
