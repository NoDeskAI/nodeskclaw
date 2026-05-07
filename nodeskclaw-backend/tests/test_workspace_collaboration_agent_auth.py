from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api import blackboard
from app.api import corridors
from app.api import workspaces
from app.core.security import AuthActor, _auth_actor
from app.schemas.workspace import CollaborationSendRequest


class _ScalarResult:
    def __init__(self, value) -> None:
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _ScalarsResult:
    def __init__(self, values: list) -> None:
        self._values = values

    def scalars(self):
        return self

    def all(self) -> list:
        return self._values


class _WorkspaceAgentDb:
    def __init__(self, *, has_agent: bool = True) -> None:
        self.has_agent = has_agent

    async def execute(self, _stmt):
        return _ScalarResult("workspace-agent-1" if self.has_agent else None)


class _SequenceDb:
    def __init__(self, results: list) -> None:
        self._results = list(results)

    async def execute(self, _stmt):
        return self._results.pop(0)


class _Dump:
    def __init__(self, data: dict) -> None:
        self._data = data

    def model_dump(self, mode: str | None = None) -> dict:
        return self._data


@pytest.fixture
def agent_actor():
    token = _auth_actor.set(AuthActor("agent", "inst-1", "Hermes"))
    try:
        yield
    finally:
        _auth_actor.reset(token)


@pytest.fixture
def user_actor():
    token = _auth_actor.set(AuthActor("user", "user-1", "Alice"))
    try:
        yield
    finally:
        _auth_actor.reset(token)


async def _unexpected_workspace_member_check(*_args, **_kwargs):
    raise AssertionError("agent auth should not check WorkspaceMember")


async def _unexpected_workspace_access_check(*_args, **_kwargs):
    raise AssertionError("agent auth should not check WorkspaceMember permission")


async def test_send_collaboration_message_requires_source_agent_in_workspace(monkeypatch, agent_actor):
    monkeypatch.setattr(
        workspaces.wm_service,
        "check_workspace_member",
        AsyncMock(side_effect=_unexpected_workspace_member_check),
    )
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
    workspaces.wm_service.check_workspace_member.assert_not_awaited()
    handle_message.assert_not_awaited()


async def test_send_collaboration_message_uses_proxy_agent_as_source(monkeypatch, agent_actor):
    monkeypatch.setattr(
        workspaces.wm_service,
        "check_workspace_member",
        AsyncMock(side_effect=_unexpected_workspace_member_check),
    )
    handle_message = AsyncMock()
    monkeypatch.setattr("app.services.collaboration_service.handle_collaboration_message", handle_message)

    response = await workspaces.send_collaboration_message(
        "ws-1",
        CollaborationSendRequest(target="agent:Bob", text="hello"),
        db=_WorkspaceAgentDb(has_agent=True),
        user=SimpleNamespace(id="user-1"),
    )

    assert response["code"] == 0
    workspaces.wm_service.check_workspace_member.assert_not_awaited()
    handle_message.assert_awaited_once()
    assert handle_message.await_args.kwargs["source_instance_id"] == "inst-1"


async def test_agent_auth_can_read_collaboration_timeline(monkeypatch, agent_actor):
    monkeypatch.setattr(
        workspaces.wm_service,
        "check_workspace_member",
        AsyncMock(side_effect=_unexpected_workspace_member_check),
    )
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
    workspaces.wm_service.check_workspace_member.assert_not_awaited()
    get_timeline.assert_awaited_once()


async def test_agent_auth_can_only_read_own_collaboration_messages(monkeypatch, agent_actor):
    monkeypatch.setattr(
        workspaces.wm_service,
        "check_workspace_member",
        AsyncMock(side_effect=_unexpected_workspace_member_check),
    )
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
    workspaces.wm_service.check_workspace_member.assert_not_awaited()
    get_messages.assert_not_awaited()


async def test_agent_auth_can_read_own_collaboration_messages(monkeypatch, agent_actor):
    monkeypatch.setattr(
        workspaces.wm_service,
        "check_workspace_member",
        AsyncMock(side_effect=_unexpected_workspace_member_check),
    )
    get_messages = AsyncMock(return_value=[])
    monkeypatch.setattr(workspaces.msg_service, "get_agent_collaboration_messages", get_messages)

    response = await workspaces.list_agent_collaboration_messages(
        "ws-1",
        "inst-1",
        limit=50,
        db=_WorkspaceAgentDb(has_agent=True),
        user=SimpleNamespace(id="user-1"),
    )

    assert response["code"] == 0
    workspaces.wm_service.check_workspace_member.assert_not_awaited()
    get_messages.assert_awaited_once()


async def test_user_auth_reads_collaboration_timeline_through_workspace_member(monkeypatch, user_actor):
    check_member = AsyncMock()
    monkeypatch.setattr(workspaces.wm_service, "check_workspace_member", check_member)
    get_timeline = AsyncMock(return_value=[])
    monkeypatch.setattr(workspaces.msg_service, "get_collaboration_timeline", get_timeline)

    response = await workspaces.list_collaboration_timeline(
        "ws-1",
        limit=50,
        since=None,
        db=_WorkspaceAgentDb(has_agent=False),
        user=SimpleNamespace(id="user-1"),
    )

    assert response["code"] == 0
    check_member.assert_awaited_once()
    get_timeline.assert_awaited_once()


async def test_user_auth_reads_agent_messages_through_workspace_member(monkeypatch, user_actor):
    check_member = AsyncMock()
    monkeypatch.setattr(workspaces.wm_service, "check_workspace_member", check_member)
    get_messages = AsyncMock(return_value=[])
    monkeypatch.setattr(workspaces.msg_service, "get_agent_collaboration_messages", get_messages)

    response = await workspaces.list_agent_collaboration_messages(
        "ws-1",
        "inst-2",
        limit=50,
        db=_WorkspaceAgentDb(has_agent=False),
        user=SimpleNamespace(id="user-1"),
    )

    assert response["code"] == 0
    check_member.assert_awaited_once()
    get_messages.assert_awaited_once()


async def test_agent_auth_can_read_workspace_chat_history(monkeypatch, agent_actor):
    monkeypatch.setattr(
        workspaces.wm_service,
        "check_workspace_member",
        AsyncMock(side_effect=_unexpected_workspace_member_check),
    )
    get_recent_messages = AsyncMock(return_value=[
        SimpleNamespace(
            id="msg-1",
            workspace_id="ws-1",
            sender_type="user",
            sender_id="user-1",
            sender_name="Alice",
            content="hello",
            message_type="chat",
            attachments=[],
            created_at=None,
        )
    ])
    monkeypatch.setattr(workspaces.msg_service, "get_recent_messages", get_recent_messages)

    response = await workspaces.list_workspace_messages(
        "ws-1",
        limit=20,
        q=None,
        from_at=None,
        to_at=None,
        db=_WorkspaceAgentDb(has_agent=True),
        user=SimpleNamespace(id="user-1"),
    )

    assert response["code"] == 0
    assert response["data"][0]["id"] == "msg-1"
    workspaces.wm_service.check_workspace_member.assert_not_awaited()
    get_recent_messages.assert_awaited_once()


async def test_user_auth_reads_workspace_chat_history_through_workspace_member(monkeypatch, user_actor):
    check_member = AsyncMock()
    monkeypatch.setattr(workspaces.wm_service, "check_workspace_member", check_member)
    search_messages = AsyncMock(return_value=[])
    monkeypatch.setattr(workspaces.msg_service, "search_messages", search_messages)

    response = await workspaces.list_workspace_messages(
        "ws-1",
        limit=20,
        q="hello",
        from_at=None,
        to_at=None,
        db=_WorkspaceAgentDb(has_agent=False),
        user=SimpleNamespace(id="user-1"),
    )

    assert response["code"] == 0
    check_member.assert_awaited_once()
    search_messages.assert_awaited_once()


async def test_agent_auth_can_download_workspace_file(monkeypatch, agent_actor):
    monkeypatch.setattr(
        workspaces.wm_service,
        "check_workspace_member",
        AsyncMock(side_effect=_unexpected_workspace_member_check),
    )
    file_row = SimpleNamespace(
        storage_key="workspace/ws-1/report.txt",
        original_name="report.txt",
        content_type="text/plain",
    )
    monkeypatch.setattr("app.services.storage_service.is_configured", lambda: True)
    download_file = AsyncMock(return_value=b"file-body")
    monkeypatch.setattr("app.services.storage_service.download_file", download_file)

    response = await workspaces.download_workspace_file(
        "ws-1",
        "file-1",
        db=_SequenceDb([_ScalarResult("workspace-agent-1"), _ScalarResult(file_row)]),
        user=SimpleNamespace(id="user-1"),
    )

    assert response.body == b"file-body"
    assert response.headers["content-length"] == "9"
    assert "report.txt" in response.headers["content-disposition"]
    workspaces.wm_service.check_workspace_member.assert_not_awaited()
    download_file.assert_awaited_once_with("workspace/ws-1/report.txt")


async def test_agent_auth_download_workspace_file_requires_workspace_agent(monkeypatch, agent_actor):
    monkeypatch.setattr(
        workspaces.wm_service,
        "check_workspace_member",
        AsyncMock(side_effect=_unexpected_workspace_member_check),
    )
    monkeypatch.setattr("app.services.storage_service.is_configured", lambda: True)
    download_file = AsyncMock()
    monkeypatch.setattr("app.services.storage_service.download_file", download_file)

    with pytest.raises(HTTPException) as exc:
        await workspaces.download_workspace_file(
            "ws-1",
            "file-1",
            db=_WorkspaceAgentDb(has_agent=False),
            user=SimpleNamespace(id="user-1"),
        )

    assert exc.value.status_code == 403
    assert exc.value.detail["message_key"] == "errors.workspace.agent_not_in_workspace"
    workspaces.wm_service.check_workspace_member.assert_not_awaited()
    download_file.assert_not_awaited()


async def test_user_auth_download_workspace_file_through_workspace_member(monkeypatch, user_actor):
    check_member = AsyncMock()
    monkeypatch.setattr(workspaces.wm_service, "check_workspace_member", check_member)
    file_row = SimpleNamespace(
        storage_key="workspace/ws-1/report.txt",
        original_name="report.txt",
        content_type="text/plain",
    )
    monkeypatch.setattr("app.services.storage_service.is_configured", lambda: True)
    monkeypatch.setattr("app.services.storage_service.download_file", AsyncMock(return_value=b"file-body"))

    response = await workspaces.download_workspace_file(
        "ws-1",
        "file-1",
        db=_SequenceDb([_ScalarResult(file_row)]),
        user=SimpleNamespace(id="user-1"),
    )

    assert response.body == b"file-body"
    check_member.assert_awaited_once()


async def test_agent_auth_can_read_workspace_blackboard(monkeypatch, agent_actor):
    monkeypatch.setattr(
        workspaces.wm_service,
        "check_workspace_member",
        AsyncMock(side_effect=_unexpected_workspace_member_check),
    )
    monkeypatch.setattr(blackboard, "_enforce_agent_blackboard_topology", AsyncMock())
    get_blackboard = AsyncMock(return_value=_Dump({"id": "bb-1"}))
    monkeypatch.setattr(workspaces.workspace_service, "get_blackboard", get_blackboard)

    response = await workspaces.get_blackboard(
        "ws-1",
        db=_WorkspaceAgentDb(has_agent=True),
        user=SimpleNamespace(id="user-1"),
    )

    assert response["code"] == 0
    assert response["data"]["id"] == "bb-1"
    workspaces.wm_service.check_workspace_member.assert_not_awaited()
    get_blackboard.assert_awaited_once()


async def test_agent_auth_can_write_workspace_blackboard(monkeypatch, agent_actor):
    monkeypatch.setattr(
        workspaces.wm_service,
        "check_workspace_access",
        AsyncMock(side_effect=_unexpected_workspace_access_check),
    )
    monkeypatch.setattr(blackboard, "_enforce_agent_blackboard_topology", AsyncMock())
    update_blackboard = AsyncMock(return_value=_Dump({"id": "bb-1", "content": "updated"}))
    monkeypatch.setattr(workspaces.workspace_service, "update_blackboard", update_blackboard)

    response = await workspaces.update_blackboard(
        "ws-1",
        data=SimpleNamespace(),
        db=_WorkspaceAgentDb(has_agent=True),
        user=SimpleNamespace(id="user-1"),
    )

    assert response["code"] == 0
    assert response["data"]["content"] == "updated"
    workspaces.wm_service.check_workspace_access.assert_not_awaited()
    update_blackboard.assert_awaited_once()


async def test_user_auth_writes_workspace_blackboard_through_permission(monkeypatch, user_actor):
    check_access = AsyncMock()
    monkeypatch.setattr(workspaces.wm_service, "check_workspace_access", check_access)
    monkeypatch.setattr(blackboard, "_enforce_agent_blackboard_topology", AsyncMock())
    monkeypatch.setattr(
        workspaces.workspace_service,
        "update_blackboard",
        AsyncMock(return_value=_Dump({"id": "bb-1"})),
    )

    response = await workspaces.update_blackboard(
        "ws-1",
        data=SimpleNamespace(),
        db=_WorkspaceAgentDb(has_agent=False),
        user=SimpleNamespace(id="user-1"),
    )

    assert response["code"] == 0
    check_access.assert_awaited_once()


async def test_agent_auth_can_list_shared_files(monkeypatch, agent_actor):
    monkeypatch.setattr(
        workspaces.wm_service,
        "check_workspace_member",
        AsyncMock(side_effect=_unexpected_workspace_member_check),
    )
    monkeypatch.setattr(blackboard, "_enforce_agent_blackboard_topology", AsyncMock())
    list_shared_files = AsyncMock(return_value=[_Dump({"id": "shared-file-1"})])
    monkeypatch.setattr(blackboard.workspace_service, "list_shared_files", list_shared_files)

    response = await blackboard.list_files(
        "ws-1",
        parent_path="/",
        db=_WorkspaceAgentDb(has_agent=True),
        user=SimpleNamespace(id="user-1"),
    )

    assert response["code"] == 0
    assert response["data"][0]["id"] == "shared-file-1"
    workspaces.wm_service.check_workspace_member.assert_not_awaited()
    list_shared_files.assert_awaited_once()


async def test_agent_auth_can_write_shared_files(monkeypatch, agent_actor):
    monkeypatch.setattr(
        workspaces.wm_service,
        "check_workspace_access",
        AsyncMock(side_effect=_unexpected_workspace_access_check),
    )
    monkeypatch.setattr(blackboard, "_enforce_agent_blackboard_topology", AsyncMock())
    monkeypatch.setattr(blackboard, "_broadcast", lambda *_args, **_kwargs: None)
    create_shared_directory = AsyncMock(return_value=_Dump({"id": "dir-1"}))
    monkeypatch.setattr(blackboard.workspace_service, "create_shared_directory", create_shared_directory)

    response = await blackboard.mkdir(
        "ws-1",
        data=SimpleNamespace(),
        db=_WorkspaceAgentDb(has_agent=True),
        user=SimpleNamespace(id="user-1"),
    )

    assert response["code"] == 0
    assert response["data"]["id"] == "dir-1"
    workspaces.wm_service.check_workspace_access.assert_not_awaited()
    create_shared_directory.assert_awaited_once()


async def test_user_auth_reads_shared_files_through_workspace_member(monkeypatch, user_actor):
    check_member = AsyncMock()
    monkeypatch.setattr(workspaces.wm_service, "check_workspace_member", check_member)
    monkeypatch.setattr(blackboard, "_enforce_agent_blackboard_topology", AsyncMock())
    monkeypatch.setattr(blackboard.workspace_service, "list_shared_files", AsyncMock(return_value=[]))

    response = await blackboard.list_files(
        "ws-1",
        parent_path="/",
        db=_WorkspaceAgentDb(has_agent=False),
        user=SimpleNamespace(id="user-1"),
    )

    assert response["code"] == 0
    check_member.assert_awaited_once()


async def test_agent_auth_can_read_performance_without_workspace_member(monkeypatch, agent_actor):
    monkeypatch.setattr(
        workspaces.wm_service,
        "check_workspace_member",
        AsyncMock(side_effect=_unexpected_workspace_member_check),
    )

    response = await workspaces.collect_performance(
        "ws-1",
        db=_SequenceDb([_ScalarResult("workspace-agent-1"), _ScalarsResult([])]),
        user=SimpleNamespace(id="user-1"),
    )

    assert response["code"] == 0
    assert response["data"] == []
    workspaces.wm_service.check_workspace_member.assert_not_awaited()


async def test_user_auth_reads_performance_through_workspace_member(monkeypatch, user_actor):
    check_member = AsyncMock()
    monkeypatch.setattr(workspaces.wm_service, "check_workspace_member", check_member)

    response = await workspaces.collect_performance(
        "ws-1",
        db=_SequenceDb([_ScalarsResult([])]),
        user=SimpleNamespace(id="user-1"),
    )

    assert response["code"] == 0
    assert response["data"] == []
    check_member.assert_awaited_once()


async def test_agent_auth_can_read_members_without_workspace_member(monkeypatch, agent_actor):
    monkeypatch.setattr(
        workspaces.wm_service,
        "check_workspace_member",
        AsyncMock(side_effect=_unexpected_workspace_member_check),
    )
    list_workspace_members = AsyncMock(return_value=[_Dump({"user_id": "user-2"})])
    monkeypatch.setattr(workspaces.workspace_service, "list_workspace_members", list_workspace_members)

    response = await workspaces.list_members(
        "ws-1",
        db=_WorkspaceAgentDb(has_agent=True),
        user=SimpleNamespace(id="user-1"),
    )

    assert response["code"] == 0
    assert response["data"][0]["user_id"] == "user-2"
    workspaces.wm_service.check_workspace_member.assert_not_awaited()
    list_workspace_members.assert_awaited_once()


async def test_user_auth_reads_members_through_workspace_member(monkeypatch, user_actor):
    check_member = AsyncMock()
    monkeypatch.setattr(workspaces.wm_service, "check_workspace_member", check_member)
    list_workspace_members = AsyncMock(return_value=[])
    monkeypatch.setattr(workspaces.workspace_service, "list_workspace_members", list_workspace_members)

    response = await workspaces.list_members(
        "ws-1",
        db=_WorkspaceAgentDb(has_agent=False),
        user=SimpleNamespace(id="user-1"),
    )

    assert response["code"] == 0
    check_member.assert_awaited_once()
    list_workspace_members.assert_awaited_once()


async def test_agent_auth_can_read_topology_without_workspace_member(monkeypatch, agent_actor):
    monkeypatch.setattr(
        workspaces.wm_service,
        "check_workspace_member",
        AsyncMock(side_effect=_unexpected_workspace_member_check),
    )
    monkeypatch.setattr(corridors, "_check_workspace", AsyncMock(return_value=SimpleNamespace(id="ws-1")))
    monkeypatch.setattr(
        corridors.corridor_router,
        "get_topology",
        AsyncMock(return_value=SimpleNamespace(nodes=[], edges=[])),
    )

    response = await corridors.get_topology(
        "ws-1",
        org_ctx=(SimpleNamespace(id="user-1"), SimpleNamespace(id="org-1")),
        db=_WorkspaceAgentDb(has_agent=True),
    )

    assert response["code"] == 0
    assert response["data"]["nodes"] == []
    workspaces.wm_service.check_workspace_member.assert_not_awaited()


async def test_user_auth_reads_topology_through_workspace_member(monkeypatch, user_actor):
    check_member = AsyncMock()
    monkeypatch.setattr(workspaces.wm_service, "check_workspace_member", check_member)
    monkeypatch.setattr(corridors, "_check_workspace", AsyncMock(return_value=SimpleNamespace(id="ws-1")))
    monkeypatch.setattr(
        corridors.corridor_router,
        "get_topology",
        AsyncMock(return_value=SimpleNamespace(nodes=[], edges=[])),
    )

    response = await corridors.get_topology(
        "ws-1",
        org_ctx=(SimpleNamespace(id="user-1"), SimpleNamespace(id="org-1")),
        db=_WorkspaceAgentDb(has_agent=False),
    )

    assert response["code"] == 0
    check_member.assert_awaited_once()
