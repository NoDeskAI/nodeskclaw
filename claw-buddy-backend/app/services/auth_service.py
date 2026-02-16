"""Auth service: Feishu SSO login, JWT management."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.user import User, UserRole
from app.schemas.auth import LoginResponse, TokenResponse, UserInfo
from app.utils.feishu import exchange_code_for_user


async def feishu_login(code: str, db: AsyncSession, redirect_uri: str | None = None) -> LoginResponse:
    """
    Handle Feishu SSO callback:
    1. Exchange code for user info via Feishu API
    2. Upsert user record
    3. Issue JWT tokens
    """
    feishu_user = await exchange_code_for_user(code, redirect_uri=redirect_uri)

    # Upsert user by feishu open_id
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
            role=UserRole.user,
        )
        db.add(user)
    else:
        user.name = feishu_user["name"]
        user.email = feishu_user.get("email")
        user.avatar_url = feishu_user.get("avatar_url")

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserInfo.model_validate(user),
    )


async def refresh_tokens(refresh_token_str: str, db: AsyncSession) -> TokenResponse:
    """Validate refresh token, issue new token pair."""
    payload = decode_token(refresh_token_str)

    if payload.get("type") != "refresh":
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token 类型错误")

    user_id = payload.get("sub")
    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")

    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )
