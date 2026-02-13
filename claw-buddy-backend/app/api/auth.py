"""Auth endpoints: Feishu SSO, token refresh, user info, logout."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.auth import (
    FeishuCallbackRequest,
    LoginResponse,
    RefreshTokenRequest,
    TokenResponse,
    UserInfo,
)
from app.schemas.common import ApiResponse
from app.services.auth_service import feishu_login, refresh_tokens

router = APIRouter()


@router.post("/feishu/callback", response_model=ApiResponse[LoginResponse])
async def feishu_callback(body: FeishuCallbackRequest, db: AsyncSession = Depends(get_db)):
    """飞书 SSO 回调：用临时 code 换取 JWT。"""
    result = await feishu_login(body.code, db)
    return ApiResponse(data=result)


@router.post("/refresh", response_model=ApiResponse[TokenResponse])
async def refresh(body: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """刷新 Token。"""
    result = await refresh_tokens(body.refresh_token, db)
    return ApiResponse(data=result)


@router.get("/me", response_model=ApiResponse[UserInfo])
async def me(current_user: User = Depends(get_current_user)):
    """获取当前用户信息。"""
    return ApiResponse(data=UserInfo.model_validate(current_user))


@router.post("/logout", response_model=ApiResponse)
async def logout(current_user: User = Depends(get_current_user)):
    """登出（客户端清除 Token 即可，服务端无需额外操作）。"""
    return ApiResponse(message="已登出")
