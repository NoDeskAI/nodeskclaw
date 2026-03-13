"""WebSocket client for communicating with backend security evaluation service."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

from .types import AfterAction, AfterResult, BeforeAction, BeforeResult

logger = logging.getLogger("nanobot_security_layer.ws_client")

_ws: Any = None
_pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
_counter = 0
_recv_task: asyncio.Task[None] | None = None
_reconnect_task: asyncio.Task[None] | None = None

RECONNECT_DELAY = 3.0


def _endpoint() -> str:
    base = os.environ.get("SECURITY_WS_ENDPOINT") or os.environ.get("NODESKCLAW_BACKEND_URL") or "ws://localhost:8000"
    url = base.replace("http://", "ws://").replace("https://", "wss://")
    token = os.environ.get("NODESKCLAW_API_TOKEN", "")
    return f"{url}/api/v1/security/ws?token={token}"


def _next_id() -> str:
    global _counter
    _counter += 1
    return f"r-{_counter}"


async def connect() -> None:
    global _ws, _recv_task
    try:
        import websockets
    except ImportError:
        logger.error("websockets package not installed, security layer disabled")
        return

    endpoint = _endpoint()
    logger.info("Connecting to %s", endpoint.split("?")[0])

    try:
        _ws = await websockets.connect(endpoint, ping_interval=20, ping_timeout=60)
        logger.info("WebSocket connected")
        _recv_task = asyncio.create_task(_recv_loop())
    except Exception as e:
        logger.warning("WebSocket connection failed: %s, will retry", e)
        _schedule_reconnect()


async def _recv_loop() -> None:
    global _ws
    try:
        async for raw in _ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")
            msg_id = msg.get("id")

            if msg_type == "result" and msg_id and msg_id in _pending:
                fut = _pending.pop(msg_id)
                if not fut.done():
                    fut.set_result(msg.get("result", {}))
    except Exception as e:
        logger.warning("WebSocket recv loop ended: %s", e)
    finally:
        _ws = None
        _resolve_all_pending()
        _schedule_reconnect()


def _resolve_all_pending() -> None:
    for fut in _pending.values():
        if not fut.done():
            fut.set_result({"action": "allow"})
    _pending.clear()


def _schedule_reconnect() -> None:
    global _reconnect_task
    if _reconnect_task and not _reconnect_task.done():
        return

    async def _do_reconnect() -> None:
        await asyncio.sleep(RECONNECT_DELAY)
        await connect()

    try:
        _reconnect_task = asyncio.create_task(_do_reconnect())
    except RuntimeError:
        pass


def _build_ctx(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "params": params,
        "agent_instance_id": os.environ.get("AGENT_INSTANCE_ID", ""),
        "workspace_id": os.environ.get("WORKSPACE_ID", ""),
        "timestamp": time.time(),
    }


async def evaluate_before(tool_name: str, params: dict[str, Any]) -> BeforeResult:
    if _ws is None:
        return BeforeResult()

    req_id = _next_id()
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[dict[str, Any]] = loop.create_future()
    _pending[req_id] = fut

    try:
        await _ws.send(json.dumps({
            "type": "evaluate_before",
            "id": req_id,
            "ctx": _build_ctx(tool_name, params),
        }))
    except Exception:
        _pending.pop(req_id, None)
        return BeforeResult()

    result = await fut
    return BeforeResult(
        action=BeforeAction(result.get("action", "allow")),
        reason=result.get("reason"),
        message=result.get("message"),
        modified_params=result.get("modified_params"),
    )


async def evaluate_after(
    tool_name: str,
    params: dict[str, Any],
    exec_result: str | None = None,
    exec_error: str | None = None,
    duration_ms: float | None = None,
) -> AfterResult:
    if _ws is None:
        return AfterResult()

    req_id = _next_id()
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[dict[str, Any]] = loop.create_future()
    _pending[req_id] = fut

    try:
        await _ws.send(json.dumps({
            "type": "evaluate_after",
            "id": req_id,
            "ctx": _build_ctx(tool_name, params),
            "exec_result": {
                "result": exec_result,
                "error": exec_error,
                "duration_ms": duration_ms,
            },
        }))
    except Exception:
        _pending.pop(req_id, None)
        return AfterResult()

    result = await fut
    return AfterResult(
        action=AfterAction(result.get("action", "pass")),
        reason=result.get("reason"),
        message=result.get("message"),
        modified_result=result.get("modified_result"),
    )


async def disconnect() -> None:
    global _ws, _recv_task, _reconnect_task
    if _reconnect_task and not _reconnect_task.done():
        _reconnect_task.cancel()
        _reconnect_task = None
    if _recv_task and not _recv_task.done():
        _recv_task.cancel()
        _recv_task = None
    if _ws:
        await _ws.close()
        _ws = None
    _resolve_all_pending()
