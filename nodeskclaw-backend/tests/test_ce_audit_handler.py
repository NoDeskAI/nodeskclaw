"""CE 审计 handler 单元测试 — 验证只记录 user 操作，跳过 agent/org。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.audit_handler import _on_operation_audit


@pytest.fixture(autouse=True)
def _reset_audited():
    from app.core import hooks
    hooks.reset_audited()
    yield
    hooks.reset_audited()


@pytest.mark.asyncio
async def test_user_operation_is_persisted():
    """actor_type=user 应该写入数据库。"""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.audit_handler.async_session_factory", return_value=mock_session), \
         patch("app.services.audit_handler.get_auth_actor", return_value=None):
        await _on_operation_audit(
            action="instance.create",
            target_type="instance",
            target_id="inst-001",
            actor_id="user-001",
            actor_type="user",
            org_id="org-001",
        )

    mock_session.add.assert_called_once()
    mock_session.commit.assert_awaited_once()

    audit_obj = mock_session.add.call_args[0][0]
    assert audit_obj.action == "instance.create"
    assert audit_obj.actor_type == "user"
    assert audit_obj.actor_id == "user-001"


@pytest.mark.asyncio
async def test_agent_operation_is_skipped():
    """actor_type=agent 应该被跳过，不写入数据库。"""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.audit_handler.async_session_factory", return_value=mock_session):
        await _on_operation_audit(
            action="agent.message_sent",
            target_type="workspace",
            target_id="ws-001",
            actor_id="agent-001",
            actor_type="agent",
        )

    mock_session.add.assert_not_called()
    mock_session.commit.assert_not_awaited()

    from app.core.hooks import is_audited
    assert is_audited() is True


@pytest.mark.asyncio
async def test_org_operation_is_skipped():
    """actor_type=org 应该被跳过，不写入数据库。"""
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.audit_handler.async_session_factory", return_value=mock_session):
        await _on_operation_audit(
            action="org.update_settings",
            target_type="organization",
            target_id="org-001",
            actor_id="org-001",
            actor_type="org",
        )

    mock_session.add.assert_not_called()
    mock_session.commit.assert_not_awaited()

    from app.core.hooks import is_audited
    assert is_audited() is True
