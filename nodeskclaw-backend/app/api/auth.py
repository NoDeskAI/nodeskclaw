"""Auth endpoints: OAuth, email/password, phone/SMS, token refresh, user info, logout, user management."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core import hooks
from app.core.deps import get_db, require_feature, require_super_admin_dep
from app.core.security import get_current_user, get_current_user_unchecked
from app.models.user import User
from app.schemas.auth import (
    AccountLoginRequest,
    ChangePasswordRequest,
    EmailLoginRequest,
    FeishuCallbackRequest,
    LoginResponse,
    OAuthCallbackRequest,
    RefreshTokenRequest,
    SmsLoginRequest,
    SmsSendRequest,
    TokenResponse,
    UserInfo,
    VerificationCodeLoginRequest,
    VerificationCodeSendRequest,
)
from app.schemas.common import ApiResponse
from app.services import auth_service

router = APIRouter()


# ── OAuth 通用回调 ────────────────────────────────────────

@router.post("/oauth/callback", response_model=ApiResponse[LoginResponse])
async def oauth_callback(body: OAuthCallbackRequest, db: AsyncSession = Depends(get_db)):
    """通用 OAuth 回调：provider + code 换取 JWT。"""
    result = await auth_service.oauth_login(
        body.provider, body.code, db, redirect_uri=body.redirect_uri, client_id=body.client_id
    )
    await hooks.emit("operation_audit", action="auth.login", target_type="user", target_id=result.user.id, actor_id=result.user.id, details={"method": "oauth"})
    return ApiResponse(data=result)


@router.post("/feishu/callback", response_model=ApiResponse[LoginResponse])
async def feishu_callback(body: FeishuCallbackRequest, db: AsyncSession = Depends(get_db)):
    """飞书 SSO 回调（向后兼容别名）。"""
    result = await auth_service.oauth_login(
        "feishu", body.code, db, redirect_uri=body.redirect_uri, client_id=body.client_id
    )
    await hooks.emit("operation_audit", action="auth.login", target_type="user", target_id=result.user.id, actor_id=result.user.id, details={"method": "feishu"})
    return ApiResponse(data=result)


# ── 邮箱密码 ─────────────────────────────────────────────

@router.post("/login", response_model=ApiResponse[LoginResponse])
async def email_login(body: EmailLoginRequest, db: AsyncSession = Depends(get_db)):
    """邮箱密码登录。"""
    result = await auth_service.login_with_email(body.email, body.password, db)
    await hooks.emit("operation_audit", action="auth.login", target_type="user", target_id=result.user.id, actor_id=result.user.id, details={"method": "email"})
    return ApiResponse(data=result)


# ── 手机验证码 ───────────────────────────────────────────

@router.post("/sms/send", response_model=ApiResponse)
async def sms_send(body: SmsSendRequest):
    """发送手机验证码。"""
    result = await auth_service.send_sms_code(body.phone)
    return ApiResponse(data=result, message=result["message"])


@router.post("/sms/login", response_model=ApiResponse[LoginResponse])
async def sms_login(body: SmsLoginRequest, db: AsyncSession = Depends(get_db)):
    """手机验证码登录（自动注册）。"""
    result = await auth_service.login_with_phone(body.phone, body.code, db)
    await hooks.emit("operation_audit", action="auth.login", target_type="user", target_id=result.user.id, actor_id=result.user.id, details={"method": "sms"})
    return ApiResponse(data=result)


@router.post("/refresh", response_model=ApiResponse[TokenResponse])
async def refresh(body: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """刷新 Token。"""
    result = await auth_service.refresh_tokens(body.refresh_token, db)
    return ApiResponse(data=result)


@router.get("/me", response_model=ApiResponse[UserInfo])
async def me(
    current_user: User = Depends(get_current_user_unchecked),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户信息（含管理平台角色和组织成员角色）。"""
    from app.models.admin_membership import AdminMembership
    from app.models.org_membership import OrgMembership

    info = UserInfo.model_validate(current_user)
    info.has_password = bool(current_user.password_hash)
    if current_user.current_org_id:
        result = await db.execute(
            select(AdminMembership.role).where(
                AdminMembership.user_id == current_user.id,
                AdminMembership.org_id == current_user.current_org_id,
                AdminMembership.deleted_at.is_(None),
            )
        )
        info.org_role = result.scalar_one_or_none()

        result = await db.execute(
            select(OrgMembership.role).where(
                OrgMembership.user_id == current_user.id,
                OrgMembership.org_id == current_user.current_org_id,
                OrgMembership.deleted_at.is_(None),
            )
        )
        info.portal_org_role = result.scalar_one_or_none()
    return ApiResponse(data=info)


@router.put("/me/password", response_model=ApiResponse)
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user_unchecked),
    db: AsyncSession = Depends(get_db),
):
    await auth_service.change_password(
        current_user.id, body.old_password, body.new_password, db,
    )
    await hooks.emit("operation_audit", action="auth.password_changed", target_type="user", target_id=current_user.id, actor_id=current_user.id, details={})
    return ApiResponse(message="密码已更新")


@router.post("/logout", response_model=ApiResponse)
async def logout(current_user: User = Depends(get_current_user_unchecked)):
    """登出（客户端清除 Token 即可，服务端无需额外操作）。"""
    await hooks.emit("operation_audit", action="auth.logout", target_type="user", target_id=current_user.id, actor_id=current_user.id, details={})
    return ApiResponse(message="已登出")


@router.get("/users", response_model=ApiResponse[list[UserInfo]],
             dependencies=[Depends(require_feature("platform_admin"))])
async def list_users(
    q: str | None = Query(None, description="按名称/邮箱/手机号模糊搜索"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin_dep),
):
    """列出所有用户（超管），支持模糊搜索。"""
    stmt = select(User).options(selectinload(User.oauth_connections)).where(User.deleted_at.is_(None))
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                User.name.ilike(pattern),
                User.email.ilike(pattern),
                User.phone.ilike(pattern),
            )
        )
    stmt = stmt.order_by(User.created_at.desc())
    result = await db.execute(stmt)
    users = [UserInfo.model_validate(u) for u in result.scalars().all()]
    return ApiResponse(data=users)


# ── 运维人员管理 ─────────────────────────────────────────

@router.get("/staff", response_model=ApiResponse[list[UserInfo]],
             dependencies=[Depends(require_feature("platform_admin"))])
async def list_staff(
    q: str | None = Query(None, description="按名称/邮箱模糊搜索"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin_dep),
):
    """列出运维人员（is_super_admin=True）。"""
    stmt = select(User).options(selectinload(User.oauth_connections)).where(User.deleted_at.is_(None), User.is_super_admin.is_(True))
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                User.name.ilike(pattern),
                User.email.ilike(pattern),
            )
        )
    stmt = stmt.order_by(User.created_at.desc())
    result = await db.execute(stmt)
    staff = [UserInfo.model_validate(u) for u in result.scalars().all()]
    return ApiResponse(data=staff)


@router.put("/staff/{user_id}", response_model=ApiResponse[UserInfo],
             dependencies=[Depends(require_feature("platform_admin"))])
async def update_staff(
    user_id: str,
    is_super_admin: bool | None = Query(None),
    is_active: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_super_admin_dep),
):
    """设置/取消超管、启用/禁用运维人员。"""
    result = await db.execute(
        select(User).options(selectinload(User.oauth_connections)).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user.id == current_user.id and is_super_admin is False:
        raise HTTPException(status_code=400, detail="不能取消自己的超管权限")

    if is_super_admin is not None:
        user.is_super_admin = is_super_admin
    if is_active is not None:
        user.is_active = is_active

    await db.commit()
    await db.refresh(user)
    await hooks.emit("operation_audit", action="auth.staff_updated", target_type="user", target_id=user_id, actor_id=current_user.id, details={"is_super_admin": user.is_super_admin, "is_active": user.is_active})
    return ApiResponse(data=UserInfo.model_validate(user))


# ── 统一认证端点 ──────────────────────────────────────────


@router.post("/account-login", response_model=ApiResponse[LoginResponse])
async def account_login(
    body: AccountLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await auth_service.login_with_account(body.account, body.password, db)
    await hooks.emit("operation_audit", action="auth.login", target_type="user", target_id=result.user.id, actor_id=result.user.id, details={"method": "account"})
    return ApiResponse(data=result)


@router.post("/verification-code/send", response_model=ApiResponse)
async def send_verification_code(
    body: VerificationCodeSendRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await auth_service.send_verification_code(body.account, db)
    return ApiResponse(data=result)


@router.post("/verification-code/login", response_model=ApiResponse[LoginResponse])
async def verification_code_login(
    body: VerificationCodeLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await auth_service.login_with_verification_code(body.account, body.code, db)
    await hooks.emit("operation_audit", action="auth.login", target_type="user", target_id=result.user.id, actor_id=result.user.id, details={"method": "verification_code"})
    return ApiResponse(data=result)
