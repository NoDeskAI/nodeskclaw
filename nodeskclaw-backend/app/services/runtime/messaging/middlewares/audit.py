"""AuditMiddleware — records full message lifecycle events to the event sourcing log.

Event types:
  - message_created      — Pipeline entry
  - message_routed       — DeliveryPlan generated
  - message_delivering   — Transport starting delivery
  - message_delivered    — Successful delivery
  - message_delivery_failed — All targets failed
  - message_retried      — Enqueued for retry
  - message_dead_lettered — Moved to DLQ
  - message_pipeline_error — Pipeline-level error
"""

from __future__ import annotations

import logging

from app.services.runtime.messaging.pipeline import MessageMiddleware, NextFn, PipelineContext

logger = logging.getLogger(__name__)


async def record_audit_event(ctx: PipelineContext, event_type: str, data: dict | None = None) -> None:
    db = ctx.db
    if db is None:
        return
    try:
        from app.models.event_log import EventLog
        from app.services.runtime.sse_registry import BACKEND_INSTANCE_ID

        envelope = ctx.envelope
        sender = envelope.data.sender if envelope.data else None
        log = EventLog(
            event_type=event_type,
            message_id=envelope.id,
            workspace_id=ctx.workspace_id,
            source_node_id=sender.id if sender else None,
            trace_id=envelope.traceid,
            backend_instance_id=BACKEND_INSTANCE_ID,
            data=data,
        )
        db.add(log)
        await db.flush()
    except Exception as e:
        logger.warning("AuditMiddleware: failed to record event '%s': %s", event_type, e)


class AuditMiddleware(MessageMiddleware):
    async def process(self, ctx: PipelineContext, next_fn: NextFn) -> None:
        await record_audit_event(ctx, "message_created", {
            "intent": ctx.envelope.data.intent.value if ctx.envelope.data else None,
            "sender_type": ctx.envelope.data.sender.type.value if ctx.envelope.data and ctx.envelope.data.sender else None,
        })

        await next_fn(ctx)

        if ctx.delivery_plan:
            await record_audit_event(ctx, "message_routed", {
                "mode": ctx.delivery_plan.mode,
                "target_count": len(ctx.delivery_plan.resolved_targets),
            })

        if ctx.delivery_results:
            await record_audit_event(ctx, "message_delivering", {
                "target_count": len(ctx.delivery_results),
            })

        delivered = [r for r in ctx.delivery_results if r.success]
        failed = [r for r in ctx.delivery_results if not r.success]

        if ctx.error:
            await record_audit_event(ctx, "message_pipeline_error", {
                "error": ctx.error,
            })
        elif failed and not delivered:
            await record_audit_event(ctx, "message_delivery_failed", {
                "failed_targets": [r.target_node_id for r in failed],
                "errors": [r.error for r in failed],
            })
        elif delivered:
            await record_audit_event(ctx, "message_delivered", {
                "delivered_to": [r.target_node_id for r in delivered],
                "failed_targets": [r.target_node_id for r in failed] if failed else [],
                "mode": ctx.delivery_plan.mode if ctx.delivery_plan else "unknown",
            })

            envelope = ctx.envelope
            sender = envelope.data.sender if envelope.data else None
            if sender and sender.type and sender.type.value == "agent":
                from app.core import hooks as _hooks
                await _hooks.emit(
                    "operation_audit",
                    action="agent.message_sent",
                    target_type="workspace",
                    target_id=ctx.workspace_id or "",
                    actor_type="agent",
                    actor_id=sender.id,
                    details={
                        "delivered_to": [r.target_node_id for r in delivered],
                        "intent": envelope.data.intent.value if envelope.data else None,
                    },
                )

        retried = ctx.extra.get("retried_targets", [])
        for target_id in retried:
            await record_audit_event(ctx, "message_retried", {
                "target_node_id": target_id,
            })

        dead_lettered = ctx.extra.get("dead_lettered_targets", [])
        for target_id in dead_lettered:
            await record_audit_event(ctx, "message_dead_lettered", {
                "target_node_id": target_id,
            })
