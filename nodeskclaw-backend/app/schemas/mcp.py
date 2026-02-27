"""Pydantic schemas for MCP Server management."""

from datetime import datetime

from pydantic import BaseModel


class McpServerCreate(BaseModel):
    name: str
    transport: str
    command: str | None = None
    url: str | None = None
    args: dict | None = None
    env: dict | None = None


class McpServerUpdate(BaseModel):
    name: str | None = None
    transport: str | None = None
    command: str | None = None
    url: str | None = None
    args: dict | None = None
    env: dict | None = None
    is_active: bool | None = None


class McpServerInfo(BaseModel):
    id: str
    instance_id: str
    name: str
    transport: str
    command: str | None
    url: str | None
    args: dict | None
    env: dict | None
    is_active: bool
    source: str
    source_gene_id: str | None
    created_at: datetime
