"""TunnelAdapter._do_deliver 上下文注入测试。

验证消息投递时 build_context_prompt 收到正确的 workspace_name、members、recent_messages，
而非修复前的空值。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.runtime.messaging.envelope import (
    IntentType,
    MessageData,
    MessageEnvelope,
    MessageSender,
    SenderType,
)
from app.services.tunnel.adapter import TunnelAdapter


WORKSPACE_ID = "ws-001"
TARGET_NODE_ID = "inst-001"
AGENT_NAME = "Alice"


def _make_envelope(
    mention_targets: list[str] | None = None,
    content: str = "hello",
) -> MessageEnvelope:
    return MessageEnvelope(
        workspaceid=WORKSPACE_ID,
        data=MessageData(
            sender=MessageSender(id="user-001", type=SenderType.USER, name="Admin"),
            intent=IntentType.CHAT,
            content=content,
            extensions={"mention_targets": mention_targets or []},
        ),
    )


def _make_fake_message(
    sender_id: str = "inst-002",
    sender_name: str = "Bob",
    content: str = "hi there",
) -> MagicMock:
    msg = MagicMock()
    msg.sender_id = sender_id
    msg.sender_name = sender_name
    msg.content = content
    msg.created_at = datetime(2026, 3, 17, 10, 0, 0, tzinfo=timezone.utc)
    msg.attachments = None
    return msg


def _make_db_mock(
    workspace_name: str | None = "Dev Office",
    members_rows: list[tuple[str, str]] | None = None,
) -> AsyncMock:
    """Build an AsyncMock for db.execute that returns appropriate results
    based on call order inside _do_deliver."""

    if members_rows is None:
        members_rows = [("agent", AGENT_NAME), ("agent", "Bob"), ("human", "Admin")]

    card_mock = MagicMock()
    card_mock.name = AGENT_NAME
    card_result = MagicMock()
    card_result.scalar_one_or_none.return_value = card_mock

    inst_mock = MagicMock()
    inst_mock.name = AGENT_NAME
    inst_result = MagicMock()
    inst_result.scalar_one_or_none.return_value = inst_mock

    ws_result = MagicMock()
    ws_result.scalar_one_or_none.return_value = workspace_name

    members_result = MagicMock()
    members_result.all.return_value = members_rows

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[card_result, inst_result, ws_result, members_result]
    )
    return db


@pytest.mark.asyncio
async def test_context_prompt_receives_workspace_name():
    """workspace_name 应从数据库查询获得，而非空字符串。"""
    db = _make_db_mock(workspace_name="Dev Office")
    envelope = _make_envelope(mention_targets=[TARGET_NODE_ID])
    adapter = TunnelAdapter()

    with patch(
        "app.services.workspace_message_service.get_recent_messages",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.services.workspace_message_service.build_context_prompt",
        return_value="mocked prompt",
    ) as mock_build, patch.object(
        adapter, "send_chat_request", new_callable=AsyncMock,
        return_value=_fake_stream("ok"),
    ), patch("app.api.workspaces.broadcast_event"):
        await adapter._do_deliver(envelope, TARGET_NODE_ID, WORKSPACE_ID, db, time.monotonic())

    mock_build.assert_called_once()
    _, call_kwargs = mock_build.call_args
    assert call_kwargs["workspace_name"] == "Dev Office"


@pytest.mark.asyncio
async def test_context_prompt_receives_members():
    """members 应包含 agent 和 human 类型的节点卡片。"""
    members_rows = [("agent", "Alice"), ("agent", "Bob"), ("human", "Admin")]
    db = _make_db_mock(members_rows=members_rows)
    envelope = _make_envelope(mention_targets=[TARGET_NODE_ID])
    adapter = TunnelAdapter()

    with patch(
        "app.services.workspace_message_service.get_recent_messages",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.services.workspace_message_service.build_context_prompt",
        return_value="mocked prompt",
    ) as mock_build, patch.object(
        adapter, "send_chat_request", new_callable=AsyncMock,
        return_value=_fake_stream("ok"),
    ), patch("app.api.workspaces.broadcast_event"):
        await adapter._do_deliver(envelope, TARGET_NODE_ID, WORKSPACE_ID, db, time.monotonic())

    _, call_kwargs = mock_build.call_args
    members_arg = call_kwargs["members"]
    assert len(members_arg) == 3
    assert {"type": "agent", "name": "Alice"} in members_arg
    assert {"type": "human", "name": "Admin"} in members_arg


@pytest.mark.asyncio
async def test_context_prompt_receives_recent_messages():
    """recent_messages 应传入 get_recent_messages 的返回值。"""
    fake_msgs = [_make_fake_message(), _make_fake_message(sender_name="Charlie")]
    db = _make_db_mock()
    envelope = _make_envelope(mention_targets=[TARGET_NODE_ID])
    adapter = TunnelAdapter()

    with patch(
        "app.services.workspace_message_service.get_recent_messages",
        new_callable=AsyncMock,
        return_value=fake_msgs,
    ), patch(
        "app.services.workspace_message_service.build_context_prompt",
        return_value="mocked prompt",
    ) as mock_build, patch.object(
        adapter, "send_chat_request", new_callable=AsyncMock,
        return_value=_fake_stream("ok"),
    ), patch("app.api.workspaces.broadcast_event"):
        await adapter._do_deliver(envelope, TARGET_NODE_ID, WORKSPACE_ID, db, time.monotonic())

    _, call_kwargs = mock_build.call_args
    assert call_kwargs["recent_messages"] is fake_msgs


@pytest.mark.asyncio
async def test_workspace_not_found_falls_back_to_empty():
    """workspace 不存在时 workspace_name 应回退为空字符串。"""
    db = _make_db_mock(workspace_name=None)
    envelope = _make_envelope(mention_targets=[TARGET_NODE_ID])
    adapter = TunnelAdapter()

    with patch(
        "app.services.workspace_message_service.get_recent_messages",
        new_callable=AsyncMock,
        return_value=[],
    ), patch(
        "app.services.workspace_message_service.build_context_prompt",
        return_value="mocked prompt",
    ) as mock_build, patch.object(
        adapter, "send_chat_request", new_callable=AsyncMock,
        return_value=_fake_stream("ok"),
    ), patch("app.api.workspaces.broadcast_event"):
        await adapter._do_deliver(envelope, TARGET_NODE_ID, WORKSPACE_ID, db, time.monotonic())

    _, call_kwargs = mock_build.call_args
    assert call_kwargs["workspace_name"] == ""


@pytest.mark.asyncio
async def test_no_reply_path_also_gets_context():
    """未被 @mention 时走 no_reply 路径，但 context prompt 仍应包含完整上下文。"""
    db = _make_db_mock(workspace_name="Dev Office")
    envelope = _make_envelope(mention_targets=[])
    adapter = TunnelAdapter()

    with patch(
        "app.services.workspace_message_service.get_recent_messages",
        new_callable=AsyncMock,
        return_value=[_make_fake_message()],
    ), patch(
        "app.services.workspace_message_service.build_context_prompt",
        return_value="mocked prompt",
    ) as mock_build, patch.object(
        adapter, "send_chat_request", new_callable=AsyncMock,
        return_value=_fake_stream(""),
    ), patch("app.api.workspaces.broadcast_event"):
        result = await adapter._do_deliver(
            envelope, TARGET_NODE_ID, WORKSPACE_ID, db, time.monotonic(),
        )

    assert result.success is True
    assert result.extra.get("no_reply") is True
    mock_build.assert_called_once()
    _, call_kwargs = mock_build.call_args
    assert call_kwargs["workspace_name"] == "Dev Office"
    assert len(call_kwargs["members"]) == 3
    assert len(call_kwargs["recent_messages"]) == 1


@pytest.mark.asyncio
async def test_node_card_not_found_returns_error():
    """目标 node_card 不存在时应直接返回失败，不执行上下文查询。"""
    db = AsyncMock()
    card_result = MagicMock()
    card_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=card_result)

    envelope = _make_envelope(mention_targets=[TARGET_NODE_ID])
    adapter = TunnelAdapter()

    result = await adapter._do_deliver(
        envelope, TARGET_NODE_ID, WORKSPACE_ID, db, time.monotonic(),
    )

    assert result.success is False
    assert result.error == "node_card_not_found"
    assert db.execute.call_count == 1


async def _fake_stream(content: str):
    """Async generator that yields a single chunk then stops."""
    yield {"choices": [{"delta": {"content": content}}]}
