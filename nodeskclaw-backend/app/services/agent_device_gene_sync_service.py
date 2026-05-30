"""Hook registration for Agent Device Gene synchronization."""

from __future__ import annotations

import logging

from app.core import hooks
from app.core.deps import async_session_factory
from app.services.agent_device_service import sync_workspace_device_genes

logger = logging.getLogger(__name__)


async def _on_topology_change(*, workspace_id: str, action: str = "topology_change", **_kwargs) -> None:
    if not workspace_id:
        return
    try:
        async with async_session_factory() as db:
            await sync_workspace_device_genes(db, workspace_id=workspace_id, reason=action)
            await db.commit()
    except Exception as exc:
        logger.warning("Agent Device Gene 拓扑同步失败 workspace=%s action=%s err=%s", workspace_id, action, exc)


def register_agent_device_gene_sync_hooks() -> None:
    hooks.register("topology_change", _on_topology_change)
    logger.info("Agent Device Gene 同步 hook 已注册")
