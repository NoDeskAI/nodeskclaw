"""Pydantic schemas for Workspace, Blackboard, Agent, and Context APIs."""

from datetime import datetime

from pydantic import BaseModel, Field


# ── Workspace ────────────────────────────────────────

class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    color: str = "#a78bfa"
    icon: str = "bot"


class WorkspaceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None
    icon: str | None = None


class AgentBrief(BaseModel):
    instance_id: str
    name: str
    display_name: str | None = None
    status: str
    hex_q: int
    hex_r: int


class WorkspaceInfo(BaseModel):
    id: str
    org_id: str
    name: str
    description: str
    color: str
    icon: str
    created_by: str
    agent_count: int = 0
    agents: list[AgentBrief] = []
    created_at: datetime
    updated_at: datetime


class WorkspaceListItem(BaseModel):
    id: str
    name: str
    description: str
    color: str
    icon: str
    agent_count: int = 0
    agents: list[AgentBrief] = []
    created_at: datetime


# ── Blackboard ───────────────────────────────────────

class BlackboardInfo(BaseModel):
    id: str
    workspace_id: str
    auto_summary: str
    manual_notes: str
    summary_updated_at: datetime | None
    updated_at: datetime


class BlackboardUpdate(BaseModel):
    manual_notes: str


# ── Agent Management ─────────────────────────────────

class AddAgentRequest(BaseModel):
    instance_id: str
    display_name: str | None = None
    hex_q: int | None = None
    hex_r: int | None = None


class UpdateAgentRequest(BaseModel):
    display_name: str | None = None
    hex_q: int | None = None
    hex_r: int | None = None


# ── Context ──────────────────────────────────────────

class ContextEntryCreate(BaseModel):
    entry_type: str = "knowledge"
    content: str
    tags: list[str] = []
    visibility: str = "workspace"
    target_instance_ids: list[str] = []
    ttl_hours: int = 24


class ContextEntryInfo(BaseModel):
    id: str
    workspace_id: str
    source_instance_id: str
    entry_type: str
    content: str
    tags: list[str]
    visibility: str
    target_instance_ids: list[str]
    ttl_hours: int
    expires_at: datetime
    created_at: datetime


# ── Agent Share/Subscribe Config ─────────────────────

class AgentShareConfigInfo(BaseModel):
    instance_id: str
    workspace_id: str
    share_enabled: bool
    share_frequency: str
    share_types: list[str]
    custom_instruction: str
    publish_tags: list[str]


class AgentShareConfigUpdate(BaseModel):
    share_enabled: bool | None = None
    share_frequency: str | None = None
    share_types: list[str] | None = None
    custom_instruction: str | None = None
    publish_tags: list[str] | None = None


class AgentSubscriptionInfo(BaseModel):
    instance_id: str
    workspace_id: str
    subscribe_tags: list[str]
    subscribe_types: list[str]
    subscribe_agents: list[str]
    max_entries: int


class AgentSubscriptionUpdate(BaseModel):
    subscribe_tags: list[str] | None = None
    subscribe_types: list[str] | None = None
    subscribe_agents: list[str] | None = None
    max_entries: int | None = None


# ── Workspace Members (RBAC) ────────────────────────

class WorkspaceMemberInfo(BaseModel):
    user_id: str
    user_name: str
    user_email: str | None = None
    user_avatar_url: str | None = None
    role: str
    created_at: datetime


class WorkspaceMemberAdd(BaseModel):
    user_id: str
    role: str = "editor"


class WorkspaceMemberUpdate(BaseModel):
    role: str


# ── Chat ─────────────────────────────────────────────

class ChatMessageRequest(BaseModel):
    message: str
    history: list[dict] = []
