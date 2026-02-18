"""Background job for auto-summary generation and expired context cleanup."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, delete

from app.models.blackboard import Blackboard
from app.models.context_entry import ContextEntry
from app.models.workspace import Workspace

logger = logging.getLogger(__name__)


class SummaryJob:
    """Periodically cleans up expired context entries and regenerates blackboard summaries."""

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
            cleaned = await self._cleanup_expired(db)
            if cleaned:
                logger.info("Cleaned %d expired context entries", cleaned)

            updated = await self._refresh_summaries(db)
            if updated:
                logger.info("Refreshed summaries for %d workspaces", updated)

    async def _cleanup_expired(self, db) -> int:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            delete(ContextEntry).where(ContextEntry.expires_at < now)
        )
        await db.commit()
        return result.rowcount or 0

    async def _refresh_summaries(self, db) -> int:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(Workspace).where(Workspace.deleted_at.is_(None))
        )
        workspaces = result.scalars().all()

        count = 0
        for ws in workspaces:
            entries_result = await db.execute(
                select(ContextEntry).where(
                    ContextEntry.workspace_id == ws.id,
                    ContextEntry.expires_at > now,
                    ContextEntry.deleted_at.is_(None),
                ).order_by(ContextEntry.created_at.desc()).limit(20)
            )
            entries = entries_result.scalars().all()

            if not entries:
                continue

            summary_lines = []
            for e in entries[:10]:
                summary_lines.append(f"[{e.entry_type}] {e.content[:100]}")
            summary_text = "\n".join(summary_lines)

            bb_result = await db.execute(
                select(Blackboard).where(Blackboard.workspace_id == ws.id)
            )
            bb = bb_result.scalar_one_or_none()
            if bb:
                bb.auto_summary = summary_text
                bb.summary_updated_at = now
                count += 1

        await db.commit()
        return count
