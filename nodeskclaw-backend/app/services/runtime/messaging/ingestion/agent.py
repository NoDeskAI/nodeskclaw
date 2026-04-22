"""Agent ingestion — converts Channel Plugin SSE events into MessageEnvelopes."""

from __future__ import annotations

from app.services.runtime.messaging.envelope import (
    IntentType,
    MessageData,
    MessageEnvelope,
    MessageRouting,
    MessageSender,
    Priority,
    SenderType,
)


def build_agent_collaboration_envelope(
    *,
    workspace_id: str,
    source_instance_id: str,
    source_name: str,
    target: str,
    content: str,
    depth: int = 0,
) -> MessageEnvelope:
    targets = []
    mode = "broadcast"
    if target and target != "broadcast":
        parts = target.split(":", 1)
        if len(parts) == 2:
            targets = [parts[1]]
            mode = "unicast"

    return MessageEnvelope(
        source=f"agent/{source_instance_id}",
        type="deskclaw.msg.v1.collaborate",
        workspaceid=workspace_id,
        data=MessageData(
            sender=MessageSender(
                id=source_instance_id,
                type=SenderType.AGENT,
                name=source_name,
                instance_id=source_instance_id,
            ),
            intent=IntentType.COLLABORATE,
            content=content,
            mentions=targets,
            priority=Priority.CRITICAL,
            extensions={"depth": depth, "mention_targets": targets},
            routing=MessageRouting(mode=mode, targets=targets, max_hops=5),
        ),
    )
