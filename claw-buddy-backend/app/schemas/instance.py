"""Instance-related schemas."""

from datetime import datetime

from pydantic import BaseModel


class InstanceInfo(BaseModel):
    id: str
    name: str
    cluster_id: str
    namespace: str
    image_version: str
    replicas: int
    available_replicas: int = 0
    status: str
    service_type: str
    ingress_domain: str | None = None
    storage_class: str = "nas-subpath"
    storage_size: str = "80Gi"
    advanced_config: str | None = None
    pending_config: str | None = None  # 待应用的配置（两步操作）
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UpdateConfigRequest(BaseModel):
    """实例配置修改请求（滚动更新）。"""
    image_version: str | None = None
    cpu_request: str | None = None
    cpu_limit: str | None = None
    mem_request: str | None = None
    mem_limit: str | None = None
    env_vars: dict[str, str] | None = None
    replicas: int | None = None
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
