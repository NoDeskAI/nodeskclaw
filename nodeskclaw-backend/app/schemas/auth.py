"""Auth-related schemas."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


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
    username: str | None = None
    avatar_url: str | None = None
    role: str
    is_active: bool = True
    is_super_admin: bool = False
    has_password: bool = False
    must_change_password: bool = False
    current_org_id: str | None = None
    org_role: str | None = None
    portal_org_role: str | None = None
    last_login_at: datetime | None = None
    oauth_connections: list[OAuthConnectionInfo] = []

    model_config = {"from_attributes": True}


class AccountLoginRequest(BaseModel):
    account: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class VerificationCodeSendRequest(BaseModel):
    account: str = Field(min_length=1, max_length=200)


class VerificationCodeLoginRequest(BaseModel):
    account: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=4, max_length=10)


class ChangePasswordRequest(BaseModel):
    old_password: str | None = Field(default=None, max_length=200)
    new_password: str = Field(min_length=6, max_length=200)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 86400
    user: UserInfo
    needs_org_setup: bool = False
    provider: str | None = None
