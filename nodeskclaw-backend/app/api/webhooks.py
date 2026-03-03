"""Webhook endpoints for external channel integrations (Feishu, etc.)."""

import json
import logging

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/feishu/workspace-message")
async def feishu_workspace_message(request: Request):
    """Receive Feishu bot message callback, inject into workspace.

    Delegates to the shared ``_handle_message_event`` which supports both
    group chat (chat_id) and private chat (open_id) matching.
    """
    body = await request.json()

    if "challenge" in body:
        return {"challenge": body["challenge"]}

    event = body.get("event", {})
    message = event.get("message", {})
    chat_id = message.get("chat_id", "")
    sender_open_id = event.get("sender", {}).get("sender_id", {}).get("open_id", "")

    content = ""
    msg_type = message.get("message_type", "")
    if msg_type == "text":
        try:
            content = json.loads(message.get("content", "{}")).get("text", "")
        except Exception:
            content = message.get("content", "")
    else:
        content = f"[{msg_type} message]"

    if not content:
        return {"code": 0}

    from app.services.channel_adapters.feishu_ws_client import _handle_message_event

    await _handle_message_event(chat_id, sender_open_id, content)

    return {"code": 0}
