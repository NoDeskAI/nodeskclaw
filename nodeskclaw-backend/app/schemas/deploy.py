"""Deploy-related schemas."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.llm import LlmConfigItem


class DeployRequest(BaseModel):
    cluster_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    slug: str | None = Field(None, max_length=63, pattern=r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$|^[a-z0-9]$")
    namespace: str | None = Field(default=None, max_length=63)
    org_id: str | None = Field(default=None, max_length=100)
    image_version: str = Field(min_length=1, max_length=200)
    replicas: int = Field(default=1, ge=1, le=10)
    cpu_request: str = Field(default="500m", max_length=20)
    cpu_limit: str = Field(default="2000m", max_length=20)
    mem_request: str = Field(default="2Gi", max_length=20)
    mem_limit: str = Field(default="2Gi", max_length=20)
    env_vars: dict[str, str] = Field(default_factory=dict, max_length=50)
    quota_cpu: str = Field(default="4", max_length=20)
    quota_mem: str = Field(default="8Gi", max_length=20)
    storage_class: str = Field(default="nas-subpath", max_length=100)
    storage_size: str = "80Gi"
    advanced_config: dict | None = None
    llm_configs: list[LlmConfigItem] | None = None
    template_id: str | None = Field(default=None, max_length=100)
    runtime: str = Field(default="openclaw", max_length=50)

    @field_validator("storage_size")
    @classmethod
    def validate_min_storage(cls, v: str) -> str:
        val = v.strip()
        gi = 0.0
        if val.endswith("Ti"):
            gi = float(val[:-2]) * 1024
        elif val.endswith("Gi"):
            gi = float(val[:-2])
        elif val.endswith("Mi"):
            gi = float(val[:-2]) / 1024
        else:
            gi = float(val) if val else 0.0
        if gi < 20:
            raise ValueError("存储空间最低为 20Gi")
        return v


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
    step_names: list[str] | None = None  # 仅首次事件携带完整步骤名列表


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
