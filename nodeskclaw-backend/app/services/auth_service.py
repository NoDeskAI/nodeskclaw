"""Auth service: Feishu SSO, email/password, phone/SMS login, JWT management."""

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.user import User, UserRole
from app.schemas.auth import LoginResponse, TokenResponse, UserInfo
from app.utils.feishu import exchange_code_for_user

logger = logging.getLogger(__name__)

# 简易内存 SMS 验证码存储（生产环境应使用 Redis）
_sms_codes: dict[str, tuple[str, float]] = {}  # phone -> (code, expire_ts)


async def feishu_login(code: str, db: AsyncSession, redirect_uri: str | None = None) -> LoginResponse:
    """
    飞书 SSO 回调处理：
    1. code 换取用户信息（含 tenant_key）
    2. Upsert 用户记录，存储 feishu_tenant_key
    3. 用 tenant_key 查组织：找到则自动加入，未找到则标记 needs_org_setup
    4. 签发 JWT
    """
    from app.models.org_membership import OrgMembership, OrgRole
    from app.models.organization import Organization

    feishu_user = await exchange_code_for_user(code, redirect_uri=redirect_uri)
    tenant_key = feishu_user.get("tenant_key")

    result = await db.execute(
        select(User).where(User.feishu_uid == feishu_user["open_id"], User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            feishu_uid=feishu_user["open_id"],
            name=feishu_user["name"],
            email=feishu_user.get("email"),
            avatar_url=feishu_user.get("avatar_url"),
            feishu_tenant_key=tenant_key,
            role=UserRole.user,
        )
        db.add(user)
    else:
        user.name = feishu_user["name"]
        user.email = feishu_user.get("email")
        user.avatar_url = feishu_user.get("avatar_url")
        if tenant_key:
            user.feishu_tenant_key = tenant_key

    user.last_login_at = datetime.now(timezone.utc)

    needs_org_setup = False

    if tenant_key:
        org_result = await db.execute(
            select(Organization).where(
                Organization.feishu_tenant_key == tenant_key,
                Organization.deleted_at.is_(None),
            )
        )
        org = org_result.scalar_one_or_none()

        if org is not None:
            await db.flush()
            existing_membership = await db.execute(
                select(OrgMembership).where(
                    OrgMembership.user_id == user.id,
                    OrgMembership.org_id == org.id,
                    OrgMembership.deleted_at.is_(None),
                )
            )
            if existing_membership.scalar_one_or_none() is None:
                db.add(OrgMembership(user_id=user.id, org_id=org.id, role=OrgRole.member))
            user.current_org_id = org.id
        else:
            needs_org_setup = True
    else:
        needs_org_setup = True

    await db.commit()
    await db.refresh(user)

    return LoginResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=UserInfo.model_validate(user),
        needs_org_setup=needs_org_setup,
    )


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
    """简单但安全的密码哈希（PBKDF2-SHA256）。"""
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


def _issue_tokens(user: User) -> LoginResponse:
    return LoginResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=UserInfo.model_validate(user),
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

    # 自动加入默认组织
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
    await db.refresh(user)
    logger.info("邮箱注册: %s", email)
    return _issue_tokens(user)


async def login_with_email(email: str, password: str, db: AsyncSession) -> LoginResponse:
    """邮箱密码登录。"""
    result = await db.execute(
        select(User).where(User.email == email, User.deleted_at.is_(None))
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
    return _issue_tokens(user)


# ── 手机验证码登录 ───────────────────────────────────────

async def send_sms_code(phone: str) -> dict:
    """发送验证码（当前为 mock，生产环境接真实 SMS 服务）。"""
    import time

    # 频率限制：60 秒内不能重复发送
    if phone in _sms_codes:
        _, expire_ts = _sms_codes[phone]
        remaining = expire_ts - time.time()
        if remaining > 240:  # 300 - 60 = 240
            raise HTTPException(
                status_code=429,
                detail={
                    "error_code": 42920,
                    "message_key": "errors.auth.sms_send_too_frequent",
                    "message": "发送过于频繁，请稍后再试",
                },
            )

    code = f"{secrets.randbelow(900000) + 100000}"
    _sms_codes[phone] = (code, time.time() + 300)  # 5 分钟过期

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

    # 验证通过，清除
    _sms_codes.pop(phone, None)

    # 查找或创建用户
    result = await db.execute(
        select(User).where(User.phone == phone, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            name=f"用户{phone[-4:]}",
            phone=phone,
            role=UserRole.user,
        )
        db.add(user)

        # 自动加入默认组织
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
    await db.refresh(user)
    logger.info("手机登录: %s", phone)
    return _issue_tokens(user)
