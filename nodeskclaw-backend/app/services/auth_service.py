"""Auth service: email/password, phone/SMS login, JWT management."""

import hashlib
import hmac
import logging
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.user import User, UserRole
from app.schemas.auth import LoginResponse, TokenResponse, UserInfo

logger = logging.getLogger(__name__)

_verification_codes: dict[str, tuple[str, float]] = {}


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
    """构建包含 org_role（管理平台角色）和 portal_org_role（组织成员角色）的 UserInfo。"""
    from app.models.admin_membership import AdminMembership
    from app.models.org_membership import OrgMembership

    info = UserInfo.model_validate(user)
    info.has_password = bool(user.password_hash)
    if user.current_org_id:
        result = await db.execute(
            select(AdminMembership.role).where(
                AdminMembership.user_id == user.id,
                AdminMembership.org_id == user.current_org_id,
                AdminMembership.deleted_at.is_(None),
            )
        )
        info.org_role = result.scalar_one_or_none()

        result = await db.execute(
            select(OrgMembership.role).where(
                OrgMembership.user_id == user.id,
                OrgMembership.org_id == user.current_org_id,
                OrgMembership.deleted_at.is_(None),
            )
        )
        info.portal_org_role = result.scalar_one_or_none()
    return info


async def _issue_tokens(user: User, db: AsyncSession) -> LoginResponse:
    user_info = await _build_user_info(user, db)
    return LoginResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=user_info,
    )


# ── 邮箱域名白名单 ────────────────────────────────────────

def _check_email_domain_allowed(email: str) -> None:
    raw = settings.LOGIN_EMAIL_WHITELIST.strip()
    if not raw:
        return
    allowed = [d.strip().lower() for d in raw.split(",") if d.strip()]
    if not allowed:
        return
    domain = email.rsplit("@", 1)[-1].lower()
    if domain not in allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": 40330,
                "message_key": "errors.auth.email_domain_not_allowed",
                "message": "当前邮箱域名不在允许范围内",
            },
        )


# ── 邮箱密码登录 ──────────────────────────────────────────

async def login_with_email(email: str, password: str, db: AsyncSession) -> LoginResponse:
    """邮箱密码登录。"""
    _check_email_domain_allowed(email)
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
    raise HTTPException(
        status_code=503,
        detail={
            "error_code": 50320,
            "message_key": "errors.auth.sms_not_available",
            "message": "当前环境未接入短信验证码服务",
        },
    )


async def login_with_phone(phone: str, code: str, db: AsyncSession) -> LoginResponse:
    """手机号验证码登录（不存在则自动注册）。"""
    raise HTTPException(
        status_code=503,
        detail={
            "error_code": 50320,
            "message_key": "errors.auth.sms_not_available",
            "message": "当前环境未接入短信验证码服务",
        },
    )


# ── 修改密码 ─────────────────────────────────────────────

async def change_password(
    user_id: str, old_password: str | None, new_password: str, db: AsyncSession
) -> None:
    if len(new_password) < 6:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": 40020,
                "message_key": "errors.auth.password_too_short",
                "message": "密码至少 6 位",
            },
        )

    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundError("用户不存在", "errors.auth.user_not_found_or_disabled")

    if user.password_hash and not user.must_change_password:
        if not old_password:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": 40024,
                    "message_key": "errors.auth.old_password_required",
                    "message": "请输入当前密码",
                },
            )
        if not _verify_password(old_password, user.password_hash):
            raise HTTPException(
                status_code=401,
                detail={
                    "error_code": 40121,
                    "message_key": "errors.auth.wrong_password",
                    "message": "当前密码错误",
                },
            )

    user.password_hash = _hash_password(new_password)
    user.must_change_password = False
    await db.commit()
    logger.info("密码修改: user_id=%s", user_id)


# ── 统一认证 ─────────────────────────────────────────────


def _detect_account_type(account: str) -> Literal["email", "phone", "username"]:
    if "@" in account:
        return "email"
    if re.match(r"^\+?\d{7,15}$", account):
        return "phone"
    return "username"


async def _login_by_field(
    field_value: str, password: str, db: AsyncSession,
    *, where_clause,
) -> LoginResponse:
    result = await db.execute(
        select(User)
        .options(selectinload(User.oauth_connections))
        .where(where_clause, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None or not user.password_hash:
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": 40120,
                "message_key": "errors.auth.invalid_account_or_password",
                "message": "账号或密码错误",
            },
        )
    if not _verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": 40120,
                "message_key": "errors.auth.invalid_account_or_password",
                "message": "账号或密码错误",
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


async def login_with_account(
    account: str, password: str, db: AsyncSession
) -> LoginResponse:
    """Unified account+password login. Auto-detects email vs phone vs username."""
    account_type = _detect_account_type(account)

    if account_type == "email":
        return await login_with_email(account, password, db)

    if account_type == "phone":
        return await _login_by_field(account, password, db, where_clause=User.phone == account)

    return await _login_by_field(account, password, db, where_clause=User.username == account)


async def send_verification_code(account: str, db: AsyncSession) -> dict:
    """Send verification code. Email -> SMTP; phone -> SMS mock."""
    account_type = _detect_account_type(account)

    if account_type == "username":
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": 40026,
                "message_key": "errors.auth.verification_code_requires_email_or_phone",
                "message": "验证码登录仅支持邮箱或手机号",
            },
        )

    if account_type == "phone":
        return await send_sms_code(account)

    _check_email_domain_allowed(account)

    from app.services.email_service import get_smtp_config_for_email, send_verification_email

    smtp_config = await get_smtp_config_for_email(db, account)
    if not smtp_config:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": 40052,
                "message_key": "errors.smtp.not_configured",
                "message": "全局 SMTP 未配置，请联系管理员",
            },
        )

    if account in _verification_codes:
        _, expire_ts = _verification_codes[account]
        remaining = expire_ts - time.time()
        if remaining > 240:
            raise HTTPException(
                status_code=429,
                detail={
                    "error_code": 42920,
                    "message_key": "errors.auth.code_send_too_frequent",
                    "message": "发送过于频繁，请稍后再试",
                },
            )

    code = f"{secrets.randbelow(900000) + 100000}"
    _verification_codes[account] = (code, time.time() + 300)

    try:
        await send_verification_email(account, code, smtp_config, db)
    except Exception as exc:
        _verification_codes.pop(account, None)
        logger.warning("Failed to send verification email to %s: %s", account, exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": 50010,
                "message_key": "errors.smtp.send_failed",
                "message": f"邮件发送失败: {exc}",
            },
        )

    return {"sent": True, "message": "验证码已发送"}


async def login_with_verification_code(
    account: str, code: str, db: AsyncSession
) -> LoginResponse:
    """Unified verification-code login. Phone auto-registers; email requires existing account."""
    account_type = _detect_account_type(account)

    if account_type == "username":
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": 40026,
                "message_key": "errors.auth.verification_code_requires_email_or_phone",
                "message": "验证码登录仅支持邮箱或手机号",
            },
        )

    if account_type == "phone":
        return await login_with_phone(account, code, db)

    _check_email_domain_allowed(account)

    stored = _verification_codes.get(account)
    if stored is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": 40021,
                "message_key": "errors.auth.code_not_requested",
                "message": "请先获取验证码",
            },
        )

    stored_code, expire_ts = stored
    if time.time() > expire_ts:
        _verification_codes.pop(account, None)
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": 40022,
                "message_key": "errors.auth.code_expired",
                "message": "验证码已过期",
            },
        )
    if stored_code != code:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": 40023,
                "message_key": "errors.auth.code_invalid",
                "message": "验证码错误",
            },
        )

    _verification_codes.pop(account, None)

    result = await db.execute(
        select(User)
        .options(selectinload(User.oauth_connections))
        .where(User.email == account, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": 40025,
                "message_key": "errors.auth.email_not_registered",
                "message": "该邮箱未注册，请联系管理员获取邀请",
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


async def admin_reset_password(user_id: str, db: AsyncSession) -> str:
    """管理员重置用户密码，返回随机明文密码。"""
    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": 40401,
                "message_key": "errors.auth.user_not_found_or_disabled",
                "message": "用户不存在",
            },
        )
    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": 40325,
                "message_key": "errors.auth.account_disabled",
                "message": "该用户已被禁用",
            },
        )

    plain = secrets.token_urlsafe(9)
    user.password_hash = _hash_password(plain)
    await db.commit()
    logger.info("管理员重置密码: user_id=%s", user_id)
    return plain
