"""Portal MCP Server management — with instance permission checks."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.security import get_current_user
from app.models.base import not_deleted
from app.models.instance import Instance
from app.models.instance_mcp_server import InstanceMcpServer
from app.models.instance_member import InstanceRole
from app.models.user import User
from app.schemas.mcp import McpServerCreate, McpServerInfo, McpServerUpdate
from app.services import instance_member_service

logger = logging.getLogger(__name__)
router = APIRouter()


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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await instance_member_service.check_instance_access(
        instance_id, current_user, InstanceRole.viewer, db
    )
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await instance_member_service.check_instance_access(
        instance_id, current_user, InstanceRole.editor, db
    )
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
    return _ok(_mcp_to_info(mcp))


@router.put("/{instance_id}/mcp-servers/{mcp_id}")
async def update_mcp_server(
    instance_id: str, mcp_id: str, body: McpServerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await instance_member_service.check_instance_access(
        instance_id, current_user, InstanceRole.editor, db
    )
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
    return _ok(_mcp_to_info(mcp))


@router.delete("/{instance_id}/mcp-servers/{mcp_id}")
async def delete_mcp_server(
    instance_id: str, mcp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await instance_member_service.check_instance_access(
        instance_id, current_user, InstanceRole.editor, db
    )
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
    return _ok(message="deleted")
