"""Webhook endpoints for external channel integrations (Feishu, etc.)."""

import hashlib
import json
import logging

from fastapi import APIRouter, HTTPException, Request

from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify_feishu_signature(request: Request, body_bytes: bytes) -> None:
    """Verify Feishu webhook request signature when FEISHU_VERIFICATION_TOKEN is set."""
    token = settings.FEISHU_VERIFICATION_TOKEN
    if not token:
        return

    timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
    nonce = request.headers.get("X-Lark-Request-Nonce", "")
    signature = request.headers.get("X-Lark-Signature", "")

    if signature:
        raw = f"{timestamp}{nonce}{token}".encode() + body_bytes
        expected = hashlib.sha256(raw).hexdigest()
        if signature != expected:
            raise HTTPException(status_code=403, detail="Invalid webhook signature")
        return

    try:
        body_json = json.loads(body_bytes)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid request body")

    body_token = body_json.get("token", "")
    if body_token != token:
        raise HTTPException(status_code=403, detail="Invalid verification token")


@router.post("/feishu/workspace-message")
async def feishu_workspace_message(request: Request):
    """Receive Feishu bot message callback, inject into workspace.

    Delegates to the shared ``_handle_message_event`` which supports both
    group chat (chat_id) and private chat (open_id) matching.
    """
    body_bytes = await request.body()
    _verify_feishu_signature(request, body_bytes)

    body = json.loads(body_bytes)

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
