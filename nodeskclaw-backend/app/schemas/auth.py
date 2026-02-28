"""Auth-related schemas."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


class OAuthCallbackRequest(BaseModel):
    provider: str
    code: str
    redirect_uri: str | None = None


class FeishuCallbackRequest(BaseModel):
    code: str
    redirect_uri: str | None = None


class EmailRegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str = ""


class EmailLoginRequest(BaseModel):
    email: EmailStr
    password: str


class SmsSendRequest(BaseModel):
    phone: str

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) < 8:
            raise ValueError("手机号格式不正确")
        return v


class SmsLoginRequest(BaseModel):
    phone: str
    code: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 86400  # seconds


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class OAuthConnectionInfo(BaseModel):
    provider: str
    provider_user_id: str

    model_config = {"from_attributes": True}


class UserInfo(BaseModel):
    id: str
    name: str
    email: str | None = None
    phone: str | None = None
    avatar_url: str | None = None
    role: str
    is_active: bool = True
    is_super_admin: bool = False
    current_org_id: str | None = None
    last_login_at: datetime | None = None
    oauth_connections: list[OAuthConnectionInfo] = []

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 86400
    user: UserInfo
    needs_org_setup: bool = False
    provider: str | None = None
