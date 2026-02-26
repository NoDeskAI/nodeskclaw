"""Background job for auto-summary generation + member status maintenance."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, func

from app.models.base import not_deleted
from app.models.blackboard import Blackboard
from app.models.instance import Instance
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.models.workspace_message import WorkspaceMessage

logger = logging.getLogger(__name__)


class SummaryJob:
    """Periodically regenerates blackboard summaries and maintains member status."""

    def __init__(self, session_factory, interval_seconds: int = 3600):
        self._session_factory = session_factory
        self._interval = interval_seconds
        self._task: asyncio.Task | None = None

    def start(self):
        self._task = asyncio.create_task(self._loop())
        logger.info("SummaryJob started (interval=%ds)", self._interval)

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("SummaryJob stopped")

    async def _loop(self):
        while True:
            try:
                await asyncio.sleep(self._interval)
                await self._run()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("SummaryJob error: %s", e)
                await asyncio.sleep(60)

    async def _run(self):
        async with self._session_factory() as db:
            updated = await self._refresh_summaries(db)
            if updated:
                logger.info("Refreshed summaries for %d workspaces", updated)

    async def _refresh_summaries(self, db) -> int:
        result = await db.execute(
            select(Workspace).where(Workspace.deleted_at.is_(None))
        )
        workspaces = result.scalars().all()

        count = 0
        for ws in workspaces:
            messages_result = await db.execute(
                select(WorkspaceMessage).where(
                    WorkspaceMessage.workspace_id == ws.id,
                    WorkspaceMessage.deleted_at.is_(None),
                ).order_by(WorkspaceMessage.created_at.desc()).limit(20)
            )
            messages = messages_result.scalars().all()

            bb_result = await db.execute(
                select(Blackboard).where(Blackboard.workspace_id == ws.id)
            )
            bb = bb_result.scalar_one_or_none()
            if not bb:
                continue

            if messages:
                task_stats = self._compute_task_stats(bb.tasks)
                summary_lines = []
                for m in reversed(messages[:10]):
                    ts = m.created_at.strftime("%H:%M") if isinstance(m.created_at, datetime) else ""
                    summary_lines.append(f"[{ts} {m.sender_name}] {m.content[:100]}")
                summary_text = "\n".join(summary_lines)
                if task_stats:
                    summary_text = f"{task_stats}\n\n{summary_text}"
                bb.auto_summary = summary_text
                bb.summary_updated_at = datetime.now(timezone.utc)

            member_status = await self._build_member_status(db, ws.id, messages)
            bb.member_status = member_status
            count += 1

        await db.commit()
        return count

    @staticmethod
    def _compute_task_stats(tasks: list | None) -> str:
        if not tasks:
            return ""
        by_status: dict[str, int] = {}
        blocked_titles: list[str] = []
        for t in tasks:
            s = t.get("status", "todo")
            by_status[s] = by_status.get(s, 0) + 1
            if s == "blocked":
                blocked_titles.append(t.get("title", ""))
        parts = [f"{s}: {c}" for s, c in by_status.items()]
        line = f"Tasks: {', '.join(parts)}"
        if blocked_titles:
            line += f" | Blocked: {', '.join(blocked_titles[:3])}"
        return line

    @staticmethod
    async def _build_member_status(db, workspace_id: str, messages: list) -> list:
        last_activity: dict[str, str] = {}
        for m in messages:
            key = f"{m.sender_type}:{m.sender_id}"
            if key not in last_activity:
                ts = m.created_at.isoformat() if isinstance(m.created_at, datetime) else ""
                last_activity[key] = ts

        agents_q = await db.execute(
            select(Instance).where(
                Instance.workspace_id == workspace_id,
                not_deleted(Instance),
            )
        )
        status_list = []
        for agent in agents_q.scalars().all():
            status_list.append({
                "type": "agent",
                "id": agent.id,
                "name": agent.agent_display_name or agent.name,
                "status": agent.status,
                "last_activity": last_activity.get(f"agent:{agent.id}", ""),
                "current_task_id": None,
            })

        humans_q = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                not_deleted(WorkspaceMember),
            )
        )
        for member in humans_q.scalars().all():
            status_list.append({
                "type": "human",
                "id": member.user_id,
                "name": "",
                "status": "online",
                "last_activity": last_activity.get(f"user:{member.user_id}", ""),
                "current_task_id": None,
            })

        return status_list
