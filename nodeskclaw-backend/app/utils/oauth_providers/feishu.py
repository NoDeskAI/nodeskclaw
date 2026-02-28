"""Feishu (Lark) OAuth provider implementation."""

import logging

import httpx

from app.core.config import settings
from app.utils.oauth_providers.base import OAuthProvider, OAuthUserInfo

logger = logging.getLogger(__name__)

FEISHU_USER_TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
FEISHU_USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"


class FeishuProvider(OAuthProvider):

    @property
    def name(self) -> str:
        return "feishu"

    async def exchange_code(self, code: str, redirect_uri: str | None = None) -> OAuthUserInfo:
        actual_redirect_uri = redirect_uri or settings.FEISHU_REDIRECT_URI

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                FEISHU_USER_TOKEN_URL,
                json={
                    "grant_type": "authorization_code",
                    "client_id": settings.FEISHU_APP_ID,
                    "client_secret": settings.FEISHU_APP_SECRET,
                    "code": code,
                    "redirect_uri": actual_redirect_uri,
                },
            )
            token_data = resp.json()
            logger.info("飞书 token 接口响应: %s", token_data)

            if "access_token" in token_data:
                user_access_token = token_data["access_token"]
            elif token_data.get("data", {}).get("access_token"):
                user_access_token = token_data["data"]["access_token"]
            else:
                raise ValueError(f"飞书 code 换 token 失败: {token_data}")

            resp = await client.get(
                FEISHU_USER_INFO_URL,
                headers={"Authorization": f"Bearer {user_access_token}"},
            )
            info_data = resp.json()
            logger.info("飞书 user_info 接口响应: %s", info_data)
            if info_data.get("code") != 0:
                raise ValueError(f"获取飞书用户信息失败: {info_data.get('msg')}")

            user = info_data["data"]
            return OAuthUserInfo(
                provider="feishu",
                provider_user_id=user.get("open_id", ""),
                provider_tenant_id=user.get("tenant_key"),
                name=user.get("name", ""),
                email=user.get("email") or user.get("enterprise_email"),
                avatar_url=user.get("avatar_url") or user.get("avatar_big") or user.get("avatar_middle"),
            )
