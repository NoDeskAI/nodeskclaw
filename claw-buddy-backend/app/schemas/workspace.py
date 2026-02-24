"""Pydantic schemas for Workspace, Blackboard, Agent, Chat, and Webhook APIs."""

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
    slug: str | None = None
    status: str
    hex_q: int
    hex_r: int
    sse_connected: bool = False


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


class WorkspaceChatRequest(BaseModel):
    message: str
    mentions: list[str] | None = None


class WorkspaceMessageInfo(BaseModel):
    id: str
    workspace_id: str
    sender_type: str
    sender_id: str
    sender_name: str
    content: str
    message_type: str
    target_instance_id: str | None = None
    depth: int = 0
    created_at: datetime


