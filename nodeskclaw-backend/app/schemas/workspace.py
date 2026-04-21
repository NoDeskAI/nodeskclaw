"""Pydantic schemas for Workspace, Blackboard, Agent, Chat, and Webhook APIs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ── Workspace ────────────────────────────────────────

class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    color: str = "#a78bfa"
    icon: str = "bot"
    template_id: str | None = None
    cluster_id: str = Field(..., min_length=1)


class WorkspaceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None
    icon: str | None = None


class AgentBrief(BaseModel):
    instance_id: str
    name: str
    display_name: str | None = None
    label: str | None = None
    slug: str | None = None
    status: str
    hex_q: int
    hex_r: int
    sse_connected: bool = False
    theme_color: str | None = None


class WorkspaceInfo(BaseModel):
    id: str
    org_id: str
    name: str
    description: str
    color: str
    icon: str
    created_by: str
    cluster_id: str | None = None
    source_template_id: str | None = None
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
    cluster_id: str | None = None
    agent_count: int = 0
    agents: list[AgentBrief] = []
    created_at: datetime


# ── Tasks & Objectives ───────────────────────────────

class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    description: str | None = None
    priority: str = "medium"
    assignee_id: str | None = None
    estimated_value: float | None = None

class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    assignee_id: str | None = None
    estimated_value: float | None = None
    actual_value: float | None = None
    token_cost: int | None = None
    blocker_reason: str | None = None

class TaskInfo(BaseModel):
    id: str
    workspace_id: str
    title: str
    description: str | None = None
    status: str
    priority: str
    assignee_instance_id: str | None = None
    assignee_name: str | None = None
    created_by_instance_id: str | None = None
    estimated_value: float | None = None
    actual_value: float | None = None
    token_cost: int | None = None
    blocker_reason: str | None = None
    completed_at: datetime | None = None
    started_at: datetime | None = None
    archived_at: datetime | None = None
    schedule_id: str | None = None
    deadline: datetime | None = None
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime

class ObjectiveInfo(BaseModel):
    id: str
    workspace_id: str
    title: str
    description: str | None = None
    progress: float = 0.0
    obj_type: str = "objective"
    parent_id: str | None = None
    children: list[ObjectiveInfo] = []
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime

class ObjectiveCreate(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    description: str | None = None
    obj_type: str = "objective"
    parent_id: str | None = None

class ObjectiveUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    progress: float | None = None
    obj_type: str | None = None
    parent_id: str | None = None


# ── Blackboard ───────────────────────────────────────

class BlackboardInfo(BaseModel):
    id: str
    workspace_id: str
    content: str
    tasks: list[TaskInfo] = []
    objectives: list[ObjectiveInfo] = []
    updated_at: datetime


class BlackboardUpdate(BaseModel):
    content: str


class BlackboardSectionPatch(BaseModel):
    section: str = Field(min_length=1, max_length=128)
    content: str


# ── Agent Management ─────────────────────────────────

class AddAgentRequest(BaseModel):
    instance_id: str
    display_name: str | None = None
    hex_q: int | None = None
    hex_r: int | None = None
    install_gene_slugs: list[str] = []


class UpdateAgentRequest(BaseModel):
    display_name: str | None = None
    label: str | None = None
    hex_q: int | None = None
    hex_r: int | None = None
    theme_color: str | None = None


# ── Workspace Members (RBAC) ────────────────────────

class WorkspaceMemberInfo(BaseModel):
    user_id: str
    user_name: str
    user_email: str | None = None
    user_avatar_url: str | None = None
    role: str
    is_admin: bool = False
    permissions: list[str] = []
    created_at: datetime


class WorkspaceMemberAdd(BaseModel):
    user_id: str
    permissions: list[str] = []
    is_admin: bool = False


class WorkspaceMemberUpdate(BaseModel):
    permissions: list[str] | None = None
    is_admin: bool | None = None


# ── Chat ─────────────────────────────────────────────

class ChatMessageRequest(BaseModel):
    message: str
    history: list[dict] = []


class WorkspaceChatRequest(BaseModel):
    message: str
    mentions: list[str] | None = None
    file_ids: list[str] | None = None


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


# ── Blackboard BBS Posts ──────────────────────────────

class PostCreate(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    content: str = Field(min_length=1)


class PostUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=256)
    content: str | None = Field(None, min_length=1)


class ReplyCreate(BaseModel):
    content: str = Field(min_length=1)


class MentionInfo(BaseModel):
    type: str
    id: str
    name: str | None = None


class ReplyInfo(BaseModel):
    id: str
    post_id: str
    floor_number: int
    content: str
    author_type: str
    author_id: str
    author_name: str
    created_at: datetime


class PostInfo(BaseModel):
    id: str
    workspace_id: str
    title: str
    content: str
    author_type: str
    author_id: str
    author_name: str
    is_pinned: bool
    reply_count: int
    replies: list[ReplyInfo] = []
    mentions: list[MentionInfo] = []
    created_at: datetime
    updated_at: datetime
    last_reply_at: datetime | None = None


class PostListItem(BaseModel):
    id: str
    workspace_id: str
    title: str
    author_type: str
    author_id: str
    author_name: str
    is_pinned: bool
    reply_count: int
    created_at: datetime
    last_reply_at: datetime | None = None


# ── Blackboard Shared Files ───────────────────────────

class FileInfo(BaseModel):
    id: str
    workspace_id: str
    parent_path: str
    name: str
    is_directory: bool
    file_size: int
    content_type: str
    uploader_type: str
    uploader_id: str
    uploader_name: str
    created_at: datetime
    updated_at: datetime


class FileWriteRequest(BaseModel):
    parent_path: str = Field("/", max_length=1024)
    content: str = Field(..., description="Base64-encoded file content")
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = "application/octet-stream"


class MkdirRequest(BaseModel):
    parent_path: str = Field("/", max_length=1024)
    name: str = Field(..., min_length=1, max_length=255)


class FileCopyRequest(BaseModel):
    target_parent_path: str = Field("/", max_length=1024)
    target_filename: str | None = Field(None, max_length=255)


# ── Agent Performance ───────────────────────────────

class ScheduleReliability(BaseModel):
    schedule_id: str
    schedule_name: str
    total: int
    completed: int
    failed: int
    success_rate: float | None = None

class AgentTaskMetrics(BaseModel):
    instance_id: str
    agent_name: str
    theme_color: str | None = None
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    pending_tasks: int
    in_progress_tasks: int
    success_rate: float | None = None
    total_work_minutes: float | None = None
    avg_duration_minutes: float | None = None
    total_token_cost: int = 0
    total_prompt_token_cost: int = 0
    total_completion_token_cost: int = 0
    total_estimated_value: float = 0
    total_actual_value: float = 0
    roi_per_1k_tokens: float | None = None
    schedules: list[ScheduleReliability] = []
    other_workspace_count: int = 0

class AgentPerformanceResponse(BaseModel):
    agents: list[AgentTaskMetrics]
    unclaimed_failures: int = 0


class WorkspaceBreakdown(BaseModel):
    workspace_id: str
    workspace_name: str
    total_tasks: int
    completed_tasks: int
    success_rate: float | None = None
    total_token_cost: int = 0
    total_actual_value: float = 0

class GlobalAgentMetrics(BaseModel):
    instance_id: str
    agent_name: str
    theme_color: str | None = None
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    success_rate: float | None = None
    total_work_minutes: float | None = None
    avg_duration_minutes: float | None = None
    total_token_cost: int = 0
    total_prompt_token_cost: int = 0
    total_completion_token_cost: int = 0
    total_estimated_value: float = 0
    total_actual_value: float = 0
    roi_per_1k_tokens: float | None = None
    workspace_count: int = 0
    workspaces: list[WorkspaceBreakdown] = []

class GlobalAgentPerformanceResponse(BaseModel):
    agents: list[GlobalAgentMetrics]
