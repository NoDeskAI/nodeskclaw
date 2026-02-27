"""Webhook endpoints for external channel integrations (Feishu, etc.)."""

import json
import logging

from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import async_session_factory
from app.models.base import not_deleted
from app.models.corridor import HumanHex
from app.services import workspace_message_service as msg_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/feishu/workspace-message")
async def feishu_workspace_message(request: Request):
    """Receive Feishu bot message callback, inject into workspace."""
    body = await request.json()

    if "challenge" in body:
        return {"challenge": body["challenge"]}

    event = body.get("event", {})
    message = event.get("message", {})
    chat_id = message.get("chat_id", "")
    sender_id = event.get("sender", {}).get("sender_id", {}).get("open_id", "")

    content = ""
    msg_type = message.get("message_type", "")
    if msg_type == "text":
        try:
            content = json.loads(message.get("content", "{}")).get("text", "")
        except Exception:
            content = message.get("content", "")
    else:
        content = f"[{msg_type} message]"

    if not chat_id or not content:
        return {"code": 0}

    async with async_session_factory() as db:
        result = await db.execute(
            select(HumanHex).where(
                HumanHex.channel_type == "feishu",
                not_deleted(HumanHex),
            )
        )
        target_hex = None
        for hh in result.scalars().all():
            cfg = hh.channel_config or {}
            if cfg.get("chat_id") == chat_id:
                target_hex = hh
                break

        if not target_hex:
            logger.warning("Feishu webhook: no human hex found for chat_id=%s", chat_id)
            return {"code": 0}

        workspace_id = target_hex.workspace_id

        await msg_service.record_message(
            db,
            workspace_id=workspace_id,
            sender_type="human",
            sender_id=target_hex.user_id,
            sender_name=f"Human:{target_hex.user_id}",
            content=content,
            message_type="chat",
        )

        from app.services import corridor_router

        endpoints = await corridor_router.get_reachable_endpoints(
            workspace_id, target_hex.hex_q, target_hex.hex_r, db
        )
        agent_ids = [ep.entity_id for ep in endpoints if ep.endpoint_type == "agent"]
        if agent_ids:
            from app.services.collaboration_service import send_system_message_to_agents

            await send_system_message_to_agents(
                workspace_id, agent_ids, content, db
            )

        from app.api.workspaces import broadcast_event

        broadcast_event(workspace_id, "human:message_received", {
            "user_id": target_hex.user_id,
            "content": content[:200],
        })

    return {"code": 0}
