"""Pydantic schemas for Agent Device API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentDevicePresetEnablementUpdate(BaseModel):
    enabled: bool = True
    config: dict[str, Any] | None = None


class AgentDevicePresetInfo(BaseModel):
    preset_id: str
    provider_id: str
    display_name: str
    description: str
    gene_slug: str
    capability_schema: dict[str, Any]
    enabled: bool
    config: dict[str, Any] | None = None
    provider_status: str
    provider_status_reason: str | None = None


class AgentDeviceCreate(BaseModel):
    preset_id: str = "browser.bpilot.session"
    display_name: str = Field(min_length=1, max_length=128)
    hex_q: int
    hex_r: int
    config: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class AgentDeviceUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    hex_q: int | None = None
    hex_r: int | None = None
    config: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class AgentDeviceInfo(BaseModel):
    id: str
    workspace_id: str
    preset_id: str
    provider_id: str
    display_name: str
    hex_q: int
    hex_r: int
    status: str
    status_reason: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime


class AgentDeviceGrantCreate(BaseModel):
    subject_type: str
    subject_id: str
    scopes: list[str]
    can_delegate: bool = False
    parent_grant_id: str | None = None
    expires_at: datetime | None = None


class AgentDeviceGrantInfo(BaseModel):
    id: str
    workspace_id: str
    device_id: str
    subject_type: str
    subject_id: str
    scopes: list[str]
    can_delegate: bool
    parent_grant_id: str | None = None
    granted_by_type: str
    granted_by_id: str
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime


class AgentDeviceLeaseAcquire(BaseModel):
    ttl_seconds: int | None = None


class AgentDeviceLeaseRenew(BaseModel):
    ttl_seconds: int | None = None


class AgentDeviceLeaseInfo(BaseModel):
    id: str
    workspace_id: str
    device_id: str
    holder_agent_id: str
    grant_id: str
    status: str
    expires_at: datetime
    renewed_at: datetime | None = None
    released_at: datetime | None = None
    created_at: datetime


class AgentDeviceVisibilityInfo(BaseModel):
    device_id: str
    visible: bool
    reasons: list[str]
    status: str
    status_reason: str | None = None
    preset_id: str
    provider_id: str
    display_name: str
    hex_q: int
    hex_r: int
    grant_id: str | None = None
    topology_reachable: bool
    reachability_source: str | None = None
    topology_path_ref: str | None = None
    topology_reason: str
    active_lease: dict[str, Any] | None = None


class AgentDeviceInvokeRequest(BaseModel):
    lease_id: str
    action: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentDeviceInvokeResponse(BaseModel):
    status: str
    result: dict[str, Any]
