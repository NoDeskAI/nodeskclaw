"""Organization management endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_org_admin, require_super_admin_dep
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.organization import (
    AddMemberRequest,
    MemberInfo,
    OAuthOrgSetupRequest,
    OrgCreate,
    OrgInfo,
    OrgUpdate,
    UpdateMemberRoleRequest,
)
from app.services import org_service

router = APIRouter()


# ── 组织 CRUD（超管） ────────────────────────────────────

@router.get("", response_model=ApiResponse[list[OrgInfo]])
async def list_organizations(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin_dep),
):
    """列出所有组织（超管）。"""
    data = await org_service.list_orgs(db)
    return ApiResponse(data=data)


@router.post("", response_model=ApiResponse[OrgInfo])
async def create_organization(
    body: OrgCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_super_admin_dep),
):
    """创建组织（超管）。"""
    data = await org_service.create_org(body, admin, db)
    return ApiResponse(data=data)


@router.get("/my", response_model=ApiResponse[list[OrgInfo]])
async def list_my_organizations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出当前用户所属的所有组织。"""
    data = await org_service.list_user_orgs(current_user, db)
    return ApiResponse(data=data)


@router.post("/switch/{org_id}", response_model=ApiResponse[OrgInfo])
async def switch_organization(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """切换当前组织。"""
    data = await org_service.switch_org(current_user, org_id, db)
    return ApiResponse(data=data)


@router.get("/{org_id}", response_model=ApiResponse[OrgInfo])
async def get_organization(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin_dep),
):
    """组织详情（超管）。"""
    org = await org_service.get_org(org_id, db)
    return ApiResponse(data=OrgInfo.model_validate(org))


@router.put("/{org_id}", response_model=ApiResponse[OrgInfo])
async def update_organization(
    org_id: str,
    body: OrgUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin_dep),
):
    """更新组织（超管）。"""
    data = await org_service.update_org(org_id, body, db)
    return ApiResponse(data=data)


@router.delete("/{org_id}", response_model=ApiResponse)
async def delete_organization(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin_dep),
):
    """删除组织（超管）。"""
    await org_service.delete_org(org_id, db)
    return ApiResponse(message="组织已删除")


# ── OAuth 自助开通 ─────────────────────────────────────────

@router.post("/oauth-setup", response_model=ApiResponse[OrgInfo])
async def oauth_org_setup(
    body: OAuthOrgSetupRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """OAuth 登录后首次开通组织：创建组织并绑定 OAuth 租户。"""
    data = await org_service.oauth_org_setup(current_user, body, db)
    return ApiResponse(data=data)


@router.post("/feishu-setup", response_model=ApiResponse[OrgInfo])
async def feishu_org_setup(
    body: OAuthOrgSetupRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """飞书开通组织（向后兼容别名）。"""
    if not body.provider:
        body.provider = "feishu"
    data = await org_service.oauth_org_setup(current_user, body, db)
    return ApiResponse(data=data)


# ── 成员管理 ─────────────────────────────────────────────

@router.get("/{org_id}/members", response_model=ApiResponse[list[MemberInfo]])
async def list_members(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _org_ctx: tuple = Depends(require_org_admin),
):
    """列出组织成员（组织管理员+）。"""
    data = await org_service.list_members(org_id, db)
    return ApiResponse(data=data)


@router.post("/{org_id}/members", response_model=ApiResponse[MemberInfo])
async def add_member(
    org_id: str,
    body: AddMemberRequest,
    db: AsyncSession = Depends(get_db),
    _org_ctx: tuple = Depends(require_org_admin),
):
    """添加成员（组织管理员+）。"""
    data = await org_service.add_member(org_id, body.user_id, body.role, db)
    return ApiResponse(data=data)


@router.put("/{org_id}/members/{membership_id}", response_model=ApiResponse[MemberInfo])
async def update_member_role(
    org_id: str,
    membership_id: str,
    body: UpdateMemberRoleRequest,
    db: AsyncSession = Depends(get_db),
    _org_ctx: tuple = Depends(require_org_admin),
):
    """修改成员角色（组织管理员+）。"""
    data = await org_service.update_member_role(org_id, membership_id, body.role, db)
    return ApiResponse(data=data)


@router.delete("/{org_id}/members/{membership_id}", response_model=ApiResponse)
async def remove_member(
    org_id: str,
    membership_id: str,
    db: AsyncSession = Depends(get_db),
    _org_ctx: tuple = Depends(require_org_admin),
):
    """移除成员（组织管理员+）。"""
    await org_service.remove_member(org_id, membership_id, db)
    return ApiResponse(message="成员已移除")
