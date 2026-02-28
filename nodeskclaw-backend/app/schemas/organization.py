"""Organization & membership schemas."""

from datetime import datetime

from pydantic import BaseModel


class OrgCreate(BaseModel):
    name: str
    slug: str
    plan: str = "free"


class OrgUpdate(BaseModel):
    name: str | None = None
    plan: str | None = None
    max_instances: int | None = None
    max_cpu_total: str | None = None
    max_mem_total: str | None = None
    max_storage_total: str | None = None
    cluster_id: str | None = None  # 绑定/解绑专属集群
    is_active: bool | None = None


class OrgInfo(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    max_instances: int
    max_cpu_total: str
    max_mem_total: str
    max_storage_total: str
    cluster_id: str | None = None
    is_active: bool
    member_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MemberInfo(BaseModel):
    id: str
    user_id: str
    org_id: str
    role: str
    user_name: str | None = None
    user_email: str | None = None
    user_avatar_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AddMemberRequest(BaseModel):
    user_id: str
    role: str = "member"


class UpdateMemberRoleRequest(BaseModel):
    role: str


class OAuthOrgSetupRequest(BaseModel):
    provider: str
    name: str
    slug: str
    job_title: str | None = None


FeishuOrgSetupRequest = OAuthOrgSetupRequest
