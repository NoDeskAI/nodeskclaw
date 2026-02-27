"""Feishu channel adapter — delivers workspace messages to Feishu group chats."""

from __future__ import annotations

import logging

import httpx

from app.services.channel_adapters.base import ChannelAdapter

logger = logging.getLogger(__name__)


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
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": self._app_id, "app_secret": self._app_secret},
            )
            data = resp.json()
            self._token = data.get("tenant_access_token", "")
            return self._token or ""

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
                    "https://open.feishu.cn/open-apis/im/v1/messages",
                    params={"receive_id_type": "chat_id"},
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "receive_id": chat_id,
                        "msg_type": "text",
                        "content": f'{{"text": "{text}"}}',
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

        token = await self._get_tenant_token()
        if not token:
            return False

        import json
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

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://open.feishu.cn/open-apis/im/v1/messages",
                    params={"receive_id_type": "chat_id"},
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "receive_id": chat_id,
                        "msg_type": "interactive",
                        "content": json.dumps(card_content),
                    },
                )
                return resp.status_code == 200 and resp.json().get("code") == 0
        except Exception as e:
            logger.error("Feishu approval request error: %s", e)
            return False
