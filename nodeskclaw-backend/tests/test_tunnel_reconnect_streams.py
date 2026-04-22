"""TunnelAdapter 隧道重连时 in-flight stream 保活测试。

验证 WebSocket 重连后，正在等待响应的 streaming queue 能被转移到新连接，
而非被 cancel_all() 清空导致 agent 回复丢失。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.tunnel.adapter import TunnelAdapter, _InstanceConnection
from app.services.tunnel.protocol import TunnelMessage, TunnelMessageType

INSTANCE_ID = "inst-reconnect-001"


def _make_ws_mock() -> MagicMock:
    ws = AsyncMock()
    from starlette.websockets import WebSocketState
    ws.client_state = WebSocketState.CONNECTED
    return ws


def test_cancel_all_clears_stream_queues():
    """cancel_all 应当清空 _instance_streams（基线行为确认）。"""
    streams: dict = {}
    ws = _make_ws_mock()
    conn = _InstanceConnection(ws, INSTANCE_ID, streams)
    q = conn.register_stream("req-1")
    assert "req-1" in conn._instance_streams

    conn.cancel_all()
    assert len(conn._instance_streams) == 0
    assert q.empty()


def test_stream_queue_snapshot_survives_cancel_all():
    """在 cancel_all 之前对 _instance_streams 取快照，快照中的 Queue 对象应仍可用。"""
    streams: dict = {}
    ws = _make_ws_mock()
    conn = _InstanceConnection(ws, INSTANCE_ID, streams)
    q = conn.register_stream("req-1")

    snapshot = dict(conn._instance_streams)
    conn.cancel_all()

    assert len(conn._instance_streams) == 0
    assert "req-1" in snapshot
    assert snapshot["req-1"] is q

    q.put_nowait(TunnelMessage(type=TunnelMessageType.CHAT_RESPONSE_CHUNK, payload={"content": "hello"}))
    assert not q.empty()


def test_surviving_streams_transferred_to_new_connection():
    """模拟重连流程：adapter 级别 streams dict 在新旧连接间共享。"""
    streams: dict = {}
    old_ws = _make_ws_mock()
    old_conn = _InstanceConnection(old_ws, INSTANCE_ID, streams)
    q = old_conn.register_stream("req-42")

    new_ws = _make_ws_mock()
    new_conn = _InstanceConnection(new_ws, INSTANCE_ID, streams)

    assert "req-42" in new_conn._instance_streams

    chunk = TunnelMessage(
        type=TunnelMessageType.CHAT_RESPONSE_CHUNK,
        payload={"content": "world"},
    )
    resolved = new_conn.resolve_response("req-42", chunk)
    assert resolved is True
    assert not q.empty()
    assert q.get_nowait() is chunk


def test_response_without_handler_returns_false():
    """新连接上如果没有 handler，resolve_response 应返回 False。"""
    streams: dict = {}
    ws = _make_ws_mock()
    conn = _InstanceConnection(ws, INSTANCE_ID, streams)

    chunk = TunnelMessage(
        type=TunnelMessageType.CHAT_RESPONSE_CHUNK,
        payload={"content": "lost"},
    )
    resolved = conn.resolve_response("req-nonexistent", chunk)
    assert resolved is False


def test_resolve_response_auto_cleanup_on_done():
    """resolve_response 收到 DONE/ERROR 时应自动移除 stream 条目，防止重连后泄漏。"""
    streams: dict = {}
    ws = _make_ws_mock()
    conn = _InstanceConnection(ws, INSTANCE_ID, streams)
    q = conn.register_stream("req-77")

    chunk = TunnelMessage(type=TunnelMessageType.CHAT_RESPONSE_CHUNK, payload={"content": "hi"})
    conn.resolve_response("req-77", chunk)
    assert "req-77" in conn._instance_streams

    done = TunnelMessage(type=TunnelMessageType.CHAT_RESPONSE_DONE, payload={})
    conn.resolve_response("req-77", done)
    assert "req-77" not in conn._instance_streams, \
        "Stream entry should be auto-removed after DONE"
    assert q.get_nowait() is chunk
    assert q.get_nowait() is done


@pytest.mark.asyncio
async def test_handle_websocket_transfers_streams_on_reconnect():
    """集成测试：handle_websocket 处理重连时应保留 in-flight streams。"""
    adapter = TunnelAdapter()

    old_ws = _make_ws_mock()
    streams = adapter._instance_streams.setdefault(INSTANCE_ID, {})
    old_conn = _InstanceConnection(old_ws, INSTANCE_ID, streams)
    q = old_conn.register_stream("req-100")
    adapter._connections[INSTANCE_ID] = old_conn

    auth_payload = {
        "type": "auth",
        "payload": {"instance_id": INSTANCE_ID, "token": "valid-token"},
        "ts": 0,
    }

    new_ws = AsyncMock()
    new_ws.client_state = MagicMock()
    from starlette.websockets import WebSocketState
    new_ws.client_state = WebSocketState.CONNECTED
    call_count = 0

    async def receive_json_side_effect():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return auth_payload
        await asyncio.sleep(999)

    new_ws.receive_json = AsyncMock(side_effect=receive_json_side_effect)

    with patch.object(adapter, "_verify_token", new_callable=AsyncMock, return_value=True), \
         patch.object(adapter, "_broadcast_connection_event"), \
         patch.object(adapter, "_safe_replay", new_callable=AsyncMock):

        task = asyncio.create_task(adapter.handle_websocket(new_ws))
        await asyncio.sleep(0.05)

        new_conn = adapter._connections.get(INSTANCE_ID)
        assert new_conn is not None
        assert new_conn is not old_conn
        assert "req-100" in new_conn._instance_streams, \
            "In-flight stream queue should survive reconnection"
        assert new_conn._instance_streams["req-100"] is q, \
            "Should be the same Queue object so waiting coroutines receive messages"

        chunk = TunnelMessage(
            type=TunnelMessageType.CHAT_RESPONSE_CHUNK,
            payload={"content": "agent reply"},
        )
        resolved = new_conn.resolve_response("req-100", chunk)
        assert resolved is True
        msg = q.get_nowait()
        assert msg.payload["content"] == "agent reply"

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
