"""Billing & plan schemas."""

from pydantic import BaseModel


class PlanInfo(BaseModel):
    id: str
    name: str
    display_name: str
    max_instances: int
    max_cpu_per_instance: str
    max_mem_per_instance: str
    allowed_specs: str  # JSON array string
    dedicated_cluster: bool
    price_monthly: int  # 分
    is_active: bool

    model_config = {"from_attributes": True}


class OrgUsage(BaseModel):
    """当前组织资源使用量。"""
    instance_count: int
    instance_limit: int
    cpu_used: str
    cpu_limit: str
    mem_used: str
    mem_limit: str


class UpgradeRequest(BaseModel):
    plan_name: str
