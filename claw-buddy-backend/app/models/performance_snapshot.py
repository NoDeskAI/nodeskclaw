"""Performance snapshot — stores historical performance data for trend analysis."""

from sqlalchemy import Column, String, DateTime, JSON
from sqlalchemy.sql import func

from app.models.base import BaseModel


class PerformanceSnapshot(BaseModel):
    __tablename__ = "performance_snapshots"

    workspace_id = Column(String, index=True, nullable=False)
    instance_id = Column(String, index=True, nullable=False)
    agent_name = Column(String, default="")
    metrics = Column(JSON, default=list)
    collected_at = Column(DateTime(timezone=True), server_default=func.now())
