"""Portal ingestion — converts Portal HTTP requests into MessageEnvelopes."""

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

MENTION_ALL_SENTINEL = "__all__"


def build_portal_envelope(
    *,
    workspace_id: str,
    user_id: str,
    user_name: str,
    content: str,
    mentions: list[str] | None = None,
    attachments: list[dict] | None = None,
    conversation_id: str | None = None,
) -> MessageEnvelope:
    mention_targets = mentions or []
    routing_targets = [] if MENTION_ALL_SENTINEL in mention_targets else mention_targets
    routing_mode = "unicast" if len(routing_targets) == 1 else "multicast"
    extensions: dict = {}
    if conversation_id:
        extensions["conversation_id"] = conversation_id
    if mention_targets:
        extensions["mention_targets"] = mention_targets

    return MessageEnvelope(
        source=f"portal/user/{user_id}",
        type="deskclaw.msg.v1.chat",
        workspaceid=workspace_id,
        data=MessageData(
            sender=MessageSender(
                id=user_id,
                type=SenderType.USER,
                name=user_name,
            ),
            intent=IntentType.CHAT,
            content=content,
            mentions=mention_targets,
            attachments=attachments or [],
            routing=MessageRouting(mode=routing_mode, targets=routing_targets),
            extensions=extensions,
            priority=Priority.NORMAL,
        ),
    )
