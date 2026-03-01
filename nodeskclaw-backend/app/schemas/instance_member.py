"""Instance member schemas."""

from datetime import datetime

from pydantic import BaseModel


class InstanceMemberInfo(BaseModel):
    id: str
    instance_id: str
    user_id: str
    role: str
    user_name: str | None = None
    user_email: str | None = None
    user_avatar_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AddMemberRequest(BaseModel):
    user_id: str
    role: str = "viewer"


class UpdateMemberRoleRequest(BaseModel):
    role: str


class SearchUserResult(BaseModel):
    user_id: str
    name: str | None = None
    email: str | None = None
    avatar_url: str | None = None
