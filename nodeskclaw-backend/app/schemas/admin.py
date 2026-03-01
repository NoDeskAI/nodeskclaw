"""Admin platform membership schemas."""

from datetime import datetime

from pydantic import BaseModel


class AdminMemberInfo(BaseModel):
    id: str
    user_id: str
    org_id: str
    role: str
    user_name: str | None = None
    user_email: str | None = None
    user_avatar_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AddAdminMemberRequest(BaseModel):
    user_id: str
    role: str = "member"


class UpdateAdminMemberRoleRequest(BaseModel):
    role: str
