"""SSE Connection Registry — tracks active SSE connections across backend instances.

Cross-instance push flow:
  - Local: direct push via in-memory lookup
  - Remote: PG NOTIFY('sse_push:{backend_instance_id}', payload) forwarding
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import not_deleted
from app.models.sse_connection import SSEConnection

logger = logging.getLogger(__name__)

BACKEND_INSTANCE_ID = os.environ.get("BACKEND_INSTANCE_ID", str(uuid.uuid4())[:8])

HEARTBEAT_INTERVAL_S = 15
HEARTBEAT_TIMEOUT_S = 60


async def register_connection(
    db: AsyncSession,
    *,
    connection_id: str,
    instance_id: str,
    target_type: str,
    target_id: str,
    workspace_id: str | None = None,
) -> SSEConnection:
    conn = SSEConnection(
        connection_id=connection_id,
        instance_id=instance_id,
        backend_instance_id=BACKEND_INSTANCE_ID,
        target_type=target_type,
        target_id=target_id,
        workspace_id=workspace_id,
    )
    db.add(conn)
    await db.flush()
    logger.info(
        "SSE connection registered: conn=%s instance=%s target=%s:%s backend=%s",
        connection_id, instance_id, target_type, target_id, BACKEND_INSTANCE_ID,
    )
    return conn


async def unregister_connection(db: AsyncSession, connection_id: str) -> None:
    result = await db.execute(
        select(SSEConnection).where(
            SSEConnection.connection_id == connection_id,
            not_deleted(SSEConnection),
        )
    )
    conn = result.scalar_one_or_none()
    if conn:
        conn.soft_delete()
        await db.flush()
        logger.info("SSE connection unregistered: %s", connection_id)


async def heartbeat(db: AsyncSession, connection_id: str) -> None:
    await db.execute(
        update(SSEConnection)
        .where(
            SSEConnection.connection_id == connection_id,
            not_deleted(SSEConnection),
        )
        .values(last_heartbeat=datetime.now(timezone.utc))
    )


async def get_connections_for_target(
    db: AsyncSession,
    target_type: str,
    target_id: str,
) -> list[SSEConnection]:
    result = await db.execute(
        select(SSEConnection).where(
            SSEConnection.target_type == target_type,
            SSEConnection.target_id == target_id,
            not_deleted(SSEConnection),
        )
    )
    return list(result.scalars().all())


async def get_connections_for_workspace(
    db: AsyncSession,
    workspace_id: str,
) -> list[SSEConnection]:
    result = await db.execute(
        select(SSEConnection).where(
            SSEConnection.workspace_id == workspace_id,
            not_deleted(SSEConnection),
        )
    )
    return list(result.scalars().all())


async def get_local_connections(db: AsyncSession) -> list[SSEConnection]:
    result = await db.execute(
        select(SSEConnection).where(
            SSEConnection.backend_instance_id == BACKEND_INSTANCE_ID,
            not_deleted(SSEConnection),
        )
    )
    return list(result.scalars().all())


async def is_local_connection(db: AsyncSession, connection_id: str) -> bool:
    result = await db.execute(
        select(SSEConnection.backend_instance_id).where(
            SSEConnection.connection_id == connection_id,
            not_deleted(SSEConnection),
        )
    )
    backend_id = result.scalar_one_or_none()
    return backend_id == BACKEND_INSTANCE_ID


async def cleanup_stale_connections(db: AsyncSession) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=HEARTBEAT_TIMEOUT_S)
    result = await db.execute(
        select(SSEConnection).where(
            SSEConnection.last_heartbeat < cutoff,
            not_deleted(SSEConnection),
        )
    )
    stale = result.scalars().all()
    count = 0
    for conn in stale:
        conn.soft_delete()
        count += 1
    if count:
        await db.flush()
        logger.warning("Cleaned up %d stale SSE connections (heartbeat timeout)", count)
    return count


async def get_remote_instances_for_workspace(
    db: AsyncSession,
    workspace_id: str,
    *,
    exclude_self: bool = True,
) -> list[str]:
    """Return distinct backend_instance_ids that have SSE connections for a workspace, excluding self."""
    from sqlalchemy import distinct

    stmt = select(distinct(SSEConnection.backend_instance_id)).where(
        SSEConnection.workspace_id == workspace_id,
        not_deleted(SSEConnection),
    )
    if exclude_self:
        stmt = stmt.where(SSEConnection.backend_instance_id != BACKEND_INSTANCE_ID)

    result = await db.execute(stmt)
    return [row[0] for row in result.all()]


async def cleanup_backend_connections(db: AsyncSession, backend_id: str | None = None) -> int:
    """Remove all connections belonging to a specific backend instance (e.g. on shutdown)."""
    bid = backend_id or BACKEND_INSTANCE_ID
    result = await db.execute(
        select(SSEConnection).where(
            SSEConnection.backend_instance_id == bid,
            not_deleted(SSEConnection),
        )
    )
    conns = result.scalars().all()
    count = 0
    for conn in conns:
        conn.soft_delete()
        count += 1
    if count:
        await db.flush()
        logger.info("Cleaned up %d SSE connections for backend %s", count, bid)
    return count
