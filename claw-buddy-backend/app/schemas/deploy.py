"""Deploy-related schemas."""

from datetime import datetime

from pydantic import BaseModel


class DeployRequest(BaseModel):
    cluster_id: str
    name: str
    namespace: str | None = None  # auto-generated if not provided
    image_version: str
    replicas: int = 1
    cpu_request: str = "500m"
    cpu_limit: str = "2000m"
    mem_request: str = "512Mi"
    mem_limit: str = "2Gi"
    env_vars: dict[str, str] = {}
    quota_cpu: str = "4"
    quota_mem: str = "8Gi"
    storage_class: str = "nas-subpath"
    storage_size: str = "80Gi"
    advanced_config: dict | None = None  # Volume/Sidecar/Init/Network


class PrecheckItem(BaseModel):
    name: str
    status: str  # pass / fail / warning
    message: str


class PrecheckResult(BaseModel):
    passed: bool
    items: list[PrecheckItem] = []


class DeployProgress(BaseModel):
    deploy_id: str
    step: int
    total_steps: int
    current_step: str
    status: str  # in_progress / success / failed
    message: str | None = None
    percent: float = 0.0
    logs: list[str] | None = None  # 当前步骤的诊断日志行


class DeployRecordInfo(BaseModel):
    id: str
    instance_id: str
    revision: int
    action: str
    image_version: str | None = None
    replicas: int | None = None
    config_snapshot: str | None = None
    status: str
    message: str | None = None
    triggered_by: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ImageTag(BaseModel):
    tag: str
    digest: str | None = None
    created_at: str | None = None
