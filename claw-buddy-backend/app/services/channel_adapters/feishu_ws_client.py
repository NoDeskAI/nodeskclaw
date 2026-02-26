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
    """Core message routing — shared between webhook and ws modes."""
    from sqlalchemy import select

    from app.core.deps import async_session_factory
    from app.models.base import not_deleted
    from app.models.workspace_member import WorkspaceMember
    from app.services import workspace_message_service as msg_service

    if not chat_id or not content:
        return

    async with async_session_factory() as db:
        result = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.channel_type == "feishu",
                not_deleted(WorkspaceMember),
            )
        )
        target_member = None
        for member in result.scalars().all():
            config = member.channel_config or {}
            if config.get("chat_id") == chat_id:
                target_member = member
                break

        if not target_member:
            logger.warning("Feishu WS: no member for chat_id=%s", chat_id)
            return

        workspace_id = target_member.workspace_id

        await msg_service.record_message(
            db,
            workspace_id=workspace_id,
            sender_type="human",
            sender_id=target_member.user_id,
            sender_name=f"Human:{target_member.user_id}",
            content=content,
            message_type="chat",
        )

        from app.services import corridor_router
        from app.models.corridor import HumanHex
        from app.models.base import not_deleted
        from sqlalchemy import select as sa_select

        hh_q = await db.execute(
            sa_select(HumanHex.hex_q, HumanHex.hex_r).where(
                HumanHex.workspace_id == workspace_id,
                HumanHex.user_id == target_member.user_id,
                not_deleted(HumanHex),
            )
        )
        all_agent_ids: set[str] = set()
        for row in hh_q.all():
            endpoints = await corridor_router.get_reachable_endpoints(
                workspace_id, row.hex_q, row.hex_r, db
            )
            all_agent_ids.update(ep.entity_id for ep in endpoints if ep.endpoint_type == "agent")
        if all_agent_ids:
            from app.services.collaboration_service import send_system_message_to_agents

            await send_system_message_to_agents(
                workspace_id, list(all_agent_ids), content, db
            )

        from app.api.workspaces import broadcast_event

        broadcast_event(workspace_id, "human:message_received", {
            "user_id": target_member.user_id,
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
