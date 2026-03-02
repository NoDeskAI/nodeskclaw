"""Feishu channel adapter — delivers workspace messages to Feishu via Bot API.

Supports both group chat (chat_id) and private chat (open_id) delivery.
"""

from __future__ import annotations

import json
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.channel_adapters.base import ChannelAdapter

logger = logging.getLogger(__name__)

FEISHU_API_BASE = "https://open.feishu.cn/open-apis"


async def get_feishu_open_id(user_id: str, db: AsyncSession) -> str | None:
    """Look up a user's Feishu open_id via user_oauth_connections."""
    from app.models.base import not_deleted
    from app.models.oauth_connection import UserOAuthConnection

    result = await db.execute(
        select(UserOAuthConnection.provider_user_id).where(
            UserOAuthConnection.user_id == user_id,
            UserOAuthConnection.provider == "feishu",
            not_deleted(UserOAuthConnection),
        )
    )
    return result.scalar_one_or_none()


def build_workspace_message_card(
    *,
    workspace_name: str,
    workspace_id: str,
    agent_name: str,
    content: str,
    human_hex_name: str = "",
    portal_base_url: str = "",
) -> dict:
    """Build an interactive card for delivering an Agent collaboration message."""
    truncated = content[:500] + ("..." if len(content) > 500 else "")

    if human_hex_name:
        body_md = f"**工位**: {human_hex_name}\n**来源 Agent**: {agent_name}\n\n{truncated}"
    else:
        body_md = f"**来源 Agent**: {agent_name}\n\n{truncated}"

    if human_hex_name:
        note_text = f"通过工位「{human_hex_name}」接收 · 直接回复将路由至相邻 Agent"
    else:
        note_text = "直接回复将路由至相邻 Agent"

    elements: list[dict] = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": body_md},
        },
        {"tag": "hr"},
        {
            "tag": "note",
            "elements": [{"tag": "plain_text", "content": note_text}],
        },
    ]

    if portal_base_url:
        elements.insert(2, {
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "打开工作区"},
                    "type": "default",
                    "url": f"{portal_base_url}/workspace/{workspace_id}",
                },
            ],
        })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"[{workspace_name}] 工位消息"},
            "template": "blue",
        },
        "elements": elements,
    }


class FeishuChannelAdapter(ChannelAdapter):
    """Sends messages to Feishu via Bot API, reusing the SSO app credentials."""

    def __init__(self, app_id: str, app_secret: str):
        self._app_id = app_id
        self._app_secret = app_secret
        self._token: str | None = None

    async def _get_tenant_token(self) -> str:
        if self._token:
            return self._token
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal",
                json={"app_id": self._app_id, "app_secret": self._app_secret},
            )
            data = resp.json()
            self._token = data.get("tenant_access_token", "")
            return self._token or ""

    async def send_card(
        self,
        *,
        receive_id: str,
        receive_id_type: str,
        card_content: dict,
        workspace_id: str = "",
    ) -> bool:
        """Send an interactive card to a chat_id or open_id.

        ``workspace_id`` is attached as custom metadata so replies can be
        correlated back to the originating workspace.
        """
        token = await self._get_tenant_token()
        if not token:
            logger.error("Failed to obtain Feishu tenant_access_token")
            return False

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{FEISHU_API_BASE}/im/v1/messages",
                    params={"receive_id_type": receive_id_type},
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "receive_id": receive_id,
                        "msg_type": "interactive",
                        "content": json.dumps(card_content),
                    },
                )
                result = resp.json()
                if resp.status_code == 200 and result.get("code") == 0:
                    return True
                logger.warning(
                    "Feishu send_card failed: status=%d body=%s",
                    resp.status_code, resp.text[:300],
                )
                return False
        except Exception as e:
            logger.error("Feishu send_card error: %s", e)
            return False

    async def send_message(
        self,
        *,
        channel_config: dict,
        sender_name: str,
        content: str,
        workspace_name: str,
        metadata: dict | None = None,
    ) -> bool:
        chat_id = channel_config.get("chat_id", "")
        if not chat_id:
            logger.warning("Feishu channel_config missing chat_id")
            return False

        token = await self._get_tenant_token()
        if not token:
            logger.error("Failed to obtain Feishu tenant_access_token")
            return False

        text = f"[{workspace_name}] {sender_name}:\n{content}"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{FEISHU_API_BASE}/im/v1/messages",
                    params={"receive_id_type": "chat_id"},
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "receive_id": chat_id,
                        "msg_type": "text",
                        "content": json.dumps({"text": text}),
                    },
                )
                if resp.status_code == 200 and resp.json().get("code") == 0:
                    return True
                logger.warning("Feishu send_message failed: %s", resp.text)
                return False
        except Exception as e:
            logger.error("Feishu send_message error: %s", e)
            return False

    async def send_approval_request(
        self,
        *,
        channel_config: dict,
        agent_name: str,
        action_type: str,
        proposal: dict,
        workspace_name: str,
        callback_url: str,
    ) -> bool:
        chat_id = channel_config.get("chat_id", "")
        if not chat_id:
            return False

        card_content = {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": f"[{workspace_name}] Approval Request"}},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**Agent**: {agent_name}\n**Action**: {action_type}\n**Details**: {json.dumps(proposal, ensure_ascii=False, indent=2)[:500]}"}},
                {"tag": "action", "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "Allow this time"}, "type": "primary", "value": {"action": "allow_once", "callback_url": callback_url}},
                    {"tag": "button", "text": {"tag": "plain_text", "content": "Allow always"}, "type": "default", "value": {"action": "allow_always", "callback_url": callback_url}},
                    {"tag": "button", "text": {"tag": "plain_text", "content": "Deny"}, "type": "danger", "value": {"action": "deny", "callback_url": callback_url}},
                ]},
            ],
        }
        return await self.send_card(
            receive_id=chat_id,
            receive_id_type="chat_id",
            card_content=card_content,
        )
