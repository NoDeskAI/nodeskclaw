"""Auth-related schemas."""

from datetime import datetime

from pydantic import BaseModel


class FeishuCallbackRequest(BaseModel):
    code: str
    redirect_uri: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 86400  # seconds


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class UserInfo(BaseModel):
    id: str
    feishu_uid: str
    name: str
    email: str | None = None
    avatar_url: str | None = None
    role: str
    is_super_admin: bool = False
    current_org_id: str | None = None
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 86400
    user: UserInfo
