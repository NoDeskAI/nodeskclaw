"""Hermes-side adapter that maps NoDeskClaw tunnel messages to Hermes API calls."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

from .client import TunnelClient

logger = logging.getLogger("hermes_nodeskclaw_bridge.hermes")


class HermesChannel:
    """Translate tunnel chat requests into Hermes API server requests."""

    def __init__(
        self,
        client: TunnelClient,
        *,
        hermes_base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._client = client
        self._hermes_base_url = (
            hermes_base_url
            or os.environ.get("HERMES_BASE_URL")
            or "http://127.0.0.1:8642"
        ).rstrip("/")
        self._api_key = api_key or os.environ.get("HERMES_API_KEY") or os.environ.get("API_SERVER_KEY")
        self._model = model or os.environ.get("HERMES_MODEL_NAME") or os.environ.get("API_SERVER_MODEL_NAME") or "hermes-agent"

    async def handle_chat_request(
        self,
        request_id: str,
        trace_id: str,
        messages: list[dict[str, Any]],
        workspace_id: str,
        no_reply: bool,
    ) -> None:
        session_id = _session_id_for(workspace_id, request_id)
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if session_id:
            headers["X-Hermes-Session-Id"] = session_id

        payload = {
            "model": self._model,
            "messages": [_normalize_message(msg) for msg in messages],
        }

        if no_reply:
            await self._inject_context(headers, payload)
            await self._client.send_response_done(request_id, trace_id)
            return

        await self._stream_response(headers, payload, request_id, trace_id)

    async def _inject_context(self, headers: dict[str, str], payload: dict[str, Any]) -> None:
        body = dict(payload)
        body["stream"] = False
        body["max_tokens"] = 1
        url = f"{self._hermes_base_url}/v1/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=60) as http:
                await http.post(url, headers=headers, json=body)
        except Exception as exc:
            logger.debug("Hermes no_reply context injection failed: %s", exc)

    async def _stream_response(
        self,
        headers: dict[str, str],
        payload: dict[str, Any],
        request_id: str,
        trace_id: str,
    ) -> None:
        body = dict(payload)
        body["stream"] = True
        url = f"{self._hermes_base_url}/v1/chat/completions"

        async with httpx.AsyncClient(timeout=httpx.Timeout(1800.0, connect=10.0)) as http:
            async with http.stream("POST", url, headers=headers, json=body) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    error_msg = _extract_error_message(response.status_code, error_text)
                    await self._client.send_response_error(request_id, trace_id, error_msg)
                    return

                async for raw_line in response.aiter_lines():
                    line = raw_line.strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    content = _extract_chunk_text(chunk)
                    if content:
                        await self._client.send_response_chunk(request_id, trace_id, content)

        await self._client.send_response_done(request_id, trace_id)


def _session_id_for(workspace_id: str, request_id: str) -> str:
    if workspace_id:
        return f"workspace:{workspace_id}"
    return f"nodeskclaw:{request_id}"


def _normalize_message(message: dict[str, Any]) -> dict[str, str]:
    role = str(message.get("role") or "user")
    content = _normalize_content(message.get("content", ""))
    return {"role": role, "content": content}


def _normalize_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
        return "\n".join(parts)
    if content is None:
        return ""
    return str(content)


def _extract_chunk_text(chunk: dict[str, Any]) -> str:
    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    delta = choices[0].get("delta", {})
    if not isinstance(delta, dict):
        return ""
    content = delta.get("content", "")
    return content if isinstance(content, str) else ""


def _extract_error_message(status_code: int, raw_body: bytes) -> str:
    default = f"Hermes API returned {status_code}"
    if not raw_body:
        return default
    text = raw_body.decode("utf-8", errors="replace")
    try:
        body = json.loads(text)
    except json.JSONDecodeError:
        return f"{default}: {text[:300]}"
    error = body.get("error")
    if isinstance(error, dict):
        detail = error.get("message")
        if detail:
            return f"Hermes API {status_code}: {detail}"
    if isinstance(error, str) and error:
        return f"Hermes API {status_code}: {error}"
    return f"{default}: {text[:300]}"
