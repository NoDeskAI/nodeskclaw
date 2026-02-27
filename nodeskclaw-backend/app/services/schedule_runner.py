"""Background job for workspace schedule triggers (cron-based system messages)."""

import asyncio
import logging
from datetime import datetime, timezone

from croniter import croniter
from sqlalchemy import select

from app.models.workspace import Workspace
from app.models.workspace_schedule import WorkspaceSchedule

logger = logging.getLogger(__name__)


class ScheduleRunner:
    """Checks workspace_schedules every 60s, fires matching cron triggers."""

    def __init__(self, session_factory, check_interval: int = 60):
        self._session_factory = session_factory
        self._interval = check_interval
        self._task: asyncio.Task | None = None
        self._last_check: datetime | None = None

    def start(self):
        self._task = asyncio.create_task(self._loop())
        logger.info("ScheduleRunner started (interval=%ds)", self._interval)

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("ScheduleRunner stopped")

    async def _loop(self):
        while True:
            try:
                await asyncio.sleep(self._interval)
                await self._check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("ScheduleRunner error: %s", e)
                await asyncio.sleep(30)

    async def _check(self):
        now = datetime.now(timezone.utc)
        prev = self._last_check or now
        self._last_check = now

        async with self._session_factory() as db:
            result = await db.execute(
                select(WorkspaceSchedule).where(
                    WorkspaceSchedule.is_active == True,
                    WorkspaceSchedule.deleted_at.is_(None),
                )
            )
            schedules = result.scalars().all()

            for schedule in schedules:
                try:
                    cron = croniter(schedule.cron_expr, prev)
                    next_fire = cron.get_next(datetime)
                    if next_fire.replace(tzinfo=timezone.utc) <= now:
                        await self._fire(db, schedule)
                except Exception as e:
                    logger.warning(
                        "Schedule %s cron error: %s", schedule.id, e
                    )

    async def _fire(self, db, schedule: WorkspaceSchedule):
        from app.services import corridor_router
        from app.services.collaboration_service import send_system_message_to_agents
        from app.models.instance import Instance
        from app.models.base import not_deleted

        workspace_id = schedule.workspace_id
        message = schedule.message_template or f"[{schedule.name}]"

        has_topo = await corridor_router.has_any_connections(workspace_id, db)
        if has_topo:
            audience = await corridor_router.get_blackboard_audience(workspace_id, db)
            agent_ids = [ep.entity_id for ep in audience if ep.endpoint_type == "agent"]
        else:
            agents_q = await db.execute(
                select(Instance).where(
                    Instance.workspace_id == workspace_id,
                    Instance.status == "running",
                    not_deleted(Instance),
                )
            )
            agent_ids = [a.id for a in agents_q.scalars().all()]

        if agent_ids:
            await send_system_message_to_agents(
                workspace_id, agent_ids, message, db
            )
            logger.info(
                "Schedule '%s' fired to %d agents in workspace %s",
                schedule.name, len(agent_ids), workspace_id,
            )


PRESET_TEMPLATES = [
    {
        "name": "daily_standup",
        "label": "每日站会",
        "cron_expr": "0 9 * * *",
        "message_template": "请各位汇报昨日进展、今日计划和当前卡点。",
    },
    {
        "name": "weekly_report",
        "label": "每周周报",
        "cron_expr": "0 17 * * 5",
        "message_template": "请提交本周工作总结和下周计划。",
    },
    {
        "name": "sprint_retro",
        "label": "冲刺回顾",
        "cron_expr": "0 14 1,15 * *",
        "message_template": "请回顾本冲刺的完成情况和改进建议。",
    },
]
