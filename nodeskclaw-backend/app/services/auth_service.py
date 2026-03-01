"""Auth service: OAuth (generic), email/password, phone/SMS login, JWT management."""

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.user import User, UserRole
from app.schemas.auth import LoginResponse, TokenResponse, UserInfo
from app.utils.oauth_providers import get_provider

logger = logging.getLogger(__name__)

_sms_codes: dict[str, tuple[str, float]] = {}


async def oauth_login(
    provider_name: str, code: str, db: AsyncSession,
    redirect_uri: str | None = None, client_id: str | None = None,
) -> LoginResponse:
    """
    通用 OAuth 登录：
    1. 通过 provider registry 用 code 换取用户信息
    2. 按 (provider, provider_user_id) 查 OAuthConnection → 找到 User 或创建新 User
    3. 按 (provider, provider_tenant_id) 查 OrgOAuthBinding → 自动加入组织或标记 needs_org_setup
    4. 签发 JWT
    """
    from app.models.oauth_connection import UserOAuthConnection
    from app.models.org_membership import OrgMembership, OrgRole
    from app.models.org_oauth_binding import OrgOAuthBinding

    provider = get_provider(provider_name)
    oauth_info = await provider.exchange_code(code, redirect_uri, client_id=client_id)

    conn_result = await db.execute(
        select(UserOAuthConnection)
        .where(
            UserOAuthConnection.provider == oauth_info.provider,
            UserOAuthConnection.provider_user_id == oauth_info.provider_user_id,
            UserOAuthConnection.deleted_at.is_(None),
        )
    )
    connection = conn_result.scalar_one_or_none()

    if connection is not None:
        user_result = await db.execute(
            select(User)
            .options(selectinload(User.oauth_connections))
            .where(User.id == connection.user_id, User.deleted_at.is_(None))
        )
        user = user_result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error_code": 40106,
                    "message_key": "errors.auth.user_not_found_or_disabled",
                    "message": "用户不存在或已禁用",
                },
            )
        user.name = oauth_info.name
        if oauth_info.email:
            user.email = oauth_info.email
        if oauth_info.avatar_url:
            user.avatar_url = oauth_info.avatar_url
        if oauth_info.provider_tenant_id:
            connection.provider_tenant_id = oauth_info.provider_tenant_id
    else:
        user = User(
            name=oauth_info.name,
            email=oauth_info.email,
            avatar_url=oauth_info.avatar_url,
            role=UserRole.user,
        )
        db.add(user)
        await db.flush()

        connection = UserOAuthConnection(
            user_id=user.id,
            provider=oauth_info.provider,
            provider_user_id=oauth_info.provider_user_id,
            provider_tenant_id=oauth_info.provider_tenant_id,
        )
        db.add(connection)

    user.last_login_at = datetime.now(timezone.utc)

    needs_org_setup = False
    tenant_id = oauth_info.provider_tenant_id

    if tenant_id:
        binding_result = await db.execute(
            select(OrgOAuthBinding).where(
                OrgOAuthBinding.provider == oauth_info.provider,
                OrgOAuthBinding.provider_tenant_id == tenant_id,
                OrgOAuthBinding.deleted_at.is_(None),
            )
        )
        binding = binding_result.scalar_one_or_none()

        if binding is not None:
            await db.flush()
            existing_membership = await db.execute(
                select(OrgMembership).where(
                    OrgMembership.user_id == user.id,
                    OrgMembership.org_id == binding.org_id,
                    OrgMembership.deleted_at.is_(None),
                )
            )
            if existing_membership.scalar_one_or_none() is None:
                db.add(OrgMembership(user_id=user.id, org_id=binding.org_id, role=OrgRole.member))
            user.current_org_id = binding.org_id
        else:
            needs_org_setup = True
    else:
        needs_org_setup = True

    await db.commit()

    refreshed = await db.execute(
        select(User)
        .options(selectinload(User.oauth_connections))
        .where(User.id == user.id)
    )
    user = refreshed.scalar_one()

    user_info = await _build_user_info(user, db)
    return LoginResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=user_info,
        needs_org_setup=needs_org_setup,
        provider=oauth_info.provider,
    )


async def feishu_login(
    code: str, db: AsyncSession, redirect_uri: str | None = None, client_id: str | None = None,
) -> LoginResponse:
    """向后兼容别名。"""
    return await oauth_login("feishu", code, db, redirect_uri, client_id=client_id)


async def refresh_tokens(refresh_token_str: str, db: AsyncSession) -> TokenResponse:
    """Validate refresh token, issue new token pair."""
    payload = decode_token(refresh_token_str)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": 40102,
                "message_key": "errors.auth.token_type_invalid",
                "message": "Token 类型错误",
            },
        )

    user_id = payload.get("sub")
    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": 40105,
                "message_key": "errors.auth.user_not_found_or_disabled",
                "message": "用户不存在或已禁用",
            },
        )

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


# ── 密码工具 ────────────────────────────────────────────

def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"{salt}${dk.hex()}"


def _verify_password(password: str, hashed: str) -> bool:
    parts = hashed.split("$", 1)
    if len(parts) != 2:
        return False
    salt, stored_dk = parts
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return hmac.compare_digest(dk.hex(), stored_dk)


async def _build_user_info(user: User, db: AsyncSession) -> UserInfo:
    """构建包含 org_role（管理平台角色）的 UserInfo。"""
    from app.models.admin_membership import AdminMembership

    info = UserInfo.model_validate(user)
    if user.current_org_id:
        result = await db.execute(
            select(AdminMembership.role).where(
                AdminMembership.user_id == user.id,
                AdminMembership.org_id == user.current_org_id,
                AdminMembership.deleted_at.is_(None),
            )
        )
        info.org_role = result.scalar_one_or_none()
    return info


async def _issue_tokens(user: User, db: AsyncSession) -> LoginResponse:
    user_info = await _build_user_info(user, db)
    return LoginResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=user_info,
    )


# ── 邮箱密码注册 / 登录 ─────────────────────────────────

async def register_with_email(
    email: str, password: str, name: str, db: AsyncSession
) -> LoginResponse:
    """邮箱密码注册，自动登录。"""
    if len(password) < 6:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": 40020,
                "message_key": "errors.auth.password_too_short",
                "message": "密码至少 6 位",
            },
        )

    exists = await db.execute(
        select(User).where(User.email == email, User.deleted_at.is_(None))
    )
    if exists.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": 40920,
                "message_key": "errors.auth.email_already_registered",
                "message": "该邮箱已注册",
            },
        )

    user = User(
        name=name or email.split("@")[0],
        email=email,
        password_hash=_hash_password(password),
        role=UserRole.user,
    )
    db.add(user)

    from app.models.org_membership import OrgMembership, OrgRole
    from app.models.organization import Organization
    org_result = await db.execute(
        select(Organization).where(Organization.slug.in_(["nodesk-ai", "default"]), Organization.deleted_at.is_(None))
    )
    default_org = org_result.scalar_one_or_none()
    if default_org:
        await db.flush()
        membership = OrgMembership(user_id=user.id, org_id=default_org.id, role=OrgRole.member)
        db.add(membership)
        user.current_org_id = default_org.id

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    refreshed = await db.execute(
        select(User).options(selectinload(User.oauth_connections)).where(User.id == user.id)
    )
    user = refreshed.scalar_one()
    logger.info("邮箱注册: %s", email)
    return await _issue_tokens(user, db)


async def login_with_email(email: str, password: str, db: AsyncSession) -> LoginResponse:
    """邮箱密码登录。"""
    result = await db.execute(
        select(User).options(selectinload(User.oauth_connections)).where(User.email == email, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None or not user.password_hash:
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": 40120,
                "message_key": "errors.auth.invalid_email_or_password",
                "message": "邮箱或密码错误",
            },
        )
    if not _verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": 40120,
                "message_key": "errors.auth.invalid_email_or_password",
                "message": "邮箱或密码错误",
            },
        )
    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": 40320,
                "message_key": "errors.auth.account_disabled",
                "message": "账户已被禁用",
            },
        )

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    return await _issue_tokens(user, db)


# ── 手机验证码登录 ───────────────────────────────────────

async def send_sms_code(phone: str) -> dict:
    """发送验证码（当前为 mock，生产环境接真实 SMS 服务）。"""
    import time

    if phone in _sms_codes:
        _, expire_ts = _sms_codes[phone]
        remaining = expire_ts - time.time()
        if remaining > 240:
            raise HTTPException(
                status_code=429,
                detail={
                    "error_code": 42920,
                    "message_key": "errors.auth.sms_send_too_frequent",
                    "message": "发送过于频繁，请稍后再试",
                },
            )

    code = f"{secrets.randbelow(900000) + 100000}"
    _sms_codes[phone] = (code, time.time() + 300)

    # TODO: 接入真实 SMS 服务（阿里云/腾讯云短信）
    logger.info("SMS 验证码 [%s]: %s (mock)", phone, code)

    return {"sent": True, "message": "验证码已发送"}


async def login_with_phone(phone: str, code: str, db: AsyncSession) -> LoginResponse:
    """手机号验证码登录（不存在则自动注册）。"""
    import time

    stored = _sms_codes.get(phone)
    if stored is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": 40021,
                "message_key": "errors.auth.sms_code_not_requested",
                "message": "请先获取验证码",
            },
        )

    stored_code, expire_ts = stored
    if time.time() > expire_ts:
        _sms_codes.pop(phone, None)
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": 40022,
                "message_key": "errors.auth.sms_code_expired",
                "message": "验证码已过期",
            },
        )
    if stored_code != code:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": 40023,
                "message_key": "errors.auth.sms_code_invalid",
                "message": "验证码错误",
            },
        )

    _sms_codes.pop(phone, None)

    result = await db.execute(
        select(User).options(selectinload(User.oauth_connections)).where(User.phone == phone, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            name=f"用户{phone[-4:]}",
            phone=phone,
            role=UserRole.user,
        )
        db.add(user)

        from app.models.org_membership import OrgMembership, OrgRole
        from app.models.organization import Organization
        org_result = await db.execute(
            select(Organization).where(Organization.slug.in_(["nodesk-ai", "default"]), Organization.deleted_at.is_(None))
        )
        default_org = org_result.scalar_one_or_none()
        if default_org:
            await db.flush()
            membership = OrgMembership(user_id=user.id, org_id=default_org.id, role=OrgRole.member)
            db.add(membership)
            user.current_org_id = default_org.id

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": 40320,
                "message_key": "errors.auth.account_disabled",
                "message": "账户已被禁用",
            },
        )

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    refreshed = await db.execute(
        select(User).options(selectinload(User.oauth_connections)).where(User.id == user.id)
    )
    user = refreshed.scalar_one()
    logger.info("手机登录: %s", phone)
    return await _issue_tokens(user, db)
