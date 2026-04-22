"""Fetch available models from LLM provider APIs with in-memory caching."""

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field

import httpx

from app.core.config import settings
from app.schemas.llm import ModelInfo
from app.services.codex_provider import CODEX_MODELS, is_codex_provider

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 600


def _make_client(verify: bool = True, **kwargs) -> httpx.AsyncClient:
    proxy = settings.HTTPS_PROXY or None
    return httpx.AsyncClient(proxy=proxy, verify=verify, trust_env=True, **kwargs)

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
    "openai": "openai-completions",
    "anthropic": "anthropic-messages",
    "gemini": "google-generative-ai",
    "openrouter": "openai-completions",
    "minimax-openai": "openai-completions",
    "minimax-anthropic": "anthropic-messages",
}


def _infer_api_type(provider: str) -> str:
    return PROVIDER_API_TYPE.get(provider, "openai-completions")


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
    provider: str, api_key: str, *, base_url: str | None = None, api_type: str | None = None,
    skip_cache: bool = False, skip_ssl_verify: bool = False,
) -> list[ModelInfo]:
    if is_codex_provider(provider):
        return list(CODEX_MODELS)

    if not skip_cache:
        cached = _get_cached(provider, api_key)
        if cached is not None:
            return cached

    if base_url:
        _url = base_url
        _verify = not skip_ssl_verify
        resolved_type = api_type or _infer_api_type(provider)
        if resolved_type == "anthropic-messages":
            async def _custom_fetcher(key: str) -> list[ModelInfo]:
                return await _fetch_anthropic_compatible(key, _url, verify=_verify)
        else:
            async def _custom_fetcher(key: str) -> list[ModelInfo]:
                return await _fetch_openai_compatible(key, _url, verify=_verify)

        fetcher = _custom_fetcher
    else:
        fetcher = _FETCHERS.get(provider)
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
    except json.JSONDecodeError as e:
        logger.error("拉取 %s 模型列表失败: 响应非 JSON (base_url=%s): %s", provider, base_url, e)
        raise ValueError("模型列表接口返回了无效响应，该 API 地址可能不支持自动获取模型列表") from e
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
    ModelInfo(id="MiniMax-M2.7", name="MiniMax-M2.7", context_window=204800),
    ModelInfo(id="MiniMax-M2.7-highspeed", name="MiniMax-M2.7 Highspeed", context_window=204800),
    ModelInfo(id="MiniMax-M2.5", name="MiniMax-M2.5", context_window=204800),
    ModelInfo(id="MiniMax-M2.5-highspeed", name="MiniMax-M2.5 Highspeed", context_window=204800),
    ModelInfo(id="MiniMax-M2.1", name="MiniMax-M2.1", context_window=204800),
    ModelInfo(id="MiniMax-M2.1-highspeed", name="MiniMax-M2.1 Highspeed", context_window=204800),
    ModelInfo(id="MiniMax-M2", name="MiniMax-M2", context_window=204800),
]


async def _fetch_minimax(_api_key: str) -> list[ModelInfo]:
    """Minimax 没有模型列表 API，返回官方已知的文本模型。"""
    return list(_MINIMAX_TEXT_MODELS)


async def _fetch_openai_compatible(api_key: str, base_url: str, *, verify: bool = True) -> list[ModelInfo]:
    base = base_url.rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    url = f"{base}/models"
    async with _make_client(verify=verify, timeout=15) as client:
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


async def _fetch_anthropic_compatible(api_key: str, base_url: str, *, verify: bool = True) -> list[ModelInfo]:
    base = base_url.rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    url = f"{base}/models"
    async with _make_client(verify=verify, timeout=15) as client:
        resp = await client.get(
            url,
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
        if not mid:
            continue
        name = m.get("display_name") or m.get("name") or mid
        ctx = m.get("max_input_tokens")
        max_tok = m.get("max_tokens")
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


# ══════════════════════════════════════════════════════════
# Chat Completion Test
# ══════════════════════════════════════════════════════════

DEFAULT_TEST_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-haiku-20240307",
    "gemini": "gemini-2.0-flash-lite",
    "openrouter": "openai/gpt-4o-mini",
    "minimax-openai": "MiniMax-M2.5",
    "minimax-anthropic": "MiniMax-M2.5",
}


@dataclass
class ChatTestResult:
    ok: bool
    model: str
    message: str
    latency_ms: int = 0
    error_detail: str | None = None


def _sanitize_url(url: str) -> str:
    return re.sub(r"(key=)[^&]+", r"\1***", url)


def _build_error_detail(url: str, status: int | None = None, body: str = "") -> str:
    parts = [f"URL: {_sanitize_url(url)}"]
    if status is not None:
        parts.append(f"HTTP {status}")
    if body:
        parts.append(body[:200])
    return " | ".join(parts)


async def test_provider_chat_completion(
    provider: str,
    api_key: str,
    model: str | None = None,
    *,
    base_url: str | None = None,
    api_type: str | None = None,
    skip_ssl_verify: bool = False,
) -> ChatTestResult:
    if is_codex_provider(provider):
        return ChatTestResult(ok=True, model=model or "codex", message="连接成功")

    resolved_model = model or DEFAULT_TEST_MODELS.get(provider)
    if not resolved_model:
        return ChatTestResult(
            ok=False, model="",
            message="自定义供应商需要指定测试模型",
        )

    resolved_type = api_type or _infer_api_type(provider)
    verify = not skip_ssl_verify

    if base_url:
        target_base = base_url.rstrip("/")
    else:
        target_base_raw = PROVIDER_BASE_URLS.get(provider)
        if not target_base_raw:
            return ChatTestResult(
                ok=False, model=resolved_model,
                message=f"不支持的供应商 {provider}，请配置 Base URL",
            )
        target_base = target_base_raw

    t0 = time.monotonic()
    try:
        if resolved_type == "google-generative-ai":
            await _test_gemini_chat(api_key, resolved_model, target_base, verify=verify)
        elif resolved_type == "anthropic-messages":
            url = f"{target_base}/messages" if base_url else f"{target_base}/v1/messages"
            await _test_anthropic_chat(api_key, resolved_model, url, verify=verify)
        else:
            url = f"{target_base}/chat/completions" if base_url else f"{target_base}/v1/chat/completions"
            await _test_openai_chat(api_key, resolved_model, url, verify=verify)

        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.info("测试 %s chat completion 成功: model=%s latency=%dms", provider, resolved_model, latency_ms)
        return ChatTestResult(ok=True, model=resolved_model, message="连接成功", latency_ms=latency_ms)

    except httpx.HTTPStatusError as e:
        latency_ms = int((time.monotonic() - t0) * 1000)
        status = e.response.status_code
        body = e.response.text[:200] if e.response.text else ""
        detail = _build_error_detail(str(e.request.url), status, body)

        if status in (401, 403):
            msg = f"认证失败 (HTTP {status})，请检查 API Key 是否有效且有访问权限"
        elif status == 404:
            msg = "端点不存在 (HTTP 404)，请检查 Base URL 是否正确"
        elif status == 429:
            msg = "请求过于频繁 (HTTP 429)，请稍后重试"
        elif status >= 500:
            msg = f"服务端错误 (HTTP {status})，供应商服务可能暂时不可用"
        else:
            msg = f"请求失败 (HTTP {status})"

        logger.error("测试 %s chat completion 失败 (HTTP %s): %s", provider, status, detail)
        return ChatTestResult(ok=False, model=resolved_model, message=msg, latency_ms=latency_ms, error_detail=detail)

    except httpx.ConnectError as e:
        latency_ms = int((time.monotonic() - t0) * 1000)
        err_str = str(e)
        if "SSL" in err_str or "certificate" in err_str.lower():
            msg = "SSL 证书验证失败，可尝试开启「跳过 SSL 验证」"
        else:
            msg = "连接失败，请检查 Base URL 是否可访问"
        logger.error("测试 %s chat completion 连接失败: %s", provider, e)
        return ChatTestResult(ok=False, model=resolved_model, message=msg, latency_ms=latency_ms, error_detail=err_str)

    except httpx.TimeoutException:
        latency_ms = int((time.monotonic() - t0) * 1000)
        logger.error("测试 %s chat completion 超时", provider)
        return ChatTestResult(
            ok=False, model=resolved_model,
            message="请求超时，请检查网络连接或稍后重试",
            latency_ms=latency_ms,
        )

    except Exception as e:
        latency_ms = int((time.monotonic() - t0) * 1000)
        err_str = str(e)
        if "SSL" in err_str or "certificate" in err_str.lower():
            msg = "SSL 证书验证失败，可尝试开启「跳过 SSL 验证」"
        else:
            msg = f"测试失败: {err_str}"
        logger.error("测试 %s chat completion 失败: %s", provider, e)
        return ChatTestResult(ok=False, model=resolved_model, message=msg, latency_ms=latency_ms, error_detail=err_str)


async def _test_openai_chat(api_key: str, model: str, url: str, *, verify: bool = True) -> None:
    async with _make_client(verify=verify, timeout=30) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
        )
        resp.raise_for_status()


async def _test_anthropic_chat(api_key: str, model: str, url: str, *, verify: bool = True) -> None:
    async with _make_client(verify=verify, timeout=30) as client:
        resp = await client.post(
            url,
            headers={"X-Api-Key": api_key, "anthropic-version": "2023-06-01"},
            json={"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
        )
        resp.raise_for_status()


async def _test_gemini_chat(api_key: str, model: str, base_url: str, *, verify: bool = True) -> None:
    url = f"{base_url}/v1beta/models/{model}:generateContent"
    async with _make_client(verify=verify, timeout=30) as client:
        resp = await client.post(
            url,
            params={"key": api_key},
            json={"contents": [{"parts": [{"text": "hi"}]}], "generationConfig": {"maxOutputTokens": 1}},
        )
        resp.raise_for_status()
