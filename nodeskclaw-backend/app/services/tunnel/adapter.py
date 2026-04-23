"""TunnelAdapter — unified WebSocket tunnel for backend <-> instance communication.

Replaces SSEListenerManager + AgentTransportAdapter + runtime HTTP adapters
with a single bidirectional WebSocket channel per instance.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from app.services.runtime.messaging.envelope import MessageEnvelope
from app.services.runtime.transport.base import DeliveryResult
from app.services.tunnel.protocol import TunnelMessage, TunnelMessageType
from app.services.workspace_message_service import (
    ABSOLUTE_MAX_COLLABORATION_DEPTH,
    get_collaboration_depth_limit,
)

logger = logging.getLogger(__name__)

NO_REPLY_BUFFER_SIZE = 30
AUTH_TIMEOUT_S = 10
PING_INTERVAL_S = 30
PING_TIMEOUT_S = 45
MENTION_ALL_SENTINEL = "__all__"
_WS_CONTEXT_TTL = 5.0


@dataclass
class _WorkspaceContext:
    workspace_name: str
    members: list[dict[str, str]]
    recent_messages: list
    fetched_at: float


def _parse_delegation(response: str) -> tuple[str, str] | None:
    stripped = response.strip()
    for prefix in ("delegate:", "escalate:"):
        if stripped.lower().startswith(prefix):
            target = stripped[len(prefix):].strip().split()[0] if stripped[len(prefix):].strip() else ""
            if target:
                return (prefix.rstrip(":"), target)
    return None


def _format_attachment_refs(attachments: list[dict]) -> str:
    if not attachments:
        return ""
    lines = []
    for idx, att in enumerate(attachments, 1):
        name = att.get("name", "unnamed")
        size = att.get("size", 0)
        ct = att.get("content_type", "")
        fid = att.get("id", "")
        if size >= 1024 * 1024:
            size_str = f"{size / (1024 * 1024):.1f}MB"
        elif size >= 1024:
            size_str = f"{size / 1024:.0f}KB"
        else:
            size_str = f"{size}B"
        parts = [name, size_str]
        if ct:
            parts.append(ct)
        lines.append(f"[附件{idx}: {', '.join(parts)}, file_id: {fid}]")
    lines.append("(可使用 nodeskclaw_file_download 工具下载附件到工作台)")
    return "\n".join(lines)


def _format_user_content(sender_name: str, text: str, attachments: list[dict]) -> str:
    content = f"[{sender_name}]: {text}"
    ref = _format_attachment_refs(attachments)
    if ref:
        content += "\n" + ref
    return content


def _extract_mentions(
    text: str,
    members: list[dict],
    self_name: str,
    *,
    exclude_names: list[str] | None = None,
) -> list[dict]:
    """Parse @name from agent response, matching all workspace members (agent + human).

    Uses negative lookahead to avoid prefix false positives (e.g. @test matching @test-2).
    ``exclude_names`` suppresses mentions of the upstream sender so that
    gratuitous acknowledgements like "@咕咕嘎嘎 收到！" don't trigger a
    collaboration round-trip back to the original requester.
    """
    skip = {self_name}
    if exclude_names:
        skip.update(exclude_names)
    results = []
    for m in members:
        name = m.get("name", "")
        if not name or name in skip:
            continue
        if re.search(rf"@{re.escape(name)}(?![\w-])", text):
            results.append(m)
    return results


class _InstanceConnection:
    """Tracks a single WebSocket tunnel connection to an instance."""

    __slots__ = (
        "ws", "instance_id", "connected_at", "last_pong",
        "msg_count_in", "msg_count_out",
        "_pending_responses", "_instance_streams",
    )

    def __init__(
        self, ws: WebSocket, instance_id: str,
        instance_streams: dict[str, asyncio.Queue[TunnelMessage]],
    ) -> None:
        self.ws = ws
        self.instance_id = instance_id
        self.connected_at = time.monotonic()
        self.last_pong = time.monotonic()
        self.msg_count_in = 0
        self.msg_count_out = 0
        self._pending_responses: dict[str, asyncio.Future[TunnelMessage]] = {}
        self._instance_streams = instance_streams

    def create_response_future(self, request_id: str) -> asyncio.Future[TunnelMessage]:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[TunnelMessage] = loop.create_future()
        self._pending_responses[request_id] = fut
        return fut

    def register_stream(self, request_id: str) -> asyncio.Queue[TunnelMessage]:
        q: asyncio.Queue[TunnelMessage] = asyncio.Queue()
        self._instance_streams[request_id] = q
        return q

    def unregister_stream(self, request_id: str) -> None:
        self._instance_streams.pop(request_id, None)

    def resolve_response(self, reply_to: str, msg: TunnelMessage) -> bool:
        queue = self._instance_streams.get(reply_to)
        if queue is not None:
            queue.put_nowait(msg)
            if msg.type in (
                TunnelMessageType.CHAT_RESPONSE_DONE,
                TunnelMessageType.CHAT_RESPONSE_ERROR,
            ):
                self._instance_streams.pop(reply_to, None)
            return True
        fut = self._pending_responses.pop(reply_to, None)
        if fut and not fut.done():
            fut.set_result(msg)
            return True
        return False

    def cancel_all(self) -> None:
        for fut in self._pending_responses.values():
            if not fut.done():
                fut.cancel()
        self._pending_responses.clear()
        self._instance_streams.clear()


class TunnelAdapter:
    """Unified tunnel adapter — manages WS connections and implements TransportAdapter."""

    transport_id = "agent"

    def __init__(self) -> None:
        self._connections: dict[str, _InstanceConnection] = {}
        self._ping_tasks: dict[str, asyncio.Task] = {}
        self._stats = {"total_connections": 0, "total_messages_in": 0, "total_messages_out": 0}
        self._ws_context_cache: dict[str, _WorkspaceContext] = {}
        self._instance_streams: dict[str, dict[str, asyncio.Queue[TunnelMessage]]] = {}

    @property
    def connected_instances(self) -> set[str]:
        return set(self._connections.keys())

    def get_connection(self, instance_id: str) -> WebSocket | None:
        conn = self._connections.get(instance_id)
        return conn.ws if conn else None

    # ── WebSocket lifecycle ──────────────────────────────────

    async def handle_websocket(self, ws: WebSocket) -> None:
        await ws.accept()

        try:
            raw = await asyncio.wait_for(ws.receive_json(), timeout=AUTH_TIMEOUT_S)
        except (asyncio.TimeoutError, WebSocketDisconnect, Exception) as e:
            logger.warning("Tunnel auth timeout or error: %s", e)
            try:
                await ws.close(code=4001, reason="auth_timeout")
            except Exception:
                logger.warning("Tunnel: failed to close ws after auth timeout", exc_info=True)
            return

        auth_msg = TunnelMessage.from_dict(raw)
        if auth_msg.type != TunnelMessageType.AUTH:
            await self._send(ws, TunnelMessage(
                type=TunnelMessageType.AUTH_ERROR,
                payload={"reason": "expected_auth_message"},
            ))
            await ws.close(code=4002, reason="expected_auth")
            return

        instance_id = auth_msg.payload.get("instance_id", "")
        token = auth_msg.payload.get("token", "")

        if not instance_id or not token:
            await self._send(ws, TunnelMessage(
                type=TunnelMessageType.AUTH_ERROR,
                payload={"reason": "missing_credentials"},
            ))
            await ws.close(code=4003, reason="missing_credentials")
            return

        if not await self._verify_token(instance_id, token):
            await self._send(ws, TunnelMessage(
                type=TunnelMessageType.AUTH_ERROR,
                payload={"reason": "invalid_token"},
            ))
            await ws.close(code=4004, reason="invalid_token")
            return

        old_conn = self._connections.get(instance_id)
        surviving_streams: dict[str, asyncio.Queue[TunnelMessage]] = {}
        if old_conn:
            logger.info("Tunnel: kicking previous connection for %s", instance_id)
            surviving_streams = dict(old_conn._instance_streams)
            old_conn.cancel_all()
            try:
                await old_conn.ws.close(code=4010, reason="replaced")
            except Exception:
                logger.warning("Tunnel: failed to close old ws for %s", instance_id, exc_info=True)
            self._cleanup_instance(instance_id)

        streams = self._instance_streams.setdefault(instance_id, {})
        streams.update(surviving_streams)
        conn = _InstanceConnection(ws, instance_id, streams)
        if streams:
            logger.info(
                "Tunnel: %d in-flight stream(s) survive reconnect for %s",
                len(streams), instance_id,
            )
        self._connections[instance_id] = conn
        self._stats["total_connections"] += 1

        await self._send(ws, TunnelMessage(type=TunnelMessageType.AUTH_OK))
        logger.info("Tunnel: instance %s connected", instance_id)

        self._broadcast_connection_event(instance_id, connected=True)

        ping_task = asyncio.create_task(self._ping_loop(instance_id))
        self._ping_tasks[instance_id] = ping_task

        replay_task = asyncio.create_task(self._safe_replay(instance_id))

        try:
            await self._message_loop(conn)
        except WebSocketDisconnect:
            logger.info("Tunnel: instance %s disconnected", instance_id)
        except Exception as e:
            logger.error("Tunnel: message loop error for %s: %s", instance_id, e)
        finally:
            replay_task.cancel()
            if self._connections.get(instance_id) is conn:
                self._cleanup_instance(instance_id)
                self._broadcast_connection_event(instance_id, connected=False)
            else:
                logger.info("Tunnel: instance %s handler exited (superseded by newer connection)", instance_id)

    async def _message_loop(self, conn: _InstanceConnection) -> None:
        while True:
            raw = await conn.ws.receive_json()
            msg = TunnelMessage.from_dict(raw)
            conn.msg_count_in += 1
            self._stats["total_messages_in"] += 1

            logger.debug(
                "[%s] tunnel recv type=%s instance=%s",
                msg.trace_id or "-", msg.type, conn.instance_id,
            )

            if msg.type == TunnelMessageType.PONG:
                conn.last_pong = time.monotonic()
            elif msg.type == TunnelMessageType.COLLABORATION_MESSAGE:
                asyncio.create_task(self._on_collaboration_message(conn.instance_id, msg))
            elif msg.type in (
                TunnelMessageType.CHAT_RESPONSE_CHUNK,
                TunnelMessageType.CHAT_RESPONSE_DONE,
                TunnelMessageType.CHAT_RESPONSE_ERROR,
            ):
                self._on_chat_response(conn, msg)
            elif msg.type == TunnelMessageType.STATUS_REPORT:
                logger.info("Tunnel: status report from %s: %s", conn.instance_id, msg.payload)
            else:
                logger.warning("Tunnel: unknown message type %s from %s", msg.type, conn.instance_id)

    def _on_chat_response(self, conn: _InstanceConnection, msg: TunnelMessage) -> None:
        if msg.reply_to:
            resolved = conn.resolve_response(msg.reply_to, msg)
            if not resolved:
                logger.warning(
                    "Tunnel: chat response for request %s has no handler on conn %s (type=%s)",
                    msg.reply_to, conn.instance_id, msg.type,
                )

    async def _on_collaboration_message(self, instance_id: str, msg: TunnelMessage) -> None:
        try:
            from app.services.collaboration_service import handle_collaboration_event
            await handle_collaboration_event(instance_id, msg.payload)
        except Exception as e:
            logger.error("Tunnel: collaboration message handling failed for %s: %s", instance_id, e)

    # ── Send to instance ─────────────────────────────────────

    async def send_chat_request(
        self,
        instance_id: str,
        messages: list[dict],
        *,
        workspace_id: str = "",
        trace_id: str = "",
        stream: bool = True,
        no_reply: bool = False,
    ) -> AsyncChatStream:
        conn = self._connections.get(instance_id)
        if not conn:
            raise ConnectionError(f"Instance {instance_id} not connected via tunnel")

        request_id = str(uuid.uuid4())
        payload: dict[str, Any] = {
            "messages": messages,
            "stream": stream,
            "workspace_id": workspace_id,
        }
        if no_reply:
            payload["no_reply"] = True

        msg = TunnelMessage(
            id=request_id,
            type=TunnelMessageType.CHAT_REQUEST,
            trace_id=trace_id,
            payload=payload,
        )
        await self._send(conn.ws, msg)
        logger.info(
            "Tunnel: chat request sent to %s, request_id=%s, trace=%s",
            instance_id, request_id, trace_id,
        )
        return AsyncChatStream(conn, request_id, trace_id)

    async def send_learning_task(self, instance_id: str, task: dict) -> None:
        conn = self._connections.get(instance_id)
        if not conn:
            raise ConnectionError(f"Instance {instance_id} not connected via tunnel")

        msg = TunnelMessage(
            type=TunnelMessageType.LEARNING_TASK,
            trace_id=str(uuid.uuid4()),
            payload=task,
        )
        await self._send(conn.ws, msg)
        logger.info("Tunnel: learning task sent to %s (mode=%s)", instance_id, task.get("mode", "?"))

    async def send_ping(self, instance_id: str) -> bool:
        conn = self._connections.get(instance_id)
        if not conn:
            return False
        try:
            await self._send(conn.ws, TunnelMessage(type=TunnelMessageType.PING))
            return True
        except Exception:
            return False

    # ── TransportAdapter protocol ────────────────────────────

    async def deliver(
        self,
        envelope: MessageEnvelope,
        target_node_id: str,
        *,
        workspace_id: str = "",
        db: Any = None,
    ) -> DeliveryResult:
        start = time.monotonic()
        logger.debug("TunnelAdapter.deliver: envelope=%s target=%s", envelope.id, target_node_id)

        if target_node_id not in self._connections:
            return DeliveryResult(
                success=False, target_node_id=target_node_id,
                transport=self.transport_id, error="instance_not_connected_locally",
                latency_ms=int((time.monotonic() - start) * 1000),
            )

        if db is None:
            from app.core.deps import async_session_factory
            async with async_session_factory() as db:
                return await self._do_deliver(envelope, target_node_id, workspace_id, db, start)
        return await self._do_deliver(envelope, target_node_id, workspace_id, db, start)

    async def _fetch_workspace_context(
        self, workspace_id: str, db: Any,
    ) -> _WorkspaceContext:
        now = time.monotonic()
        cached = self._ws_context_cache.get(workspace_id)
        if cached and (now - cached.fetched_at) < _WS_CONTEXT_TTL:
            return cached

        from sqlalchemy import select

        from app.models.base import not_deleted
        from app.models.node_card import NodeCard
        from app.models.workspace import Workspace
        from app.services import workspace_message_service as msg_service

        ws_result = await db.execute(
            select(Workspace.name).where(
                Workspace.id == workspace_id, not_deleted(Workspace)
            )
        )
        workspace_name = ws_result.scalar_one_or_none() or ""

        cards_result = await db.execute(
            select(NodeCard.node_type, NodeCard.name).where(
                NodeCard.workspace_id == workspace_id,
                NodeCard.node_type.in_(["agent", "human"]),
                not_deleted(NodeCard),
            )
        )
        members = [{"type": r[0], "name": r[1]} for r in cards_result.all()]

        recent_messages = await msg_service.get_recent_messages(
            db, workspace_id, limit=30
        )

        ctx = _WorkspaceContext(
            workspace_name=workspace_name,
            members=members,
            recent_messages=recent_messages,
            fetched_at=now,
        )
        self._ws_context_cache[workspace_id] = ctx
        return ctx

    async def _do_deliver(
        self,
        envelope: MessageEnvelope,
        target_node_id: str,
        workspace_id: str,
        db: Any,
        start: float,
    ) -> DeliveryResult:
        from sqlalchemy import select

        from app.models.base import not_deleted
        from app.models.instance import Instance
        from app.models.node_card import NodeCard

        card_result = await db.execute(
            select(NodeCard).where(
                NodeCard.node_id == target_node_id,
                NodeCard.workspace_id == workspace_id,
                not_deleted(NodeCard),
            )
        )
        card = card_result.scalar_one_or_none()
        if card is None:
            return DeliveryResult(
                success=False, target_node_id=target_node_id,
                transport=self.transport_id, error="node_card_not_found",
                latency_ms=int((time.monotonic() - start) * 1000),
            )

        inst_result = await db.execute(
            select(Instance).where(Instance.id == target_node_id, not_deleted(Instance))
        )
        inst = inst_result.scalar_one_or_none()
        if inst is None:
            return DeliveryResult(
                success=False, target_node_id=target_node_id,
                transport=self.transport_id, error="instance_not_found",
                latency_ms=int((time.monotonic() - start) * 1000),
            )

        agent_name = card.name or inst.name
        data = envelope.data
        if data is None:
            return DeliveryResult(
                success=False, target_node_id=target_node_id,
                transport=self.transport_id, error="no_envelope_data",
                latency_ms=int((time.monotonic() - start) * 1000),
            )

        from app.services import workspace_message_service as msg_service
        from app.services.corridor_router import get_reachable_names

        ws_ctx = await self._fetch_workspace_context(workspace_id, db)
        reachable = await get_reachable_names(workspace_id, target_node_id, db)

        context_prompt = msg_service.build_context_prompt(
            workspace_name=ws_ctx.workspace_name,
            agent_display_name=agent_name,
            current_instance_id=target_node_id,
            members=ws_ctx.members,
            recent_messages=ws_ctx.recent_messages,
            workspace_id=workspace_id,
            reachable_names=reachable,
        )

        mention_targets: list[str] = data.extensions.get("mention_targets", [])
        is_mention_all = MENTION_ALL_SENTINEL in mention_targets
        is_mentioned = (
            is_mention_all
            or agent_name in mention_targets
            or target_node_id in mention_targets
        )
        has_any_mention = len(mention_targets) > 0
        no_reply = False

        if not has_any_mention:
            no_reply = True
        elif has_any_mention and not is_mentioned:
            no_reply = True
        elif has_any_mention and is_mentioned:
            context_prompt += "\n[重要] 用户在消息中 @提及了你，请务必回复。"

        from app.api.workspaces import broadcast_event

        if no_reply:
            logger.info(
                "Mention skip for %s: targets=%s, mentioned=%s",
                agent_name, mention_targets, is_mentioned,
            )
            return DeliveryResult(
                success=True, target_node_id=target_node_id,
                transport=self.transport_id,
                latency_ms=int((time.monotonic() - start) * 1000),
                extra={"no_reply": True},
            )

        broadcast_event(workspace_id, "agent:typing", {
            "instance_id": target_node_id,
            "agent_name": agent_name,
        })

        user_content = _format_user_content(data.sender.name, data.content, data.attachments)
        messages = [
            {"role": "system", "content": context_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            chat_stream = await self.send_chat_request(
                target_node_id, messages,
                workspace_id=workspace_id,
                trace_id=envelope.traceid,
                stream=True,
            )
        except ConnectionError as e:
            return DeliveryResult(
                success=False, target_node_id=target_node_id,
                transport=self.transport_id, error=str(e),
                latency_ms=int((time.monotonic() - start) * 1000),
            )

        buffer = ""
        flushed = False
        full_response = ""
        error_msg: str | None = None
        error_type: str | None = None
        error_raw: str | None = None

        try:
            async for chunk_msg in chat_stream:
                if chunk_msg.type == TunnelMessageType.CHAT_RESPONSE_ERROR:
                    raw_error = chunk_msg.payload.get("error", "unknown_error")
                    error_msg = str(raw_error)[:256]
                    error_type = chunk_msg.payload.get("error_type")
                    raw_body = chunk_msg.payload.get("error_raw")
                    if raw_body:
                        error_raw = str(raw_body)[:2048]
                    break
                if chunk_msg.type == TunnelMessageType.CHAT_RESPONSE_DONE:
                    break

                content = chunk_msg.payload.get("content", "")
                if not content:
                    continue

                full_response += content
                if not flushed:
                    buffer += content
                    if len(buffer) > NO_REPLY_BUFFER_SIZE:
                        if msg_service.is_no_reply(buffer.strip()):
                            logger.info("Agent %s replied NO_REPLY", agent_name)
                            broadcast_event(workspace_id, "agent:done", {
                                "instance_id": target_node_id, "agent_name": agent_name,
                            })
                            return DeliveryResult(
                                success=True, target_node_id=target_node_id,
                                transport=self.transport_id,
                                latency_ms=int((time.monotonic() - start) * 1000),
                                extra={"no_reply": True},
                            )
                        broadcast_event(workspace_id, "agent:chunk", {
                            "instance_id": target_node_id,
                            "agent_name": agent_name,
                            "content": buffer,
                            "trace_id": envelope.traceid,
                        })
                        flushed = True
                else:
                    broadcast_event(workspace_id, "agent:chunk", {
                        "instance_id": target_node_id,
                        "agent_name": agent_name,
                        "content": content,
                        "trace_id": envelope.traceid,
                    })
        except Exception as e:
            error_msg = str(e)
            logger.error("Agent %s streaming failed: %s", agent_name, e)

        if error_msg:
            error_code = "llm_error" if error_type == "llm" else "stream_error"
            evt: dict = {
                "instance_id": target_node_id, "agent_name": agent_name,
                "error": error_code, "error_detail": error_msg,
            }
            if error_raw:
                evt["error_raw"] = error_raw
            broadcast_event(workspace_id, "agent:error", evt)
            return DeliveryResult(
                success=False, target_node_id=target_node_id,
                transport=self.transport_id, error=error_msg,
                latency_ms=int((time.monotonic() - start) * 1000),
            )

        if not flushed and buffer:
            if msg_service.is_no_reply(buffer.strip()):
                broadcast_event(workspace_id, "agent:done", {
                    "instance_id": target_node_id, "agent_name": agent_name,
                })
                return DeliveryResult(
                    success=True, target_node_id=target_node_id,
                    transport=self.transport_id,
                    latency_ms=int((time.monotonic() - start) * 1000),
                    extra={"no_reply": True},
                )
            broadcast_event(workspace_id, "agent:chunk", {
                "instance_id": target_node_id, "agent_name": agent_name,
                "content": buffer, "trace_id": envelope.traceid,
            })

        delegation = _parse_delegation(full_response)
        if delegation:
            action, delegate_target = delegation
            logger.info("Agent %s issued %s to %s", agent_name, action, delegate_target)
            try:
                await self._handle_delegation(
                    action, delegate_target, envelope, target_node_id, workspace_id, db,
                )
            except Exception as e:
                logger.warning("Delegation %s->%s failed: %s", action, delegate_target, e)

        elif full_response and not msg_service.is_no_reply(full_response.strip()):
            upstream_sender = data.sender.name if data.sender else ""
            mentions = _extract_mentions(
                full_response, ws_ctx.members, agent_name,
                exclude_names=[upstream_sender] if upstream_sender else None,
            )
            logger.info(
                "Agent %s response mentions=%s (upstream=%s, response_len=%d)",
                agent_name, [m["name"] for m in mentions], upstream_sender, len(full_response),
            )
            if mentions:
                depth = (data.extensions or {}).get("depth", 0)
                from app.core.deps import async_session_factory
                async with async_session_factory() as save_db:
                    collab_limit = await get_collaboration_depth_limit(save_db, workspace_id)
                    if depth < collab_limit:
                        saved_msg = await msg_service.record_message(
                            save_db,
                            workspace_id=workspace_id,
                            sender_type="agent",
                            sender_id=target_node_id,
                            sender_name=agent_name,
                            content=full_response,
                            message_type="collaboration",
                            depth=depth,
                        )
                if depth < collab_limit:
                    broadcast_event(workspace_id, "agent:collaboration", {
                        "instance_id": target_node_id,
                        "agent_name": agent_name,
                        "content": full_response,
                        "envelope_id": saved_msg.id,
                        "trace_id": envelope.traceid,
                    })
                    for mention in mentions:
                        if mention["type"] == "agent":
                            from app.services.runtime.messaging.ingestion.agent import (
                                build_agent_collaboration_envelope,
                            )
                            collab_env = build_agent_collaboration_envelope(
                                workspace_id=workspace_id,
                                source_instance_id=target_node_id,
                                source_name=agent_name,
                                target=f"agent:{mention['name']}",
                                content=full_response,
                                depth=depth + 1,
                            )
                            from app.services.runtime.messaging.bus import message_bus
                            async with async_session_factory() as route_db:
                                await message_bus.publish(collab_env, db=route_db)
                        elif mention["type"] == "human":
                            from app.services.collaboration_service import (
                                _find_human_by_display_name,
                                _route_to_human,
                            )
                            async with async_session_factory() as route_db:
                                hh = await _find_human_by_display_name(
                                    route_db, workspace_id, mention["name"],
                                )
                                if hh:
                                    await _route_to_human(
                                        route_db, workspace_id,
                                        target_node_id, agent_name, hh, full_response,
                                    )
                                else:
                                    logger.warning(
                                        "Human mention target not found: %s in workspace %s",
                                        mention["name"], workspace_id,
                                    )
                    broadcast_event(workspace_id, "agent:done", {
                        "instance_id": target_node_id, "agent_name": agent_name,
                    })
                    return DeliveryResult(
                        success=True, target_node_id=target_node_id,
                        transport=self.transport_id,
                        latency_ms=int((time.monotonic() - start) * 1000),
                    )
                else:
                    logger.warning(
                        "Mention routing skipped: depth %d >= %d",
                        depth, collab_limit,
                    )

        if full_response and not msg_service.is_no_reply(full_response.strip()):
            broadcast_event(workspace_id, "agent:done", {
                "instance_id": target_node_id,
                "agent_name": agent_name,
                "full_content": full_response,
                "trace_id": envelope.traceid,
            })
            from app.core.deps import async_session_factory
            async with async_session_factory() as save_db:
                await msg_service.record_message(
                    save_db,
                    workspace_id=workspace_id,
                    sender_type="agent",
                    sender_id=target_node_id,
                    sender_name=agent_name,
                    content=full_response,
                )
        elif not full_response:
            broadcast_event(workspace_id, "agent:error", {
                "instance_id": target_node_id, "agent_name": agent_name,
                "error": "empty_response",
            })
        else:
            broadcast_event(workspace_id, "agent:done", {
                "instance_id": target_node_id, "agent_name": agent_name,
            })

        return DeliveryResult(
            success=True, target_node_id=target_node_id,
            transport=self.transport_id,
            latency_ms=int((time.monotonic() - start) * 1000),
        )

    async def _handle_delegation(
        self,
        action: str,
        target_name: str,
        original_envelope: MessageEnvelope,
        source_node_id: str,
        workspace_id: str,
        db: Any,
    ) -> None:
        from sqlalchemy import select

        from app.models.base import not_deleted
        from app.services.runtime.messaging.envelope import (
            IntentType,
            MessageData,
            MessageSender,
            SenderType,
        )

        prev_visited = (
            original_envelope.data.routing.visited if original_envelope.data else []
        )
        delegation_limit = await get_collaboration_depth_limit(db, workspace_id)
        if len(prev_visited) >= delegation_limit:
            logger.warning(
                "Collaboration depth limit (%d) reached, refusing %s from %s",
                delegation_limit, action, source_node_id,
            )
            return

        if action == "escalate":
            from app.models.node_card import NodeCard
            result = await db.execute(
                select(NodeCard).where(
                    NodeCard.workspace_id == workspace_id,
                    NodeCard.node_type == "human",
                    not_deleted(NodeCard),
                ).limit(1)
            )
            human_card = result.scalar_one_or_none()
            if human_card:
                target_name = human_card.node_id

        new_visited = list(prev_visited) + [source_node_id]

        new_envelope = MessageEnvelope(
            source=f"agent/{source_node_id}",
            type="deskclaw.msg.v1.chat",
            workspaceid=workspace_id,
            causationid=original_envelope.id,
            correlationid=original_envelope.correlationid or original_envelope.id,
            traceid=original_envelope.traceid,
            data=MessageData(
                sender=MessageSender(
                    id=source_node_id,
                    type=SenderType.AGENT,
                    name=f"agent:{source_node_id}",
                    instance_id=source_node_id,
                ),
                intent=IntentType.COLLABORATE,
                content=original_envelope.data.content if original_envelope.data else "",
                extensions={"delegation_action": action, "delegation_from": source_node_id},
            ),
        )
        new_envelope.data.routing.target = target_name
        new_envelope.data.routing.targets = [target_name]
        new_envelope.data.routing.visited = new_visited

        from app.services.runtime.messaging.bus import message_bus
        await message_bus.publish(new_envelope, db=db)

    async def health_check(self, target_node_id: str) -> bool:
        return target_node_id in self._connections

    # ── Offline message replay ───────────────────────────────

    async def _safe_replay(self, instance_id: str) -> None:
        try:
            await self._replay_pending_messages(instance_id)
        except asyncio.CancelledError:
            logger.info("Tunnel: replay cancelled for %s (connection closed)", instance_id)
        except Exception as e:
            logger.warning("Tunnel: offline replay failed for %s: %s", instance_id, e)

    async def _replay_pending_messages(self, instance_id: str) -> None:
        from app.core.deps import async_session_factory
        from app.services.runtime.messaging.queue import ack, dequeue, nack

        async with async_session_factory() as db:
            items = await dequeue(db, target_node_id=instance_id, batch_size=50)
            if not items:
                return

            logger.info("Tunnel: replaying %d offline messages for %s", len(items), instance_id)
            for item in items:
                try:
                    envelope = MessageEnvelope.from_dict(item.envelope or {})
                    workspace_id = item.workspace_id or envelope.workspaceid
                    result = await self._do_deliver(
                        envelope, instance_id, workspace_id, db, time.monotonic(),
                    )
                    if result.success:
                        await ack(db, str(item.id))
                    else:
                        await nack(db, str(item.id), result.error or "replay_failed")
                except Exception as e:
                    logger.warning("Tunnel: replay delivery failed for item %s: %s", item.id, e)
            await db.commit()

    # ── Ping/Pong ────────────────────────────────────────────

    async def _ping_loop(self, instance_id: str) -> None:
        try:
            while instance_id in self._connections:
                await asyncio.sleep(PING_INTERVAL_S)
                conn = self._connections.get(instance_id)
                if not conn:
                    break
                if time.monotonic() - conn.last_pong > PING_TIMEOUT_S:
                    logger.warning("Tunnel: instance %s ping timeout, closing", instance_id)
                    try:
                        await conn.ws.close(code=4020, reason="ping_timeout")
                    except Exception:
                        logger.warning("Tunnel: failed to close ws on ping timeout for %s", instance_id, exc_info=True)
                    break
                try:
                    await self._send(conn.ws, TunnelMessage(type=TunnelMessageType.PING))
                except Exception:
                    break
        except asyncio.CancelledError:
            pass

    # ── Internal helpers ─────────────────────────────────────

    async def _verify_token(self, instance_id: str, token: str) -> bool:
        from app.core.deps import async_session_factory
        from sqlalchemy import select

        from app.models.base import not_deleted
        from app.models.instance import Instance

        async with async_session_factory() as db:
            result = await db.execute(
                select(Instance).where(Instance.id == instance_id, not_deleted(Instance))
            )
            inst = result.scalar_one_or_none()
            if inst is None:
                return False
            env_vars = json.loads(inst.env_vars or "{}")
            expected_token = env_vars.get("GATEWAY_TOKEN") or env_vars.get("OPENCLAW_GATEWAY_TOKEN", "")
            return bool(expected_token and token == expected_token)

    async def _send(self, ws: WebSocket, msg: TunnelMessage) -> None:
        if ws.client_state == WebSocketState.CONNECTED:
            await ws.send_json(msg.to_dict())
            self._stats["total_messages_out"] += 1
            logger.debug(
                "[%s] tunnel send type=%s", msg.trace_id or "-", msg.type,
            )

    def _cleanup_instance(self, instance_id: str) -> None:
        conn = self._connections.pop(instance_id, None)
        if conn:
            conn.cancel_all()
        task = self._ping_tasks.pop(instance_id, None)
        if task and not task.done():
            task.cancel()
        logger.info("Tunnel: instance %s cleaned up", instance_id)

    def _broadcast_connection_event(self, instance_id: str, *, connected: bool) -> None:
        try:
            from app.core.deps import async_session_factory
            from app.models.workspace_agent import WorkspaceAgent
            from app.models.base import not_deleted

            async def _do_broadcast():
                from sqlalchemy import select

                resolved_status: str | None = None
                async with async_session_factory() as db:
                    result = await db.execute(
                        select(WorkspaceAgent.workspace_id).where(
                            WorkspaceAgent.instance_id == instance_id,
                            not_deleted(WorkspaceAgent),
                        )
                    )
                    ws_ids = [r[0] for r in result.all()]

                    if connected:
                        from app.models.instance import Instance, InstanceStatus
                        inst = await db.get(Instance, instance_id)
                        _transitional = {
                            InstanceStatus.restarting, InstanceStatus.deploying,
                            InstanceStatus.updating, InstanceStatus.creating,
                        }
                        if inst and inst.status in _transitional:
                            old_status = inst.status
                            inst.status = InstanceStatus.running
                            inst.health_status = "unknown"
                            await db.commit()
                            resolved_status = "running"
                            logger.info(
                                "隧道连接触发状态恢复: instance=%s %s -> running",
                                instance_id, old_status,
                            )

                from app.api.workspaces import broadcast_event
                event_name = "agent:sse_connected" if connected else "agent:sse_disconnected"
                for ws_id in ws_ids:
                    broadcast_event(ws_id, event_name, {"instance_id": instance_id})

                if resolved_status:
                    for ws_id in ws_ids:
                        broadcast_event(ws_id, "agent:status", {
                            "instance_id": instance_id, "status": resolved_status,
                        })

            asyncio.create_task(_do_broadcast())
        except Exception as e:
            logger.warning("Tunnel: broadcast connection event failed: %s", e)

    # ── Observability ────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        now = time.monotonic()
        instances = []
        for iid, conn in self._connections.items():
            instances.append({
                "instance_id": iid,
                "connected_seconds": int(now - conn.connected_at),
                "last_pong_seconds_ago": int(now - conn.last_pong),
                "messages_in": conn.msg_count_in,
                "messages_out": conn.msg_count_out,
            })
        return {
            "connected_count": len(self._connections),
            "instances": instances,
            **self._stats,
        }


class AsyncChatStream:
    """Async iterator that yields TunnelMessage chunks for a chat request."""

    def __init__(self, conn: _InstanceConnection, request_id: str, trace_id: str) -> None:
        self._conn = conn
        self._request_id = request_id
        self._trace_id = trace_id
        self._queue = conn.register_stream(request_id)
        self._done = False

    def __aiter__(self):
        return self

    async def __anext__(self) -> TunnelMessage:
        if self._done and self._queue.empty():
            self._conn.unregister_stream(self._request_id)
            raise StopAsyncIteration
        try:
            msg = await asyncio.wait_for(self._queue.get(), timeout=600)
            if msg.type in (TunnelMessageType.CHAT_RESPONSE_DONE, TunnelMessageType.CHAT_RESPONSE_ERROR):
                self._done = True
                self._conn.unregister_stream(self._request_id)
            return msg
        except asyncio.TimeoutError:
            logger.warning(
                "Chat stream timeout (600s) for request %s, trace=%s",
                self._request_id, self._trace_id,
            )
            self._conn.unregister_stream(self._request_id)
            raise StopAsyncIteration
