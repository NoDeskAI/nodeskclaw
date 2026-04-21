from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api.blackboard import _notify_mentions
from app.services.runtime.messaging.ingestion.system import build_system_envelope


@pytest.mark.asyncio
async def test_notify_mentions_targets_agents_and_guides_reply():
    mentions = [
        SimpleNamespace(type="agent", id="inst-001"),
        SimpleNamespace(type="human", id="user-001"),
        SimpleNamespace(type="agent", id="inst-002"),
    ]

    with (
        patch(
            "app.services.collaboration_service.send_system_message_to_agents",
            new_callable=AsyncMock,
        ) as mock_send,
        patch(
            "app.services.corridor_router.has_any_connections",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        await _notify_mentions(
            "ws-001",
            mentions,
            "Alice",
            "post-001",
            "Sprint Planning",
            "post",
            AsyncMock(),
        )

    mock_send.assert_awaited_once()
    args, kwargs = mock_send.await_args
    assert args[0] == "ws-001"
    assert args[1] == ["inst-001", "inst-002"]
    assert args[2] == (
        'Alice mentioned you in a blackboard post "Sprint Planning" (post_id: post-001). '
        'Reply in the blackboard thread with the nodeskclaw_blackboard tool '
        'using action "reply_post" and this post_id. Do not reply in chat.'
    )
    assert kwargs["mention_targets"] == ["inst-001", "inst-002"]


@pytest.mark.asyncio
async def test_notify_mentions_skips_when_no_agent_targets():
    mentions = [SimpleNamespace(type="human", id="user-001")]

    with (
        patch(
            "app.services.collaboration_service.send_system_message_to_agents",
            new_callable=AsyncMock,
        ) as mock_send,
        patch(
            "app.services.corridor_router.has_any_connections",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        await _notify_mentions(
            "ws-001",
            mentions,
            "Alice",
            "post-001",
            "Sprint Planning",
            "reply",
            AsyncMock(),
        )

    mock_send.assert_not_awaited()


def test_build_system_envelope_keeps_mention_targets():
    envelope = build_system_envelope(
        workspace_id="ws-001",
        content="hello",
        targets=["inst-001", "inst-002"],
        mention_targets=["inst-001", "inst-002"],
    )

    assert envelope.data is not None
    assert envelope.data.routing.targets == ["inst-001", "inst-002"]
    assert envelope.data.extensions["mention_targets"] == ["inst-001", "inst-002"]
