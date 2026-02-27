"""LLM Proxy: resolves real API keys and forwards requests to upstream LLM providers."""

import json
import logging
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, select

from app.database import get_session
from app.models import Instance, LlmUsageLog, OrgLlmKey, UserLlmConfig, UserLlmKey, not_deleted

logger = logging.getLogger(__name__)

router = APIRouter()

PROVIDER_DEFAULTS: dict[str, dict] = {
    "openai": {"base_url": "https://api.openai.com", "auth_type": "bearer"},
    "anthropic": {"base_url": "https://api.anthropic.com", "auth_type": "x-api-key"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com", "auth_type": "query_param"},
    "openrouter": {"base_url": "https://openrouter.ai/api", "auth_type": "bearer"},
    "minimax-openai": {"base_url": "https://api.minimaxi.com", "auth_type": "bearer"},
    "minimax-anthropic": {"base_url": "https://api.minimaxi.com/anthropic", "auth_type": "bearer"},
}

_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=httpx.Timeout(300, connect=10))
    return _http_client


def _extract_proxy_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def _build_target_url(provider: str, path: str, base_url: str | None, api_key: str | None) -> str:
    base = (base_url or PROVIDER_DEFAULTS.get(provider, {}).get("base_url", "")).rstrip("/")
    url = f"{base}/{path}"

    prov_conf = PROVIDER_DEFAULTS.get(provider, {})
    if prov_conf.get("auth_type") == "query_param" and api_key:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        qs["key"] = [api_key]
        url = urlunparse(parsed._replace(query=urlencode(qs, doseq=True)))

    return url


def _build_auth_headers(provider: str, api_key: str, original_headers: dict) -> dict:
    headers = {}
    for k, v in original_headers.items():
        lower = k.lower()
        if lower in ("host", "content-length", "transfer-encoding", "authorization", "x-api-key", "accept-encoding"):
            continue
        headers[k] = v

    prov_conf = PROVIDER_DEFAULTS.get(provider, {})
    auth_type = prov_conf.get("auth_type", "bearer")

    if auth_type == "bearer":
        headers["authorization"] = f"Bearer {api_key}"
    elif auth_type == "x-api-key":
        headers["x-api-key"] = api_key

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


def _maybe_inject_stream_options(body: bytes, is_org_key: bool) -> bytes:
    if not is_org_key:
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

        cfg_result = await db.execute(
            select(UserLlmConfig).where(
                UserLlmConfig.user_id == instance.created_by,
                UserLlmConfig.org_id == instance.org_id,
                UserLlmConfig.provider == provider,
                not_deleted(UserLlmConfig),
            )
        )
        config = cfg_result.scalar_one_or_none()
        if config is None:
            return JSONResponse(status_code=404, content={
                "error": f"未配置 {provider} 的 LLM Key，请在实例设置中配置"
            })

        is_org_key = config.key_source == "org"
        real_key: str | None = None
        base_url: str | None = None
        org_key_id: str | None = None

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
            org_key_id = org_key.id

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

    target_url = _build_target_url(provider, path, base_url, real_key)
    req_headers = _build_auth_headers(provider, real_key, dict(request.headers))

    body = await request.body()
    body = _maybe_inject_stream_options(body, is_org_key)

    is_stream = False
    try:
        req_data = json.loads(body)
        is_stream = req_data.get("stream", False)
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    client = _get_http_client()

    if is_stream:
        return await _handle_stream(
            client, request.method, target_url, req_headers, body,
            is_org_key, org_key_id, instance, provider,
        )
    else:
        return await _handle_non_stream(
            client, request.method, target_url, req_headers, body,
            is_org_key, org_key_id, instance, provider,
        )


async def _handle_non_stream(
    client: httpx.AsyncClient,
    method: str, url: str, headers: dict, body: bytes,
    is_org_key: bool, org_key_id: str | None,
    instance: Instance, provider: str,
) -> JSONResponse:
    try:
        resp = await client.request(method, url, headers=headers, content=body)
    except httpx.RequestError as e:
        logger.error("LLM proxy request failed: %s", e)
        return JSONResponse(status_code=502, content={"error": f"上游请求失败: {e}"})

    resp_body = resp.content

    if is_org_key and org_key_id and resp.status_code < 400:
        usage = _parse_usage_from_response(resp_body)
        if usage:
            await _record_usage(org_key_id, instance, provider, usage)

    resp_headers = {}
    for k, v in resp.headers.items():
        if k.lower() not in ("content-encoding", "content-length", "transfer-encoding"):
            resp_headers[k] = v

    if resp_body:
        try:
            parsed = json.loads(resp_body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            from fastapi.responses import Response
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


async def _handle_stream(
    client: httpx.AsyncClient,
    method: str, url: str, headers: dict, body: bytes,
    is_org_key: bool, org_key_id: str | None,
    instance: Instance, provider: str,
) -> StreamingResponse:
    try:
        req = client.build_request(method, url, headers=headers, content=body)
        resp = await client.send(req, stream=True)
    except httpx.RequestError as e:
        logger.error("LLM proxy stream request failed: %s", e)
        return JSONResponse(status_code=502, content={"error": f"上游请求失败: {e}"})

    usage_data: dict = {}

    async def stream_generator():
        nonlocal usage_data
        seen_done = False
        try:
            async for line in resp.aiter_lines():
                if is_org_key and org_key_id:
                    parsed = _parse_usage_from_sse_chunk(line)
                    if parsed:
                        usage_data = parsed
                if line.strip() == "data: [DONE]":
                    seen_done = True
                yield line + "\n"
            if not seen_done:
                yield "data: [DONE]\n\n"
        finally:
            await resp.aclose()
            if is_org_key and org_key_id and usage_data:
                await _record_usage(org_key_id, instance, provider, usage_data)

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


async def _record_usage(org_key_id: str, instance: Instance, provider: str, usage: dict):
    try:
        async with get_session() as db:
            log = LlmUsageLog(
                org_llm_key_id=org_key_id,
                user_id=instance.created_by,
                instance_id=instance.id,
                provider=provider,
                model=usage.get("model"),
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            )
            db.add(log)
            await db.commit()
    except Exception:
        logger.warning("Failed to record LLM usage", exc_info=True)
