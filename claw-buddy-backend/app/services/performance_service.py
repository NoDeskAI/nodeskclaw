"""Performance data collection — aggregates metrics from tasks, ratings, and usage."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import not_deleted
from app.models.blackboard import Blackboard
from app.models.gene import GeneEffectLog, GeneRating, InstanceGene
from app.models.instance import Instance
from app.models.workspace_message import WorkspaceMessage

logger = logging.getLogger(__name__)


async def collect_agent_performance(
    db: AsyncSession, workspace_id: str, instance_id: str,
) -> dict:
    """Collect performance metrics for a single agent in a workspace."""
    bb_q = await db.execute(
        select(Blackboard).where(Blackboard.workspace_id == workspace_id)
    )
    bb = bb_q.scalar_one_or_none()

    task_completion_rate = 0.0
    if bb and bb.tasks:
        total = len(bb.tasks)
        assigned = [t for t in bb.tasks if t.get("assignee_id") == instance_id]
        done = [t for t in assigned if t.get("status") == "done"]
        if assigned:
            task_completion_rate = len(done) / len(assigned)

    msg_count_q = await db.execute(
        select(func.count(WorkspaceMessage.id)).where(
            WorkspaceMessage.workspace_id == workspace_id,
            WorkspaceMessage.sender_id == instance_id,
            WorkspaceMessage.sender_type == "agent",
            not_deleted(WorkspaceMessage),
        )
    )
    message_count = msg_count_q.scalar() or 0

    genes_q = await db.execute(
        select(InstanceGene).where(
            InstanceGene.instance_id == instance_id,
            not_deleted(InstanceGene),
        )
    )
    gene_ids = [ig.gene_id for ig in genes_q.scalars().all()]

    avg_rating = 0.0
    if gene_ids:
        rating_q = await db.execute(
            select(func.avg(GeneRating.rating)).where(
                GeneRating.gene_id.in_(gene_ids),
                not_deleted(GeneRating),
            )
        )
        avg_rating = float(rating_q.scalar() or 0.0)

    effectiveness_q = await db.execute(
        select(func.avg(GeneEffectLog.value)).where(
            GeneEffectLog.instance_id == instance_id,
            not_deleted(GeneEffectLog),
        )
    )
    avg_effectiveness = float(effectiveness_q.scalar() or 0.0)

    assigned_tasks = [t for t in (bb.tasks if bb and bb.tasks else []) if t.get("assignee_id") == instance_id]
    done_tasks = [t for t in assigned_tasks if t.get("status") == "done"]
    collab_efficiency = (len(done_tasks) / message_count) if message_count > 0 else 0.0

    return {
        "instance_id": instance_id,
        "workspace_id": workspace_id,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "metrics": [
            {"name": "task_completion_rate", "value": round(task_completion_rate, 2), "target": 0.8},
            {"name": "message_activity", "value": message_count, "target": 50},
            {"name": "avg_gene_rating", "value": round(avg_rating, 2), "target": 4.0},
            {"name": "avg_effectiveness", "value": round(avg_effectiveness, 2), "target": 0.7},
            {"name": "collaboration_efficiency", "value": round(collab_efficiency, 4), "target": 0.1},
        ],
    }


async def collect_workspace_performance(
    db: AsyncSession, workspace_id: str,
) -> list[dict]:
    """Collect performance metrics for all agents in a workspace."""
    agents_q = await db.execute(
        select(Instance).where(
            Instance.workspace_id == workspace_id,
            not_deleted(Instance),
        )
    )
    results = []
    for agent in agents_q.scalars().all():
        perf = await collect_agent_performance(db, workspace_id, agent.id)
        perf["agent_name"] = agent.agent_display_name or agent.name
        results.append(perf)
    return results


async def update_blackboard_performance(db: AsyncSession, workspace_id: str) -> None:
    """Refresh the blackboard's performance field with latest collected data."""
    import uuid
    from app.models.performance_snapshot import PerformanceSnapshot

    perf_data = await collect_workspace_performance(db, workspace_id)
    bb_q = await db.execute(
        select(Blackboard).where(Blackboard.workspace_id == workspace_id)
    )
    bb = bb_q.scalar_one_or_none()
    if bb:
        bb.performance = [
            {
                "member_id": p["instance_id"],
                "member_name": p.get("agent_name", ""),
                "period": "current",
                "metrics": p["metrics"],
            }
            for p in perf_data
        ]

        for p in perf_data:
            snapshot = PerformanceSnapshot(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                instance_id=p["instance_id"],
                agent_name=p.get("agent_name", ""),
                metrics=p["metrics"],
            )
            db.add(snapshot)

        await db.commit()
