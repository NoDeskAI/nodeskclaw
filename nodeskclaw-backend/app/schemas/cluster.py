"""Cluster-related schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class ClusterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    compute_provider: str = "k8s"
    kubeconfig: str | None = Field(default=None, max_length=65536)
    provider: str = Field(default="vke", max_length=50)
    ingress_class: str = Field(default="nginx", max_length=100)
    proxy_endpoint: str | None = Field(default=None, max_length=2048)


class ClusterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    provider: str | None = Field(default=None, max_length=50)
    ingress_class: str | None = Field(default=None, max_length=100)
    proxy_endpoint: str | None = Field(default=None, max_length=2048)


class ClusterInfo(BaseModel):
    id: str
    name: str
    provider: str
    compute_provider: str = "k8s"
    auth_type: str
    ingress_class: str = "nginx"
    proxy_endpoint: str | None = None
    api_server_url: str | None = None
    k8s_version: str | None = None
    status: str
    health_status: str | None = None
    token_expires_at: datetime | None = None
    last_health_check: datetime | None = None
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ClusterOverview(BaseModel):
    name: str
    version: str
    node_count: int
    node_ready: int
    cpu_total: str
    cpu_used: str
    cpu_percent: float
    memory_total: str
    memory_used: str
    memory_percent: float
    pod_count: int


class NodeInfo(BaseModel):
    name: str
    status: str
    ip: str
    cpu_capacity: str
    cpu_used: str
    memory_capacity: str
    memory_used: str
    pod_count: int
    conditions: list[dict] = []


class ClusterHealth(BaseModel):
    auth_type: str
    token_status: str  # ok / expiring_soon / expired / not_token
    token_expires_at: str | None = None
    healthy: bool
    last_health_check: str | None = None


class ConnectionTestResult(BaseModel):
    ok: bool
    version: str | None = None
    nodes: int | None = None
    message: str | None = None
