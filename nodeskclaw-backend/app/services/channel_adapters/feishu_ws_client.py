"""Feishu WebSocket long-connection client using lark-oapi SDK.

Receives im.message.receive_v1 events and routes them into the workspace,
reusing the same message handling logic as the HTTP webhook endpoint.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import TYPE_CHECKING

import lark_oapi as lark
from lark_oapi.api.im.v1.model.p2_im_message_receive_v1 import P2ImMessageReceiveV1
from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
from lark_oapi.ws import Client as LarkWSClient

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


async def _handle_message_event(
    chat_id: str,
    sender_open_id: str,
    content: str,
) -> None:
    """Core message routing — shared between webhook and ws modes.

    Matching priority:
    1. chat_id → HumanHex.channel_config.chat_id  (group chat)
    2. sender_open_id → user_oauth_connections → HumanHex.user_id  (private chat)
    """
    from sqlalchemy import select

    from app.core.deps import async_session_factory
    from app.models.base import not_deleted
    from app.models.corridor import HumanHex
    from app.services import workspace_message_service as msg_service

    if not content:
        return

    async with async_session_factory() as db:
        target_hex: HumanHex | None = None

        if chat_id:
            result = await db.execute(
                select(HumanHex).where(
                    HumanHex.channel_type == "feishu",
                    not_deleted(HumanHex),
                )
            )
            for hh in result.scalars().all():
                cfg = hh.channel_config or {}
                if cfg.get("chat_id") == chat_id:
                    target_hex = hh
                    break

        if not target_hex and sender_open_id:
            from app.models.oauth_connection import UserOAuthConnection
            oauth_q = await db.execute(
                select(UserOAuthConnection.user_id).where(
                    UserOAuthConnection.provider == "feishu",
                    UserOAuthConnection.provider_user_id == sender_open_id,
                    not_deleted(UserOAuthConnection),
                )
            )
            user_id = oauth_q.scalar_one_or_none()
            if user_id:
                hh_q = await db.execute(
                    select(HumanHex).where(
                        HumanHex.user_id == user_id,
                        not_deleted(HumanHex),
                    ).order_by(HumanHex.created_at.desc())
                )
                target_hex = hh_q.scalars().first()

        if not target_hex:
            logger.warning(
                "Feishu message: no human hex for chat_id=%s open_id=%s",
                chat_id, sender_open_id,
            )
            return

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


def _extract_text_content(message: dict) -> str:
    msg_type = message.get("message_type", "")
    if msg_type == "text":
        try:
            return json.loads(message.get("content", "{}")).get("text", "")
        except Exception:
            return message.get("content", "")
    return f"[{msg_type} message]"


class FeishuWSClient:
    """Manages a single Feishu WebSocket long-connection for one app."""

    def __init__(self, app_id: str, app_secret: str, encrypt_key: str = "", verification_token: str = ""):
        self._app_id = app_id
        self._app_secret = app_secret
        self._thread: threading.Thread | None = None
        self._client: LarkWSClient | None = None

        handler = (
            EventDispatcherHandler.builder(encrypt_key, verification_token)
            .register_p2_im_message_receive_v1(self._on_message)
            .build()
        )

        self._client = LarkWSClient(
            app_id=app_id,
            app_secret=app_secret,
            event_handler=handler,
            log_level=lark.LogLevel.WARNING,
        )

    def _on_message(self, event: P2ImMessageReceiveV1) -> None:
        """Called by lark-oapi when im.message.receive_v1 arrives."""
        import asyncio

        msg = event.event.message
        sender = event.event.sender

        chat_id = msg.chat_id if msg else ""
        sender_open_id = sender.sender_id.open_id if sender and sender.sender_id else ""

        message_dict = {}
        if msg:
            message_dict = {
                "message_type": msg.message_type or "",
                "content": msg.content or "",
            }
        content = _extract_text_content(message_dict)

        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(
                _handle_message_event(chat_id, sender_open_id, content)
            )
            loop.close()
        except Exception as e:
            logger.error("Feishu WS message handling error: %s", e)

    def start(self) -> None:
        """Start the WebSocket connection in a background daemon thread."""
        if self._thread and self._thread.is_alive():
            logger.warning("Feishu WS client already running for app_id=%s", self._app_id)
            return

        def _run() -> None:
            try:
                logger.info("Starting Feishu WS long-connection: app_id=%s", self._app_id)
                self._client.start()
            except Exception as e:
                logger.error("Feishu WS client crashed: app_id=%s err=%s", self._app_id, e)

        self._thread = threading.Thread(target=_run, daemon=True, name=f"feishu-ws-{self._app_id[:8]}")
        self._thread.start()

    def stop(self) -> None:
        """Best-effort shutdown. The daemon thread will terminate with the process."""
        logger.info("Stopping Feishu WS client: app_id=%s", self._app_id)
