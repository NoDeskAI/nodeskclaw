"""Cluster-related schemas."""

from datetime import datetime

from pydantic import BaseModel


class ClusterCreate(BaseModel):
    name: str
    provider: str = "vke"
    kubeconfig: str  # plaintext, encrypted by backend
    ingress_class: str = "nginx"
    proxy_endpoint: str | None = None


class ClusterUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    ingress_class: str | None = None
    proxy_endpoint: str | None = None


class ClusterInfo(BaseModel):
    id: str
    name: str
    provider: str
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
