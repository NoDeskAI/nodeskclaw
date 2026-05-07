from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api import trust
from app.core.security import AuthActor, _auth_actor


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


class _SequenceDb:
    def __init__(self, results: list) -> None:
        self._results = list(results)
        self.statements = []
        self.added = []
        self.commits = 0

    async def execute(self, stmt):
        self.statements.append(stmt)
        if not self._results:
            raise AssertionError("unexpected database execute")
        return self._results.pop(0)

    def add(self, item) -> None:
        self.added.append(item)

    async def commit(self) -> None:
        self.commits += 1


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


def _org_ctx():
    return SimpleNamespace(id="user-1"), SimpleNamespace(id="org-1")


def _workspace():
    return SimpleNamespace(id="ws-1", name="Office")


def _decision(agent_id: str):
    return SimpleNamespace(
        id=f"decision-{agent_id}",
        workspace_id="ws-1",
        agent_instance_id=agent_id,
        decision_type="deploy",
        context_summary="Deploy request",
        proposal={"kind": "deployment"},
        outcome="pending",
        reviewer_id=None,
        review_type=None,
        review_comment=None,
        resolved_at=None,
        created_at=None,
    )


def _compiled_param_values(stmt) -> set:
    return set(stmt.compile().params.values())


async def test_agent_check_trust_rejects_other_agent(agent_actor):
    db = _SequenceDb([
        _ScalarResult(_workspace()),
        _ScalarResult("workspace-agent-1"),
    ])

    with pytest.raises(HTTPException) as exc:
        await trust.check_trust(
            "ws-1",
            "inst-2",
            "deploy",
            org_ctx=_org_ctx(),
            db=db,
        )

    assert exc.value.status_code == 403
    assert exc.value.detail["message_key"] == "errors.collaboration.agent_scope_forbidden"


async def test_agent_check_trust_requires_workspace_agent(agent_actor):
    db = _SequenceDb([
        _ScalarResult(_workspace()),
        _ScalarResult(None),
    ])

    with pytest.raises(HTTPException) as exc:
        await trust.check_trust(
            "ws-1",
            "inst-1",
            "deploy",
            org_ctx=_org_ctx(),
            db=db,
        )

    assert exc.value.status_code == 403
    assert exc.value.detail["message_key"] == "errors.workspace.agent_not_in_workspace"


async def test_agent_submit_approval_rejects_other_agent(agent_actor):
    db = _SequenceDb([
        _ScalarResult(_workspace()),
        _ScalarResult("workspace-agent-1"),
    ])
    body = trust.ApprovalRequest(
        workspace_id="ws-1",
        agent_instance_id="inst-2",
        action_type="deploy",
        proposal={"kind": "deployment"},
    )

    with pytest.raises(HTTPException) as exc:
        await trust.submit_approval_request(body, org_ctx=_org_ctx(), db=db)

    assert exc.value.status_code == 403
    assert exc.value.detail["message_key"] == "errors.collaboration.agent_scope_forbidden"
    assert db.added == []
    assert db.commits == 0


async def test_agent_list_decisions_rejects_other_agent(agent_actor):
    db = _SequenceDb([
        _ScalarResult(_workspace()),
        _ScalarResult("workspace-agent-1"),
    ])

    with pytest.raises(HTTPException) as exc:
        await trust.list_decision_records(
            "ws-1",
            agent_id="inst-2",
            decision_type=None,
            org_ctx=_org_ctx(),
            db=db,
        )

    assert exc.value.status_code == 403
    assert exc.value.detail["message_key"] == "errors.collaboration.agent_scope_forbidden"


async def test_agent_list_decisions_without_agent_id_filters_to_self(agent_actor):
    db = _SequenceDb([
        _ScalarResult(_workspace()),
        _ScalarResult("workspace-agent-1"),
        _ScalarsResult([_decision("inst-1")]),
    ])

    response = await trust.list_decision_records(
        "ws-1",
        agent_id=None,
        decision_type=None,
        org_ctx=_org_ctx(),
        db=db,
    )

    assert response["code"] == 0
    assert response["data"][0]["agent_instance_id"] == "inst-1"
    assert "inst-1" in _compiled_param_values(db.statements[-1])


async def test_user_check_trust_uses_requested_agent(user_actor):
    db = _SequenceDb([
        _ScalarResult(_workspace()),
        _ScalarResult(SimpleNamespace(id="policy-1")),
    ])

    response = await trust.check_trust(
        "ws-1",
        "inst-2",
        "deploy",
        org_ctx=_org_ctx(),
        db=db,
    )

    assert response == {"code": 0, "message": "success", "data": {"trusted": True}}
    assert "inst-2" in _compiled_param_values(db.statements[-1])


async def test_user_list_decisions_without_agent_id_keeps_workspace_scope(user_actor):
    db = _SequenceDb([
        _ScalarResult(_workspace()),
        _ScalarsResult([_decision("inst-1"), _decision("inst-2")]),
    ])

    response = await trust.list_decision_records(
        "ws-1",
        agent_id=None,
        decision_type=None,
        org_ctx=_org_ctx(),
        db=db,
    )

    assert response["code"] == 0
    assert [item["agent_instance_id"] for item in response["data"]] == ["inst-1", "inst-2"]
    params = _compiled_param_values(db.statements[-1])
    assert "inst-1" not in params
    assert "inst-2" not in params


async def test_user_submit_approval_keeps_requested_agent(monkeypatch, user_actor):
    from app.services import corridor_router

    db = _SequenceDb([_ScalarResult(_workspace())])
    monkeypatch.setattr(corridor_router, "has_any_connections", AsyncMock(return_value=False))
    body = trust.ApprovalRequest(
        workspace_id="ws-1",
        agent_instance_id="inst-2",
        action_type="deploy",
        proposal={"kind": "deployment"},
    )

    response = await trust.submit_approval_request(body, org_ctx=_org_ctx(), db=db)

    assert response["code"] == 0
    assert response["data"]["status"] == "no_topology"
    corridor_router.has_any_connections.assert_awaited_once()
