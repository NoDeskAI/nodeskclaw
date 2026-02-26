"""MCP Server management API — CRUD for instance-level MCP configurations."""

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_org, get_db
from app.models.base import not_deleted
from app.models.instance import Instance
from app.models.instance_mcp_server import InstanceMcpServer
from app.schemas.mcp import McpServerCreate, McpServerInfo, McpServerUpdate

logger = logging.getLogger(__name__)
router = APIRouter()


async def sync_mcp_to_openclaw(instance_id: str, db: AsyncSession) -> None:
    """Sync all active MCP server configs to the instance's openclaw.json via NFS."""
    from app.services.nfs_mount import nfs_mount
    from app.services.llm_config_service import _read_config_file, _write_config_file

    result = await db.execute(
        select(InstanceMcpServer).where(
            InstanceMcpServer.instance_id == instance_id,
            InstanceMcpServer.is_active == True,
            not_deleted(InstanceMcpServer),
        )
    )
    mcp_config: dict = {}
    for s in result.scalars().all():
        entry: dict = {}
        if s.transport == "stdio":
            entry["command"] = s.command
            if s.args:
                entry["args"] = s.args
        else:
            entry["url"] = s.url
        if s.env:
            entry["env"] = s.env
        mcp_config[s.name] = entry

    instance = await db.get(Instance, instance_id)
    if not instance:
        return
    try:
        async with nfs_mount(instance, db) as mount_path:
            try:
                existing = _read_config_file(mount_path)
            except ValueError as e:
                logger.warning("sync_mcp_to_openclaw: openclaw.json parse error: %s", e)
                return
            if existing is None:
                existing = {}
            existing["mcpServers"] = mcp_config
            _write_config_file(mount_path, existing)
        logger.info("Synced %d MCP servers to openclaw.json: instance=%s", len(mcp_config), instance.name)
    except Exception as e:
        logger.warning("sync_mcp_to_openclaw failed for %s: %s", instance_id, e)


def _ok(data=None, message: str = "success"):
    return {"code": 0, "message": message, "data": data}


def _mcp_to_info(m: InstanceMcpServer) -> dict:
    return McpServerInfo(
        id=m.id, instance_id=m.instance_id, name=m.name,
        transport=m.transport, command=m.command, url=m.url,
        args=m.args, env=m.env, is_active=m.is_active,
        source=m.source, source_gene_id=m.source_gene_id,
        created_at=m.created_at,
    ).model_dump()


@router.get("/{instance_id}/mcp-servers")
async def list_mcp_servers(
    instance_id: str,
    org: dict = Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InstanceMcpServer).where(
            InstanceMcpServer.instance_id == instance_id,
            not_deleted(InstanceMcpServer),
        )
    )
    items = [_mcp_to_info(m) for m in result.scalars().all()]
    return _ok(items)


@router.post("/{instance_id}/mcp-servers")
async def create_mcp_server(
    instance_id: str, body: McpServerCreate,
    org: dict = Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    inst_q = await db.execute(
        select(Instance).where(Instance.id == instance_id, not_deleted(Instance))
    )
    if not inst_q.scalar_one_or_none():
        raise HTTPException(404, "instance not found")

    mcp = InstanceMcpServer(
        id=str(uuid.uuid4()),
        instance_id=instance_id,
        name=body.name,
        transport=body.transport,
        command=body.command,
        url=body.url,
        args=body.args,
        env=body.env,
    )
    db.add(mcp)
    await db.commit()
    await db.refresh(mcp)
    await sync_mcp_to_openclaw(instance_id, db)
    return _ok(_mcp_to_info(mcp))


@router.put("/{instance_id}/mcp-servers/{mcp_id}")
async def update_mcp_server(
    instance_id: str, mcp_id: str, body: McpServerUpdate,
    org: dict = Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InstanceMcpServer).where(
            InstanceMcpServer.id == mcp_id,
            InstanceMcpServer.instance_id == instance_id,
            not_deleted(InstanceMcpServer),
        )
    )
    mcp = result.scalar_one_or_none()
    if not mcp:
        raise HTTPException(404, "mcp server not found")
    for field in ("name", "transport", "command", "url", "args", "env", "is_active"):
        val = getattr(body, field, None)
        if val is not None:
            setattr(mcp, field, val)
    await db.commit()
    await sync_mcp_to_openclaw(instance_id, db)
    return _ok(_mcp_to_info(mcp))


@router.delete("/{instance_id}/mcp-servers/{mcp_id}")
async def delete_mcp_server(
    instance_id: str, mcp_id: str,
    org: dict = Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InstanceMcpServer).where(
            InstanceMcpServer.id == mcp_id,
            InstanceMcpServer.instance_id == instance_id,
            not_deleted(InstanceMcpServer),
        )
    )
    mcp = result.scalar_one_or_none()
    if not mcp:
        raise HTTPException(404, "mcp server not found")
    mcp.soft_delete()
    await db.commit()
    await sync_mcp_to_openclaw(instance_id, db)
    return _ok(message="deleted")
