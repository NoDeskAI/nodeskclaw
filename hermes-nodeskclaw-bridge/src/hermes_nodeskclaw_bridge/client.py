"""Core tunnel WebSocket client for Hermes bridge."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import httpx
import websockets
from websockets.asyncio.client import ClientConnection

logger = logging.getLogger("hermes_nodeskclaw_bridge")

RECONNECT_BASE_S = 1.0
RECONNECT_MAX_S = 30.0
PONG_TIMEOUT_S = 45.0
PING_CHECK_INTERVAL_S = 15.0

ChatRequestHandler = Callable[
    [str, str, list[dict[str, Any]], str, bool],
    Awaitable[None],
]


@dataclass
class TunnelCallbacks:
    on_auth_ok: Callable[[], None] | None = None
    on_auth_error: Callable[[str], None] | None = None
    on_close: Callable[[], None] | None = None
    on_reconnecting: Callable[[int], None] | None = None


def _derive_tunnel_url(api_url: str) -> str:
    url = api_url.rstrip("/")
    url = url.replace("https://", "wss://").replace("http://", "ws://")
    return f"{url}/tunnel/connect"


class TunnelClient:
    """Connect to the NoDeskClaw tunnel and forward chat requests."""

    def __init__(
        self,
        *,
        url: str = "",
        instance_id: str = "",
        token: str = "",
        on_chat_request: ChatRequestHandler | None = None,
        callbacks: TunnelCallbacks | None = None,
    ) -> None:
        api_url = os.environ.get("NODESKCLAW_API_URL", "") or os.environ.get("DESKCLAW_API_URL", "")
        tunnel_url = os.environ.get("NODESKCLAW_TUNNEL_URL", "")

        self._url = url or tunnel_url or (_derive_tunnel_url(api_url) if api_url else "")
        self._api_url = api_url.rstrip("/") if api_url else ""
        self._instance_id = (
            instance_id
            or os.environ.get("NODESKCLAW_INSTANCE_ID", "")
            or os.environ.get("DESKCLAW_INSTANCE_ID", "")
        )
        self._token = token or os.environ.get("NODESKCLAW_TOKEN", "") or os.environ.get("DESKCLAW_TOKEN", "")
        self.on_chat_request = on_chat_request
        self._callbacks = callbacks or TunnelCallbacks()

        self._ws: ClientConnection | None = None
        self._closed = False
        self._reconnect_attempt = 0
        self._last_pong = time.monotonic()
        self._ping_task: asyncio.Task | None = None

    @property
    def instance_id(self) -> str:
        return self._instance_id

    @property
    def connected(self) -> bool:
        return self._ws is not None and self._ws.protocol.state.name == "OPEN"

    async def run_forever(self) -> None:
        if not self._url or not self._instance_id or not self._token:
            logger.warning(
                "Tunnel bridge: missing config (url=%s, id=%s, token=%s)",
                "set" if self._url else "MISSING",
                "set" if self._instance_id else "MISSING",
                "set" if self._token else "MISSING",
            )
            return

        logger.info("Tunnel bridge: connecting to %s (instance=%s)", self._url, self._instance_id)

        while not self._closed:
            try:
                await self._connect_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Tunnel bridge: connection error: %s", exc)

            if self._closed:
                break
            delay = min(RECONNECT_BASE_S * (2 ** self._reconnect_attempt), RECONNECT_MAX_S)
            self._reconnect_attempt += 1
            logger.info("Tunnel bridge: reconnecting in %.1fs (attempt #%d)", delay, self._reconnect_attempt)
            if self._callbacks.on_reconnecting:
                self._callbacks.on_reconnecting(self._reconnect_attempt)
            await asyncio.sleep(delay)

    async def _connect_once(self) -> None:
        async with websockets.connect(self._url, max_size=2**22) as ws:
            self._ws = ws
            logger.info("Tunnel bridge: WebSocket connected, sending auth...")

            auth_msg = {
                "id": str(uuid.uuid4()),
                "type": "auth",
                "payload": {"instance_id": self._instance_id, "token": self._token},
                "ts": _now_ms(),
            }
            await ws.send(json.dumps(auth_msg))

            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Tunnel bridge: bad JSON from server")
                    continue

                await self._handle_message(msg)

        self._ws = None
        self._stop_ping()
        if self._callbacks.on_close:
            self._callbacks.on_close()

    async def _handle_message(self, msg: dict[str, Any]) -> None:
        msg_type = msg.get("type", "")

        if msg_type == "auth.ok":
            logger.info("Tunnel bridge: authenticated")
            self._reconnect_attempt = 0
            self._last_pong = time.monotonic()
            self._start_ping()
            if self._callbacks.on_auth_ok:
                self._callbacks.on_auth_ok()

        elif msg_type == "auth.error":
            reason = msg.get("payload", {}).get("reason", "unknown")
            logger.error("Tunnel bridge: auth failed: %s", reason)
            self._closed = True
            if self._callbacks.on_auth_error:
                self._callbacks.on_auth_error(reason)
            if self._ws:
                await self._ws.close()

        elif msg_type == "ping":
            await self._send({"type": "pong", "payload": {}})
            self._last_pong = time.monotonic()

        elif msg_type == "chat.request":
            asyncio.create_task(self._dispatch_chat_request(msg))

        elif msg_type == "chat.cancel":
            logger.debug("Tunnel bridge: chat cancel for %s", msg.get("payload", {}).get("id"))

        else:
            logger.debug("Tunnel bridge: unhandled message type=%s", msg_type)

    async def _dispatch_chat_request(self, msg: dict[str, Any]) -> None:
        if not self.on_chat_request:
            logger.warning("Tunnel bridge: no chat_request handler, ignoring")
            await self.send_response_done(msg.get("id", ""), msg.get("traceId", ""))
            return

        payload = msg.get("payload", {})
        request_id = msg.get("id", "")
        trace_id = msg.get("traceId", "")
        messages = payload.get("messages", [])
        workspace_id = payload.get("workspace_id", "")
        no_reply = payload.get("no_reply", False)

        try:
            await self.on_chat_request(request_id, trace_id, messages, workspace_id, no_reply)
        except Exception as exc:
            logger.error("Tunnel bridge: chat_request handler error: %s", exc)
            await self.send_response_error(request_id, trace_id, str(exc))

    async def send_response_chunk(self, reply_to: str, trace_id: str, content: str) -> None:
        await self._send({
            "type": "chat.response.chunk",
            "replyTo": reply_to,
            "traceId": trace_id,
            "payload": {"content": content},
        })

    async def send_response_done(self, reply_to: str, trace_id: str) -> None:
        await self._send({
            "type": "chat.response.done",
            "replyTo": reply_to,
            "traceId": trace_id,
            "payload": {},
        })

    async def send_response_error(self, reply_to: str, trace_id: str, error: str) -> None:
        await self._send({
            "type": "chat.response.error",
            "replyTo": reply_to,
            "traceId": trace_id,
            "payload": {"error": error},
        })

    async def list_peers(self, workspace_id: str) -> list[dict]:
        if not self._api_url or not workspace_id or not self._instance_id:
            return []
        url = f"{self._api_url}/workspaces/{workspace_id}/topology/reachable?instance_id={self._instance_id}"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {self._token}"},
                )
            if resp.status_code != 200:
                return []
            data = resp.json()
            return data.get("data", {}).get("reachable", [])
        except Exception:
            return []

    async def _send(self, msg: dict[str, Any]) -> None:
        if not self._ws:
            return
        msg.setdefault("id", str(uuid.uuid4()))
        msg.setdefault("ts", _now_ms())
        try:
            await self._ws.send(json.dumps(msg))
        except Exception as exc:
            logger.warning("Tunnel bridge: send failed: %s", exc)

    def _start_ping(self) -> None:
        self._stop_ping()
        self._ping_task = asyncio.create_task(self._ping_loop())

    def _stop_ping(self) -> None:
        if self._ping_task:
            self._ping_task.cancel()
            self._ping_task = None

    async def _ping_loop(self) -> None:
        try:
            while self._ws and not self._closed:
                await asyncio.sleep(PING_CHECK_INTERVAL_S)
                if time.monotonic() - self._last_pong > PONG_TIMEOUT_S:
                    logger.warning("Tunnel bridge: pong timeout, reconnecting")
                    await self._ws.close()
                    break
        except asyncio.CancelledError:
            return

    async def close(self) -> None:
        self._closed = True
        self._stop_ping()
        if self._ws:
            await self._ws.close()


def _now_ms() -> int:
    return int(time.time() * 1000)
