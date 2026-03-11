"""CE 操作审计 handler — 监听 operation_audit 事件，只写 actor_type=user 的记录。

EE 模式下此 handler 不会注册（由 EE 自己的 handler 接管）。
"""

from __future__ import annotations

import logging
import uuid

from app.core import hooks
from app.core.deps import async_session_factory
from app.core.security import get_auth_actor
from app.models.operation_audit_log import OperationAuditLog

logger = logging.getLogger(__name__)


async def _on_operation_audit(
    *,
    action: str,
    target_type: str,
    target_id: str,
    actor_id: str,
    actor_type: str = "user",
    actor_name: str | None = None,
    org_id: str | None = None,
    workspace_id: str | None = None,
    details: dict | None = None,
    **_kwargs,
) -> None:
    if actor_type != "user":
        hooks.mark_audited()
        return

    if actor_name is None:
        ctx = get_auth_actor()
        if ctx:
            actor_name = ctx.actor_name

    try:
        async with async_session_factory() as session:
            audit = OperationAuditLog(
                id=str(uuid.uuid4()),
                org_id=org_id,
                workspace_id=workspace_id,
                action=action[:255],
                target_type=target_type[:32],
                target_id=str(target_id)[:36],
                actor_type=actor_type[:16],
                actor_id=str(actor_id)[:36],
                actor_name=actor_name[:128] if actor_name else None,
                details=details,
            )
            session.add(audit)
            await session.commit()
    except Exception:
        logger.exception("CE audit handler write failed: action=%s target=%s/%s", action, target_type, target_id)
    finally:
        hooks.mark_audited()


def register_ce_audit_handler() -> None:
    hooks.register("operation_audit", _on_operation_audit)
    logger.info("CE 操作审计 handler 已注册（仅记录 user 操作）")
