from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api import workspaces
from app.core.security import AuthActor, _auth_actor
from app.schemas.workspace import CollaborationSendRequest


class _ScalarResult:
    def __init__(self, value: str | None) -> None:
        self._value = value

    def scalar_one_or_none(self) -> str | None:
        return self._value


class _WorkspaceAgentDb:
    def __init__(self, *, has_agent: bool = True) -> None:
        self.has_agent = has_agent

    async def execute(self, _stmt):
        return _ScalarResult("workspace-agent-1" if self.has_agent else None)


@pytest.fixture
def agent_actor():
    token = _auth_actor.set(AuthActor("agent", "inst-1", "Hermes"))
    try:
        yield
    finally:
        _auth_actor.reset(token)


async def test_send_collaboration_message_requires_source_agent_in_workspace(monkeypatch, agent_actor):
    monkeypatch.setattr(workspaces.wm_service, "check_workspace_member", AsyncMock())
    handle_message = AsyncMock()
    monkeypatch.setattr("app.services.collaboration_service.handle_collaboration_message", handle_message)

    with pytest.raises(HTTPException) as exc:
        await workspaces.send_collaboration_message(
            "ws-1",
            CollaborationSendRequest(target="agent:Bob", text="hello"),
            db=_WorkspaceAgentDb(has_agent=False),
            user=SimpleNamespace(id="user-1"),
        )

    assert exc.value.status_code == 403
    assert exc.value.detail["message_key"] == "errors.workspace.agent_not_in_workspace"
    handle_message.assert_not_awaited()


async def test_send_collaboration_message_uses_proxy_agent_as_source(monkeypatch, agent_actor):
    monkeypatch.setattr(workspaces.wm_service, "check_workspace_member", AsyncMock())
    handle_message = AsyncMock()
    monkeypatch.setattr("app.services.collaboration_service.handle_collaboration_message", handle_message)

    response = await workspaces.send_collaboration_message(
        "ws-1",
        CollaborationSendRequest(target="agent:Bob", text="hello"),
        db=_WorkspaceAgentDb(has_agent=True),
        user=SimpleNamespace(id="user-1"),
    )

    assert response["code"] == 0
    handle_message.assert_awaited_once()
    assert handle_message.await_args.kwargs["source_instance_id"] == "inst-1"


async def test_agent_auth_can_read_collaboration_timeline(monkeypatch, agent_actor):
    monkeypatch.setattr(workspaces.wm_service, "check_workspace_member", AsyncMock())
    get_timeline = AsyncMock(return_value=[])
    monkeypatch.setattr(workspaces.msg_service, "get_collaboration_timeline", get_timeline)

    response = await workspaces.list_collaboration_timeline(
        "ws-1",
        limit=50,
        since=None,
        db=_WorkspaceAgentDb(has_agent=True),
        user=SimpleNamespace(id="user-1"),
    )

    assert response["code"] == 0
    get_timeline.assert_awaited_once()


async def test_agent_auth_can_only_read_own_collaboration_messages(monkeypatch, agent_actor):
    monkeypatch.setattr(workspaces.wm_service, "check_workspace_member", AsyncMock())
    get_messages = AsyncMock(return_value=[])
    monkeypatch.setattr(workspaces.msg_service, "get_agent_collaboration_messages", get_messages)

    with pytest.raises(HTTPException) as exc:
        await workspaces.list_agent_collaboration_messages(
            "ws-1",
            "inst-2",
            limit=50,
            db=_WorkspaceAgentDb(has_agent=True),
            user=SimpleNamespace(id="user-1"),
        )

    assert exc.value.status_code == 403
    assert exc.value.detail["message_key"] == "errors.collaboration.agent_scope_forbidden"
    get_messages.assert_not_awaited()
