"""Admin platform member management API."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_org_role
from app.models.admin_membership import AdminMembership
from app.models.org_membership import ADMIN_ROLE_LEVEL
from app.models.user import User
from app.schemas.admin import (
    AddAdminMemberRequest,
    AdminMemberInfo,
    UpdateAdminMemberRoleRequest,
)
from app.schemas.common import ApiResponse

router = APIRouter()

VALID_ROLES = set(ADMIN_ROLE_LEVEL.keys())


def _to_info(m: AdminMembership, user: User) -> AdminMemberInfo:
    return AdminMemberInfo(
        id=m.id,
        user_id=m.user_id,
        org_id=m.org_id,
        role=m.role,
        user_name=user.name,
        user_email=user.email,
        user_avatar_url=user.avatar_url,
        created_at=m.created_at,
    )


@router.get("", response_model=ApiResponse[list[AdminMemberInfo]])
async def list_admin_members(
    q: str | None = Query(None, description="按名称/邮箱模糊搜索"),
    user_org=Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    _user, org = user_org
    stmt = (
        select(AdminMembership, User)
        .join(User, AdminMembership.user_id == User.id)
        .where(
            AdminMembership.org_id == org.id,
            AdminMembership.deleted_at.is_(None),
            User.deleted_at.is_(None),
        )
    )
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(User.name.ilike(pattern) | User.email.ilike(pattern))
    stmt = stmt.order_by(AdminMembership.created_at.desc())
    result = await db.execute(stmt)
    items = [_to_info(m, u) for m, u in result.all()]
    return ApiResponse(data=items)


@router.post("", response_model=ApiResponse[AdminMemberInfo], status_code=201)
async def add_admin_member(
    body: AddAdminMemberRequest,
    user_org=Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    _user, org = user_org

    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": 40030,
                "message_key": "errors.admin.invalid_role",
                "message": f"无效的角色: {body.role}",
            },
        )

    existing = await db.execute(
        select(AdminMembership).where(
            AdminMembership.user_id == body.user_id,
            AdminMembership.org_id == org.id,
            AdminMembership.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": 40930,
                "message_key": "errors.admin.member_already_exists",
                "message": "该用户已拥有管理平台权限",
            },
        )

    target_user_result = await db.execute(
        select(User).where(User.id == body.user_id, User.deleted_at.is_(None))
    )
    target_user = target_user_result.scalar_one_or_none()
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": 40430,
                "message_key": "errors.admin.user_not_found",
                "message": "用户不存在",
            },
        )

    membership = AdminMembership(
        user_id=body.user_id,
        org_id=org.id,
        role=body.role,
    )
    db.add(membership)
    await db.commit()
    await db.refresh(membership)
    return ApiResponse(data=_to_info(membership, target_user))


@router.put("/{member_id}", response_model=ApiResponse[AdminMemberInfo])
async def update_admin_member_role(
    member_id: str,
    body: UpdateAdminMemberRoleRequest,
    user_org=Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    _user, org = user_org

    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": 40030,
                "message_key": "errors.admin.invalid_role",
                "message": f"无效的角色: {body.role}",
            },
        )

    result = await db.execute(
        select(AdminMembership).where(
            AdminMembership.id == member_id,
            AdminMembership.org_id == org.id,
            AdminMembership.deleted_at.is_(None),
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": 40431,
                "message_key": "errors.admin.member_not_found",
                "message": "管理平台成员不存在",
            },
        )

    membership.role = body.role
    await db.commit()
    await db.refresh(membership)

    user_result = await db.execute(select(User).where(User.id == membership.user_id))
    target_user = user_result.scalar_one()
    return ApiResponse(data=_to_info(membership, target_user))


@router.delete("/{member_id}", response_model=ApiResponse)
async def remove_admin_member(
    member_id: str,
    user_org=Depends(require_org_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    current_user, org = user_org

    result = await db.execute(
        select(AdminMembership).where(
            AdminMembership.id == member_id,
            AdminMembership.org_id == org.id,
            AdminMembership.deleted_at.is_(None),
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": 40431,
                "message_key": "errors.admin.member_not_found",
                "message": "管理平台成员不存在",
            },
        )

    if membership.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": 40031,
                "message_key": "errors.admin.cannot_remove_self",
                "message": "不能移除自己的管理平台权限",
            },
        )

    membership.deleted_at = func.now()
    await db.commit()
    return ApiResponse(message="已移除管理平台权限")
