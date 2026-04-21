"""LLM Proxy: resolves real API keys and forwards requests to upstream LLM providers."""

import json
import logging
import time
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy import func, select

from app.codex_cli import (
    CODEX_PROVIDER,
    CodexExecutionError,
    build_chat_completion_response,
    build_chat_completion_stream_events,
    list_codex_models,
    run_codex_chat_completion,
)
from app.config import settings
from app.database import get_session
from app.models import Instance, InstanceProviderConfig, LlmUsageLog, OrgLlmKey, UserLlmConfig, UserLlmKey, not_deleted

logger = logging.getLogger(__name__)

router = APIRouter()

PROVIDER_DEFAULTS: dict[str, dict] = {
    "codex": {"base_url": "", "auth_type": "bearer"},
    "openai": {"base_url": "https://api.openai.com", "auth_type": "bearer"},
    "anthropic": {"base_url": "https://api.anthropic.com", "auth_type": "x-api-key"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com", "auth_type": "query_param"},
    "openrouter": {"base_url": "https://openrouter.ai/api", "auth_type": "bearer"},
    "minimax-openai": {"base_url": "https://api.minimaxi.com", "auth_type": "bearer"},
    "minimax-anthropic": {"base_url": "https://api.minimaxi.com/anthropic", "auth_type": "bearer"},
}

_OPENAI_STREAM_PROVIDERS = {"openai", "openrouter", "minimax-openai"}

_API_TYPE_AUTH: dict[str, str] = {
    "openai-completions": "bearer",
    "anthropic-messages": "x-api-key",
    "google-generative-ai": "query_param",
}

_http_client: httpx.AsyncClient | None = None
_http_client_no_verify: httpx.AsyncClient | None = None


def _get_http_client(skip_ssl_verify: bool = False) -> httpx.AsyncClient:
    if skip_ssl_verify:
        global _http_client_no_verify
        if _http_client_no_verify is None or _http_client_no_verify.is_closed:
            _http_client_no_verify = httpx.AsyncClient(
                timeout=httpx.Timeout(300, connect=10), trust_env=True, verify=False,
            )
        return _http_client_no_verify

    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(300, connect=10), trust_env=True)
    return _http_client


def _extract_proxy_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    api_key = request.headers.get("x-api-key", "").strip()
    if api_key:
        return api_key
    return None


def _build_target_url(provider: str, path: str, base_url: str | None, api_key: str | None) -> str:
    base = (base_url or PROVIDER_DEFAULTS.get(provider, {}).get("base_url", "")).rstrip("/")
    if base.endswith("/v1") and path.startswith("v1/"):
        path = path[3:]
    url = f"{base}/{path}"

    prov_conf = PROVIDER_DEFAULTS.get(provider, {})
    if prov_conf.get("auth_type") == "query_param" and api_key:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        qs["key"] = [api_key]
        url = urlunparse(parsed._replace(query=urlencode(qs, doseq=True)))

    return url


def _build_auth_headers(
    provider: str, api_key: str, original_headers: dict, *, api_type: str | None = None,
) -> dict:
    headers = {}
    for k, v in original_headers.items():
        lower = k.lower()
        if lower in ("host", "content-length", "transfer-encoding", "authorization", "x-api-key", "accept-encoding"):
            continue
        headers[k] = v

    prov_conf = PROVIDER_DEFAULTS.get(provider, {})
    if prov_conf:
        auth_type = prov_conf.get("auth_type", "bearer")
    else:
        auth_type = _API_TYPE_AUTH.get(api_type or "", "bearer")

    if auth_type == "bearer":
        headers["authorization"] = f"Bearer {api_key}"
    elif auth_type == "x-api-key":
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"

    return headers


async def _check_quota(org_key_id: str, org_limit: int | None, sys_limit: int | None, db) -> tuple[bool, str]:
    if org_limit is None and sys_limit is None:
        return True, ""

    result = await db.execute(
        select(func.coalesce(func.sum(LlmUsageLog.total_tokens), 0))
        .where(LlmUsageLog.org_llm_key_id == org_key_id)
    )
    total_used = int(result.scalar())

    if org_limit is not None and total_used >= org_limit:
        return False, f"Working Plan 额度已用尽 ({total_used}/{org_limit} tokens)"
    if sys_limit is not None and total_used >= sys_limit:
        return False, f"系统额度已用尽 ({total_used}/{sys_limit} tokens)"
    return True, ""


def _maybe_inject_stream_options(body: bytes, provider: str) -> bytes:
    if provider not in _OPENAI_STREAM_PROVIDERS:
        return body
    try:
        data = json.loads(body)
        if data.get("stream") is True and "stream_options" not in data:
            data["stream_options"] = {"include_usage": True}
            return json.dumps(data).encode()
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass
    return body


def _parse_usage_from_response(body: bytes) -> dict:
    try:
        data = json.loads(body)
        usage = data.get("usage", {})
        return {
            "prompt_tokens": usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0) or usage.get("output_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "model": data.get("model"),
        }
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _parse_usage_from_sse_chunk(line: str) -> dict | None:
    if not line.startswith("data: "):
        return None
    payload = line[6:].strip()
    if payload == "[DONE]":
        return None
    try:
        data = json.loads(payload)
        usage = data.get("usage")
        if usage and (usage.get("total_tokens") or usage.get("prompt_tokens")):
            return {
                "prompt_tokens": usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0) or usage.get("output_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
                "model": data.get("model"),
            }
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass
    return None


def _strip_content_from_response(body: bytes) -> str | None:
    """Strip content fields from response JSON, keeping only metadata."""
    try:
        data = json.loads(body)
        if "choices" in data:
            for choice in data.get("choices", []):
                msg = choice.get("message")
                if isinstance(msg, dict) and "content" in msg:
                    msg["content"] = None
                delta = choice.get("delta")
                if isinstance(delta, dict) and "content" in delta:
                    delta["content"] = None
        return json.dumps(data, ensure_ascii=False)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _is_codex_path(path: str, *candidates: str) -> bool:
    normalized = path.strip("/")
    return normalized in candidates


async def _handle_codex_proxy(
    request: Request,
    path: str,
    ctx: "_RequestContext",
    *,
    api_key: str | None,
) -> JSONResponse | StreamingResponse | Response:
    normalized_path = path.strip("/")

    if request.method == "GET" and _is_codex_path(normalized_path, "v1/models", "models"):
        models = list_codex_models()
        return JSONResponse(status_code=200, content={"object": "list", "data": models})

    if request.method != "POST" or not _is_codex_path(normalized_path, "v1/chat/completions", "chat/completions"):
        return JSONResponse(
            status_code=404,
            content={"error": f"Codex 暂不支持路径 /{normalized_path or path}"},
        )

    start = time.monotonic()
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        await _record_usage(
            ctx,
            usage={},
            status_code=400,
            latency_ms=int((time.monotonic() - start) * 1000),
            error_message="请求体不是合法 JSON",
        )
        return JSONResponse(status_code=400, content={"error": "请求体不是合法 JSON"})

    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        await _record_usage(
            ctx,
            usage={},
            status_code=400,
            latency_ms=int((time.monotonic() - start) * 1000),
            error_message="Codex 请求缺少 messages",
        )
        return JSONResponse(status_code=400, content={"error": "Codex 请求缺少 messages"})

    request_model = payload.get("model")
    is_stream = bool(payload.get("stream"))

    try:
        result = await run_codex_chat_completion(
            messages=messages,
            model=request_model if isinstance(request_model, str) else None,
            api_key=api_key,
        )
    except CodexExecutionError as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        error_message = str(exc)
        logger.error("Codex request failed: %s", error_message)
        await _record_usage(
            ctx,
            usage={},
            status_code=503,
            latency_ms=latency_ms,
            error_message=error_message[:512],
        )
        return JSONResponse(status_code=503, content={"error": error_message})

    latency_ms = int((time.monotonic() - start) * 1000)
    usage = {
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "total_tokens": result.total_tokens,
        "model": request_model if isinstance(request_model, str) and request_model else result.model,
    }

    if is_stream:
        events = build_chat_completion_stream_events(
            result=result,
            request_model=request_model if isinstance(request_model, str) else None,
        )

        async def stream_generator():
            try:
                for event in events:
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            finally:
                response_meta = json.dumps(usage, ensure_ascii=False)
                await _record_usage(
                    ctx,
                    usage=usage,
                    status_code=200,
                    latency_ms=latency_ms,
                    response_body=response_meta,
                )

        return StreamingResponse(
            stream_generator(),
            status_code=200,
            headers={
                "cache-control": "no-transform",
                "x-accel-buffering": "no",
            },
            media_type="text/event-stream",
        )

    response_data = build_chat_completion_response(
        result=result,
        request_model=request_model if isinstance(request_model, str) else None,
    )
    response_meta = _strip_content_from_response(json.dumps(response_data, ensure_ascii=False).encode("utf-8"))
    await _record_usage(
        ctx,
        usage=usage,
        status_code=200,
        latency_ms=latency_ms,
        response_body=response_meta,
    )
    return JSONResponse(status_code=200, content=response_data)


@router.post("/internal/test-connection")
async def internal_test_connection(request: Request):
    """Test upstream provider connectivity using the same URL construction as real traffic."""
    body = await request.json()
    provider: str = body.get("provider", "")
    base_url: str | None = body.get("base_url")
    api_key: str = body.get("api_key", "")
    api_type: str = body.get("api_type") or "openai-completions"
    model: str = body.get("model", "")
    skip_ssl_verify: bool = body.get("skip_ssl_verify", False)

    if not provider or not api_key or not model:
        return JSONResponse(status_code=400, content={
            "ok": False, "message": "provider, api_key, model 为必填",
        })

    t0 = time.monotonic()
    try:
        if api_type == "google-generative-ai":
            path = f"v1beta/models/{model}:generateContent"
            target_url = _build_target_url(provider, path, base_url, api_key)
            req_body = {
                "contents": [{"parts": [{"text": "hi"}]}],
                "generationConfig": {"maxOutputTokens": 1},
            }
            req_headers: dict = {}
        elif api_type == "anthropic-messages":
            path = "v1/messages"
            target_url = _build_target_url(provider, path, base_url, api_key)
            req_body = {"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}
            req_headers = _build_auth_headers(provider, api_key, {}, api_type=api_type)
        else:
            path = "v1/chat/completions"
            target_url = _build_target_url(provider, path, base_url, api_key)
            req_body = {"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}
            req_headers = _build_auth_headers(provider, api_key, {}, api_type=api_type)

        client = _get_http_client(skip_ssl_verify)
        resp = await client.post(target_url, json=req_body, headers=req_headers, timeout=30)
        resp.raise_for_status()

        latency_ms = int((time.monotonic() - t0) * 1000)
        return JSONResponse(content={
            "ok": True, "message": "连接成功", "model": model, "latency_ms": latency_ms,
        })

    except httpx.HTTPStatusError as e:
        latency_ms = int((time.monotonic() - t0) * 1000)
        status = e.response.status_code
        resp_text = e.response.text[:300] if e.response.text else ""
        if status in (401, 403):
            msg = f"认证失败 (HTTP {status})，请检查 API Key 是否有效"
        elif status == 404:
            msg = "端点不存在 (HTTP 404)，请检查 Base URL 是否正确"
        else:
            msg = f"HTTP {status}"
        return JSONResponse(content={
            "ok": False, "message": msg, "model": model, "latency_ms": latency_ms,
            "error_detail": f"URL: {e.request.url} | HTTP {status} | {resp_text}",
        })
    except Exception as e:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return JSONResponse(content={
            "ok": False, "message": f"连接失败: {type(e).__name__}",
            "model": model, "latency_ms": latency_ms,
            "error_detail": str(e)[:300],
        })


@router.api_route(
    "/{provider}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
async def llm_proxy(provider: str, path: str, request: Request):
    proxy_token = _extract_proxy_token(request)
    if not proxy_token:
        return JSONResponse(status_code=401, content={"error": "Missing proxy token"})

    async with get_session() as db:
        result = await db.execute(
            select(Instance).where(
                Instance.wp_api_key == proxy_token,
                Instance.deleted_at.is_(None),
            )
        )
        instance = result.scalar_one_or_none()
        if instance is None:
            result = await db.execute(
                select(Instance).where(
                    Instance.proxy_token == proxy_token,
                    Instance.deleted_at.is_(None),
                )
            )
            instance = result.scalar_one_or_none()
        if instance is None:
            return JSONResponse(status_code=401, content={"error": "Invalid proxy token"})

        ipc_result = await db.execute(
            select(InstanceProviderConfig).where(
                InstanceProviderConfig.instance_id == instance.id,
                InstanceProviderConfig.provider == provider,
                not_deleted(InstanceProviderConfig),
            )
        )
        ipc = ipc_result.scalar_one_or_none()

        if ipc is None:
            fallback_result = await db.execute(
                select(UserLlmConfig).where(
                    UserLlmConfig.user_id == instance.created_by,
                    UserLlmConfig.org_id == instance.org_id,
                    UserLlmConfig.provider == provider,
                    not_deleted(UserLlmConfig),
                )
            )
            fallback_config = fallback_result.scalar_one_or_none()
            key_source = fallback_config.key_source if fallback_config else "org"
        else:
            key_source = ipc.key_source

        is_org_key = key_source == "org"
        real_key: str | None = None
        base_url: str | None = None
        api_type: str | None = None
        org_key_id: str | None = None
        skip_ssl_verify: bool = False

        if is_org_key:
            key_result = await db.execute(
                select(OrgLlmKey).where(
                    OrgLlmKey.org_id == instance.org_id,
                    OrgLlmKey.provider == provider,
                    OrgLlmKey.is_active.is_(True),
                    not_deleted(OrgLlmKey),
                ).order_by(OrgLlmKey.created_at).limit(1)
            )
            org_key = key_result.scalar_one_or_none()
            if org_key is None:
                return JSONResponse(status_code=404, content={
                    "error": f"当前组织未配置 {provider} 的 Working Plan Key，请联系管理员"
                })
            real_key = org_key.api_key
            base_url = org_key.base_url
            api_type = org_key.api_type
            org_key_id = org_key.id
            skip_ssl_verify = org_key.skip_ssl_verify

            ok, msg = await _check_quota(org_key.id, org_key.org_token_limit, org_key.system_token_limit, db)
            if not ok:
                return JSONResponse(status_code=429, content={"error": msg})
        else:
            key_result = await db.execute(
                select(UserLlmKey).where(
                    UserLlmKey.user_id == instance.created_by,
                    UserLlmKey.provider == provider,
                    not_deleted(UserLlmKey),
                )
            )
            user_key = key_result.scalar_one_or_none()
            if user_key is None:
                return JSONResponse(status_code=404, content={
                    "error": f"未找到 {provider} 的个人 Key"
                })
            real_key = user_key.api_key
            base_url = user_key.base_url
            api_type = user_key.api_type
            skip_ssl_verify = user_key.skip_ssl_verify

    raw_body = await request.body()
    body = _maybe_inject_stream_options(raw_body, provider)

    is_stream = False
    try:
        req_data = json.loads(body)
        is_stream = req_data.get("stream", False)
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    ctx = _RequestContext(
        instance=instance,
        provider=provider,
        key_source=key_source,
        org_key_id=org_key_id,
        request_path=f"/{path}",
        is_stream=is_stream,
        raw_body=raw_body,
    )

    if provider == CODEX_PROVIDER:
        if config.key_source != "personal":
            return JSONResponse(status_code=400, content={"error": "Codex 仅支持个人配置"})
        return await _handle_codex_proxy(request, path, ctx, api_key=real_key)

    target_url = _build_target_url(provider, path, base_url, real_key)
    req_headers = _build_auth_headers(provider, real_key, dict(request.headers), api_type=api_type)

    client = _get_http_client(skip_ssl_verify=skip_ssl_verify)

    if is_stream:
        return await _handle_stream(client, request.method, target_url, req_headers, body, ctx)
    else:
        return await _handle_non_stream(client, request.method, target_url, req_headers, body, ctx)


class _RequestContext:
    __slots__ = ("instance", "provider", "key_source", "org_key_id",
                 "request_path", "is_stream", "raw_body")

    def __init__(self, *, instance: Instance, provider: str, key_source: str,
                 org_key_id: str | None, request_path: str, is_stream: bool,
                 raw_body: bytes):
        self.instance = instance
        self.provider = provider
        self.key_source = key_source
        self.org_key_id = org_key_id
        self.request_path = request_path
        self.is_stream = is_stream
        self.raw_body = raw_body


async def _handle_non_stream(
    client: httpx.AsyncClient,
    method: str, url: str, headers: dict, body: bytes,
    ctx: _RequestContext,
) -> JSONResponse:
    start = time.monotonic()
    try:
        resp = await client.request(method, url, headers=headers, content=body)
    except httpx.RequestError as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        logger.error("LLM proxy request failed: %s", e)
        await _record_usage(ctx, usage={}, status_code=502, latency_ms=latency_ms,
                            error_message=str(e)[:512])
        return JSONResponse(status_code=502, content={"error": f"上游请求失败: {e}"})

    latency_ms = int((time.monotonic() - start) * 1000)
    resp_body = resp.content

    usage = _parse_usage_from_response(resp_body) if resp.status_code < 400 else {}
    response_meta = _strip_content_from_response(resp_body)
    error_msg = None
    if resp.status_code >= 400:
        try:
            err_data = json.loads(resp_body)
            error_msg = str(err_data.get("error", ""))[:512]
        except (json.JSONDecodeError, UnicodeDecodeError):
            error_msg = resp_body[:512].decode("utf-8", errors="replace") if resp_body else None

    await _record_usage(ctx, usage=usage, status_code=resp.status_code,
                        latency_ms=latency_ms, error_message=error_msg,
                        response_body=response_meta)

    resp_headers = {}
    for k, v in resp.headers.items():
        if k.lower() not in ("content-encoding", "content-length", "transfer-encoding"):
            resp_headers[k] = v

    if resp_body:
        try:
            parsed = json.loads(resp_body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return Response(
                status_code=resp.status_code,
                content=resp_body,
                headers=resp_headers,
                media_type=resp.headers.get("content-type", "application/json"),
            )
    else:
        parsed = None

    return JSONResponse(
        status_code=resp.status_code,
        content=parsed,
        headers=resp_headers,
    )


def _extract_sse_error(line: str) -> str | None:
    """Parse an SSE data line for error content (OpenAI-compatible format)."""
    stripped = line.strip()
    if not stripped.startswith("data: ") or stripped == "data: [DONE]":
        return None
    try:
        obj = json.loads(stripped[6:])
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(obj.get("error"), dict):
        err = obj["error"]
        return f"{err.get('type', 'error')}: {err.get('message', str(err))}"[:512]
    if isinstance(obj.get("error"), str):
        return obj["error"][:512]
    for choice in obj.get("choices") or []:
        reason = choice.get("finish_reason")
        if reason and reason not in ("stop", "length", "tool_calls", "function_call"):
            return f"finish_reason={reason}"
    return None


async def _handle_stream(
    client: httpx.AsyncClient,
    method: str, url: str, headers: dict, body: bytes,
    ctx: _RequestContext,
) -> StreamingResponse:
    start = time.monotonic()
    try:
        req = client.build_request(method, url, headers=headers, content=body)
        resp = await client.send(req, stream=True)
    except httpx.RequestError as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        logger.error("LLM proxy stream request failed: %s", e)
        await _record_usage(ctx, usage={}, status_code=502, latency_ms=latency_ms,
                            error_message=str(e)[:512])
        return JSONResponse(status_code=502, content={"error": f"上游请求失败: {e}"})

    usage_data: dict = {}

    async def stream_generator():
        nonlocal usage_data
        seen_done = False
        stream_error: str | None = None
        try:
            async for line in resp.aiter_lines():
                parsed = _parse_usage_from_sse_chunk(line)
                if parsed:
                    usage_data = parsed
                if not stream_error:
                    stream_error = _extract_sse_error(line)
                if line.strip() == "data: [DONE]":
                    seen_done = True
                yield line + "\n"
            if not seen_done:
                yield "data: [DONE]\n\n"
        except Exception as e:
            stream_error = stream_error or f"stream interrupted: {e}"
            raise
        finally:
            await resp.aclose()
            latency_ms = int((time.monotonic() - start) * 1000)
            if stream_error:
                logger.warning("SSE stream error from %s: %s", ctx.provider, stream_error[:512])
            response_meta = json.dumps(usage_data, ensure_ascii=False) if usage_data else None
            await _record_usage(ctx, usage=usage_data, status_code=resp.status_code,
                                latency_ms=latency_ms,
                                error_message=stream_error[:512] if stream_error else None,
                                response_body=response_meta)

    resp_headers = {}
    for k, v in resp.headers.items():
        if k.lower() not in ("content-encoding", "content-length", "transfer-encoding"):
            resp_headers[k] = v

    resp_headers["cache-control"] = "no-transform"
    resp_headers["x-accel-buffering"] = "no"

    return StreamingResponse(
        stream_generator(),
        status_code=resp.status_code,
        headers=resp_headers,
        media_type=resp.headers.get("content-type", "text/event-stream"),
    )


async def _record_usage(
    ctx: _RequestContext,
    *,
    usage: dict,
    status_code: int | None = None,
    latency_ms: int | None = None,
    error_message: str | None = None,
    response_body: str | None = None,
):
    try:
        request_body = None
        if settings.LLM_LOG_CONTENT:
            try:
                request_body = ctx.raw_body.decode("utf-8")
            except UnicodeDecodeError:
                pass

        async with get_session() as db:
            log = LlmUsageLog(
                org_llm_key_id=ctx.org_key_id,
                user_id=ctx.instance.created_by,
                instance_id=ctx.instance.id,
                provider=ctx.provider,
                model=usage.get("model"),
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                org_id=ctx.instance.org_id,
                key_source=ctx.key_source,
                request_path=ctx.request_path,
                is_stream=ctx.is_stream,
                status_code=status_code,
                latency_ms=latency_ms,
                error_message=error_message,
                request_body=request_body,
                response_body=response_body,
            )
            db.add(log)
            await db.commit()
    except Exception:
        logger.warning("Failed to record LLM usage", exc_info=True)
