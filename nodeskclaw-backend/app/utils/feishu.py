"""Feishu (Lark) OAuth API wrapper.

基于飞书官方文档：
- 步骤二：code + client_id + client_secret → user_access_token
- 步骤三：user_access_token → user_info
- 步骤四：refresh_token → 刷新 user_access_token
"""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# v2 OAuth 接口，直接用 client_id/client_secret 换 user_access_token
FEISHU_USER_TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
FEISHU_USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"


async def exchange_code_for_user(code: str, redirect_uri: str | None = None) -> dict:
    """
    用 OAuth code 换取用户信息。

    流程（参考飞书文档）：
    1. code + client_id + client_secret → user_access_token
    2. user_access_token → user_info

    Args:
        code: 飞书 OAuth 授权码
        redirect_uri: 前端实际使用的回调地址（优先使用，保证和授权时一致）

    Returns:
        {
            "open_id": str,
            "union_id": str,
            "name": str,
            "email": str | None,
            "avatar_url": str | None,
        }
    """
    # 优先使用前端传来的 redirect_uri，保证和授权时一致
    actual_redirect_uri = redirect_uri or settings.FEISHU_REDIRECT_URI

    async with httpx.AsyncClient(timeout=10) as client:
        # Step 1: code → user_access_token
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

        # v2 接口：成功时直接返回 access_token；失败时有 code/message
        # v1 接口：嵌套在 data 里
        if "access_token" in token_data:
            user_access_token = token_data["access_token"]
        elif token_data.get("data", {}).get("access_token"):
            user_access_token = token_data["data"]["access_token"]
        else:
            raise ValueError(
                f"飞书 code 换 token 失败: {token_data}"
            )

        # Step 2: user_access_token → user_info
        resp = await client.get(
            FEISHU_USER_INFO_URL,
            headers={"Authorization": f"Bearer {user_access_token}"},
        )
        info_data = resp.json()
        logger.info("飞书 user_info 接口响应: %s", info_data)
        if info_data.get("code") != 0:
            raise ValueError(f"获取飞书用户信息失败: {info_data.get('msg')}")

        user = info_data["data"]
        return {
            "open_id": user.get("open_id", ""),
            "union_id": user.get("union_id", ""),
            "user_id": user.get("user_id", ""),
            "name": user.get("name", ""),
            "email": user.get("email") or user.get("enterprise_email"),
            "mobile": user.get("mobile"),
            "avatar_url": user.get("avatar_url") or user.get("avatar_big") or user.get("avatar_middle"),
            "tenant_key": user.get("tenant_key"),
        }
