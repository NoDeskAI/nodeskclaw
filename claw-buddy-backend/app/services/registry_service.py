"""Registry service: fetch image tags from Docker Registry HTTP API v2."""

import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.config_service import get_config

logger = logging.getLogger(__name__)

# Default timeout for registry requests
_TIMEOUT = 10.0


async def list_image_tags(
    db: AsyncSession,
    registry_url: str | None = None,
) -> list[dict]:
    """
    Query a Docker Registry v2 for available tags.
    Returns list of {"tag": str, "digest": str | None}.
    优先使用 registry_url 参数，其次从数据库/环境变量读取 image_registry 配置。
    """
    if not registry_url:
        registry_url = await get_config("image_registry", db)

    registry = (registry_url or "").strip().rstrip("/")
    if not registry:
        return []

    # Parse registry URL: expect format like "registry.example.com/repo"
    if "://" in registry:
        url = registry
    else:
        url = f"https://{registry}"

    parts = url.split("/")
    if len(parts) >= 4:
        base_url = "/".join(parts[:3])
        repo = "/".join(parts[3:])
    else:
        base_url = url
        repo = "library/openclaw"

    if not repo:
        repo = "library/openclaw"

    tags_url = f"{base_url}/v2/{repo}/tags/list"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, verify=False) as client:
            resp = await client.get(tags_url)
            resp.raise_for_status()
            data = resp.json()

            raw_tags = data.get("tags") or []

            def _sort_key(t: str) -> tuple:
                if t == "latest":
                    return (0, t)
                if t.startswith("v") and any(c.isdigit() for c in t):
                    return (1, t)
                return (2, t)

            raw_tags.sort(key=_sort_key)
            return [{"tag": t, "digest": None} for t in raw_tags]

    except httpx.HTTPStatusError as e:
        logger.warning("Registry 返回错误 %s: %s", e.response.status_code, tags_url)
        return []
    except Exception as e:
        logger.warning("Registry 请求失败 (%s): %s", tags_url, e)
        return []
