"""Fetch available models from LLM provider APIs with in-memory caching."""

import hashlib
import logging
import time

import httpx

from app.core.config import settings
from app.schemas.llm import ModelInfo

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 600


def _make_client(**kwargs) -> httpx.AsyncClient:
    proxy = settings.HTTPS_PROXY or None
    return httpx.AsyncClient(proxy=proxy, **kwargs)

_cache: dict[str, tuple[float, list[ModelInfo]]] = {}

PROVIDER_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com",
    "openrouter": "https://openrouter.ai/api",
    "minimax-openai": "https://api.minimaxi.com",
    "minimax-anthropic": "https://api.minimaxi.com/anthropic",
}

PROVIDER_API_TYPE: dict[str, str] = {
    "gemini": "google-generative-ai",
    "minimax-openai": "openai-completions",
    "minimax-anthropic": "anthropic-messages",
}


def _cache_key(provider: str, api_key: str) -> str:
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:12]
    return f"{provider}:{key_hash}"


def _get_cached(provider: str, api_key: str) -> list[ModelInfo] | None:
    ck = _cache_key(provider, api_key)
    entry = _cache.get(ck)
    if entry and (time.time() - entry[0]) < CACHE_TTL_SECONDS:
        return entry[1]
    return None


def _set_cache(provider: str, api_key: str, models: list[ModelInfo]) -> None:
    ck = _cache_key(provider, api_key)
    _cache[ck] = (time.time(), models)


async def fetch_provider_models(
    provider: str, api_key: str, *, base_url: str | None = None,
) -> list[ModelInfo]:
    cached = _get_cached(provider, api_key)
    if cached is not None:
        return cached

    fetcher = _FETCHERS.get(provider)
    if not fetcher and base_url:
        _url = base_url

        async def _custom_fetcher(key: str) -> list[ModelInfo]:
            return await _fetch_openai_compatible(key, _url)

        fetcher = _custom_fetcher
    if not fetcher:
        logger.warning("不支持的 provider: %s", provider)
        return []

    try:
        models = await fetcher(api_key)
        _set_cache(provider, api_key, models)
        logger.info("已拉取 %s 模型列表: %d 个", provider, len(models))
        return models
    except httpx.HTTPStatusError as e:
        logger.error("拉取 %s 模型列表失败 (HTTP %s): %s", provider, e.response.status_code, e)
        raise ValueError(f"API 返回 {e.response.status_code}，请检查 Key 是否有效") from e
    except httpx.TimeoutException:
        logger.error("拉取 %s 模型列表超时", provider)
        raise ValueError("请求超时，请稍后重试")
    except Exception as e:
        logger.error("拉取 %s 模型列表失败: %s", provider, e)
        raise ValueError(f"拉取模型列表失败: {e}") from e


async def _fetch_openai(api_key: str) -> list[ModelInfo]:
    async with _make_client(timeout=15) as client:
        resp = await client.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
    models = []
    for m in data:
        mid: str = m.get("id", "")
        if not mid.startswith(("gpt-", "o1", "o3", "o4", "chatgpt-")):
            continue
        if any(kw in mid for kw in ("instruct", "realtime", "audio", "transcribe")):
            continue
        models.append(ModelInfo(id=mid, name=mid))
    models.sort(key=lambda x: x.id)
    return models


async def _fetch_anthropic(api_key: str) -> list[ModelInfo]:
    async with _make_client(timeout=15) as client:
        resp = await client.get(
            "https://api.anthropic.com/v1/models",
            headers={
                "X-Api-Key": api_key,
                "anthropic-version": "2023-06-01",
            },
            params={"limit": 100},
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
    models = []
    for m in data:
        mid = m.get("id", "")
        name = m.get("display_name") or mid
        models.append(ModelInfo(id=mid, name=name))
    models.sort(key=lambda x: x.id)
    return models


async def _fetch_gemini(api_key: str) -> list[ModelInfo]:
    async with _make_client(timeout=15) as client:
        resp = await client.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key, "pageSize": 100},
        )
        resp.raise_for_status()
        data = resp.json().get("models", [])
    models = []
    for m in data:
        methods = m.get("supportedGenerationMethods", [])
        if "generateContent" not in methods:
            continue
        raw_name: str = m.get("name", "")
        mid = raw_name.removeprefix("models/")
        display = m.get("displayName") or mid
        ctx = m.get("inputTokenLimit")
        out = m.get("outputTokenLimit")
        models.append(ModelInfo(id=mid, name=display, context_window=ctx, max_tokens=out))
    models.sort(key=lambda x: x.id)
    return models


async def _fetch_openrouter(api_key: str) -> list[ModelInfo]:
    async with _make_client(timeout=20) as client:
        resp = await client.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
    models = []
    for m in data:
        mid = m.get("id", "")
        name = m.get("name") or mid
        ctx = m.get("context_length")
        models.append(ModelInfo(id=mid, name=name, context_window=ctx))
    models.sort(key=lambda x: x.name)
    return models


_MINIMAX_TEXT_MODELS: list[ModelInfo] = [
    ModelInfo(id="MiniMax-M2.5", name="MiniMax-M2.5", context_window=204800),
    ModelInfo(id="MiniMax-M2.5-highspeed", name="MiniMax-M2.5 Highspeed", context_window=204800),
    ModelInfo(id="MiniMax-M2.1", name="MiniMax-M2.1", context_window=204800),
    ModelInfo(id="MiniMax-M2.1-highspeed", name="MiniMax-M2.1 Highspeed", context_window=204800),
    ModelInfo(id="MiniMax-M2", name="MiniMax-M2", context_window=204800),
]


async def _fetch_minimax(_api_key: str) -> list[ModelInfo]:
    """Minimax 没有模型列表 API，返回官方已知的文本模型。"""
    return list(_MINIMAX_TEXT_MODELS)


async def _fetch_openai_compatible(api_key: str, base_url: str) -> list[ModelInfo]:
    url = f"{base_url.rstrip('/')}/models"
    async with _make_client(timeout=15) as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
    models = []
    for m in data:
        mid: str = m.get("id", "")
        if not mid:
            continue
        name = m.get("name") or mid
        ctx = m.get("context_length") or m.get("context_window")
        max_tok = m.get("max_tokens") or m.get("max_output_tokens")
        models.append(ModelInfo(id=mid, name=name, context_window=ctx, max_tokens=max_tok))
    models.sort(key=lambda x: x.id)
    return models


_FETCHERS: dict[str, object] = {
    "openai": _fetch_openai,
    "anthropic": _fetch_anthropic,
    "gemini": _fetch_gemini,
    "openrouter": _fetch_openrouter,
    "minimax-openai": _fetch_minimax,
    "minimax-anthropic": _fetch_minimax,
}
