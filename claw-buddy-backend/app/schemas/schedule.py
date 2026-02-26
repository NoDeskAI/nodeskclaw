"""Pydantic schemas for workspace schedule triggers."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


class ScheduleCreate(BaseModel):
    name: str
    cron_expr: str
    message_template: str
    is_active: bool = True


class ScheduleUpdate(BaseModel):
    name: str | None = None
    cron_expr: str | None = None
    message_template: str | None = None
    is_active: bool | None = None


class ScheduleInfo(BaseModel):
    id: str
    workspace_id: str
    name: str
    cron_expr: str
    message_template: str
    is_active: bool
    created_at: datetime | None = None
