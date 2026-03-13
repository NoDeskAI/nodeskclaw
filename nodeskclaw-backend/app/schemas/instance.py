"""Instance-related schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class WorkspaceBrief(BaseModel):
    id: str
    name: str


class InstanceInfo(BaseModel):
    id: str
    name: str
    slug: str = ""
    org_id: str | None = None
    cluster_id: str
    namespace: str
    image_version: str
    replicas: int
    available_replicas: int = 0
    status: str
    service_type: str
    ingress_domain: str | None = None
    compute_provider: str = "k8s"
    runtime: str = "openclaw"
    endpoint_url: str | None = None
    storage_class: str = "nas-subpath"
    storage_size: str = "80Gi"
    advanced_config: str | None = None
    pending_config: str | None = None
    created_by: str
    created_at: datetime
    updated_at: datetime
    my_role: str | None = None
    workspaces: list[WorkspaceBrief] = []

    model_config = {"from_attributes": True}


class UpdateConfigRequest(BaseModel):
    """实例配置修改请求（滚动更新）。"""
    image_version: str | None = Field(default=None, max_length=100)
    cpu_request: str | None = Field(default=None, max_length=20)
    cpu_limit: str | None = Field(default=None, max_length=20)
    mem_request: str | None = Field(default=None, max_length=20)
    mem_limit: str | None = Field(default=None, max_length=20)
    env_vars: dict[str, str] | None = Field(default=None, max_length=200)
    replicas: int | None = Field(default=None, ge=0, le=10)
    advanced_config: dict | None = None


class ContainerInfo(BaseModel):
    name: str
    image: str
    ready: bool
    restart_count: int
    state: str  # running / waiting / terminated


class PodInfo(BaseModel):
    name: str
    status: str
    node: str | None = None
    ip: str | None = None
    cpu_used: str | None = None
    memory_used: str | None = None
    restart_count: int = 0
    started_at: datetime | None = None
    containers: list[ContainerInfo] = []


class ServiceInfo(BaseModel):
    name: str
    type: str
    cluster_ip: str | None = None
    external_ip: str | None = None
    ports: list[dict] = []


class K8sEvent(BaseModel):
    type: str  # Normal / Warning
    reason: str
    message: str
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    count: int = 1


class InstanceDetail(InstanceInfo):
    cpu_request: str
    cpu_limit: str
    mem_request: str
    mem_limit: str
    env_vars: dict[str, str] = {}
    pods: list[PodInfo] = []
    service_info: ServiceInfo | None = None
    events: list[K8sEvent] = []
