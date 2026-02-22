"""Background job for auto-summary generation from workspace messages."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.blackboard import Blackboard
from app.models.workspace import Workspace
from app.models.workspace_message import WorkspaceMessage

logger = logging.getLogger(__name__)


class SummaryJob:
    """Periodically regenerates blackboard summaries from recent workspace messages."""

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

            if not messages:
                continue

            summary_lines = []
            for m in reversed(messages[:10]):
                ts = m.created_at.strftime("%H:%M") if isinstance(m.created_at, datetime) else ""
                summary_lines.append(f"[{ts} {m.sender_name}] {m.content[:100]}")
            summary_text = "\n".join(summary_lines)

            bb_result = await db.execute(
                select(Blackboard).where(Blackboard.workspace_id == ws.id)
            )
            bb = bb_result.scalar_one_or_none()
            if bb:
                bb.auto_summary = summary_text
                bb.summary_updated_at = datetime.now(timezone.utc)
                count += 1

        await db.commit()
        return count
