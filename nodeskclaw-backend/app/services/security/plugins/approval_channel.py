"""Approval Channel plugin — human-in-the-loop approval for tool execution.

Runs in the Before phase. Checks trust policies and, if no permanent grant
exists, creates a DecisionRecord and waits for human approval. Communicates
the pending/resolved state back to the runtime security layer via the
WebSocket response flow managed by security_ws.py.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..types import (
    AfterResult,
    BeforeAction,
    BeforeResult,
    ExecutionContext,
    ExecutionResult,
    Finding,
    Severity,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL = 2.0
MAX_WAIT = 600.0


class ApprovalChannelPlugin:
    def __init__(self, priority: int = 5) -> None:
        self._id = "approval-channel"
        self._priority = priority
        self._action_types: list[str] | None = None

    @property
    def id(self) -> str:
        return self._id

    @property
    def priority(self) -> int:
        return self._priority

    async def initialize(self, config: dict[str, Any]) -> None:
        self._action_types = config.get("action_types")

    async def destroy(self) -> None:
        pass

    async def before_execute(self, ctx: ExecutionContext) -> BeforeResult:
        action_type = f"tool:{ctx.tool_name}"

        if self._action_types is not None and ctx.tool_name not in self._action_types:
            return BeforeResult()

        if not ctx.workspace_id or not ctx.agent_instance_id:
            return BeforeResult()

        is_trusted = await self._check_trust(ctx.workspace_id, ctx.agent_instance_id, action_type)
        if is_trusted:
            return BeforeResult()

        decision = await self._request_approval(ctx, action_type)

        if decision == "allow_once" or decision == "allow_always":
            return BeforeResult(
                message=f"Approved by supervisor ({decision})",
            )

        return BeforeResult(
            action=BeforeAction.DENY,
            reason=f"Human denied: {action_type}",
            message="This action was denied by your supervisor. Please try a different approach.",
            findings=[Finding(
                plugin_id=self._id,
                category="APPROVAL_DENIED",
                severity=Severity.HIGH,
                message=f"Tool '{ctx.tool_name}' execution denied by human reviewer",
            )],
        )

    async def after_execute(self, ctx: ExecutionContext, result: ExecutionResult) -> AfterResult:
        return AfterResult()

    async def _check_trust(self, workspace_id: str, agent_instance_id: str, action_type: str) -> bool:
        try:
            from sqlalchemy import select

            from app.core.deps import async_session_factory
            from app.models.base import not_deleted
            from app.models.trust_policy import TrustPolicy

            async with async_session_factory() as db:
                result = await db.execute(
                    select(TrustPolicy).where(
                        TrustPolicy.workspace_id == workspace_id,
                        TrustPolicy.agent_instance_id == agent_instance_id,
                        TrustPolicy.action_type == action_type,
                        TrustPolicy.grant_type == "always",
                        not_deleted(TrustPolicy),
                    ).limit(1)
                )
                return result.scalar_one_or_none() is not None
        except Exception:
            logger.warning("Trust policy check failed, defaulting to allow", exc_info=True)
            return True

    async def _request_approval(self, ctx: ExecutionContext, action_type: str) -> str:
        try:
            import uuid

            from app.core.deps import async_session_factory
            from app.models.decision_record import DecisionRecord

            record_id = str(uuid.uuid4())

            async with async_session_factory() as db:
                record = DecisionRecord(
                    id=record_id,
                    workspace_id=ctx.workspace_id,
                    agent_instance_id=ctx.agent_instance_id,
                    decision_type=action_type,
                    context_summary=f"Tool '{ctx.tool_name}' execution requires approval",
                    proposal={"tool_name": ctx.tool_name, "params": ctx.params},
                    outcome="pending",
                )
                db.add(record)
                await db.commit()

            return await self._poll_decision(record_id)
        except Exception:
            logger.warning("Approval request failed, defaulting to allow", exc_info=True)
            return "allow_once"

    async def _poll_decision(self, record_id: str) -> str:
        from sqlalchemy import select

        from app.core.deps import async_session_factory
        from app.models.decision_record import DecisionRecord

        elapsed = 0.0
        while elapsed < MAX_WAIT:
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL

            try:
                async with async_session_factory() as db:
                    result = await db.execute(
                        select(DecisionRecord).where(DecisionRecord.id == record_id)
                    )
                    record = result.scalar_one_or_none()
                    if record and record.outcome != "pending":
                        if record.outcome == "success":
                            comment = (record.review_comment or "").lower()
                            if "always" in comment:
                                return "allow_always"
                            return "allow_once"
                        return "deny"
            except Exception:
                logger.debug("Poll decision error", exc_info=True)

        logger.warning("Approval timed out for record %s", record_id)
        return "deny"
