"""Corridor API — CRUD for corridor hexes, connections, human hex placement, and topology."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.models.base import not_deleted
from app.models.corridor import CorridorHex, HexConnection, is_adjacent, ordered_pair
from app.models.instance import Instance
from app.models.workspace_member import WorkspaceMember
from app.services import corridor_router

logger = logging.getLogger(__name__)
router = APIRouter()


def _ok(data=None, message: str = "success"):
    return {"code": 0, "message": message, "data": data}


def _error(status_code: int, error_code: int, message_key: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error_code": error_code, "message_key": message_key, "message": message},
    )


def _get_current_user_dep():
    from app.core.security import get_current_user
    return get_current_user


async def _is_position_occupied(db: AsyncSession, workspace_id: str, q: int, r: int) -> bool:
    if (q, r) == (0, 0):
        return True

    agent = await db.execute(
        select(Instance.id).where(and_(
            Instance.workspace_id == workspace_id, not_deleted(Instance),
            Instance.hex_position_q == q, Instance.hex_position_r == r,
        )).limit(1)
    )
    if agent.scalar_one_or_none():
        return True

    corridor = await db.execute(
        select(CorridorHex.id).where(and_(
            CorridorHex.workspace_id == workspace_id, not_deleted(CorridorHex),
            CorridorHex.hex_q == q, CorridorHex.hex_r == r,
        )).limit(1)
    )
    if corridor.scalar_one_or_none():
        return True

    human = await db.execute(
        select(WorkspaceMember.id).where(and_(
            WorkspaceMember.workspace_id == workspace_id, not_deleted(WorkspaceMember),
            WorkspaceMember.hex_q == q, WorkspaceMember.hex_r == r,
        )).limit(1)
    )
    return human.scalar_one_or_none() is not None


ADJACENT_OFFSETS = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, -1), (-1, 1)]


async def _auto_connect_corridor(db: AsyncSession, workspace_id: str, q: int, r: int, user_id: str):
    """Create automatic bidirectional connections to all adjacent occupied hexes."""
    for dq, dr in ADJACENT_OFFSETS:
        nq, nr = q + dq, r + dr
        if await _is_position_occupied(db, workspace_id, nq, nr):
            aq, ar, bq, br = ordered_pair(q, r, nq, nr)
            existing = await db.execute(
                select(HexConnection.id).where(and_(
                    HexConnection.workspace_id == workspace_id, not_deleted(HexConnection),
                    HexConnection.hex_a_q == aq, HexConnection.hex_a_r == ar,
                    HexConnection.hex_b_q == bq, HexConnection.hex_b_r == br,
                )).limit(1)
            )
            if existing.scalar_one_or_none() is None:
                conn = HexConnection(
                    workspace_id=workspace_id,
                    hex_a_q=aq, hex_a_r=ar, hex_b_q=bq, hex_b_r=br,
                    direction="both", auto_created=True, created_by=user_id,
                )
                db.add(conn)


# ── Corridor Hex CRUD ────────────────────────────────


class CorridorHexCreate(BaseModel):
    hex_q: int
    hex_r: int
    display_name: str = ""


class CorridorHexUpdate(BaseModel):
    display_name: str


@router.post("/{workspace_id}/corridor-hexes")
async def create_corridor_hex(
    workspace_id: str, data: CorridorHexCreate,
    db: AsyncSession = Depends(get_db), user=Depends(_get_current_user_dep()),
):
    if await _is_position_occupied(db, workspace_id, data.hex_q, data.hex_r):
        raise _error(409, 40901, "errors.corridor.position_occupied", "该位置已被占用")

    ch = CorridorHex(
        workspace_id=workspace_id, hex_q=data.hex_q, hex_r=data.hex_r,
        display_name=data.display_name, created_by=user.id,
    )
    db.add(ch)
    await _auto_connect_corridor(db, workspace_id, data.hex_q, data.hex_r, user.id)
    await db.commit()
    await db.refresh(ch)

    from app.api.workspaces import broadcast_event
    broadcast_event(workspace_id, "corridor:hex_placed", {
        "id": ch.id, "hex_q": ch.hex_q, "hex_r": ch.hex_r, "display_name": ch.display_name,
    })

    return _ok({"id": ch.id, "hex_q": ch.hex_q, "hex_r": ch.hex_r, "display_name": ch.display_name})


@router.get("/{workspace_id}/corridor-hexes")
async def list_corridor_hexes(
    workspace_id: str, db: AsyncSession = Depends(get_db), user=Depends(_get_current_user_dep()),
):
    result = await db.execute(
        select(CorridorHex).where(
            and_(CorridorHex.workspace_id == workspace_id, not_deleted(CorridorHex))
        )
    )
    items = [
        {"id": ch.id, "hex_q": ch.hex_q, "hex_r": ch.hex_r, "display_name": ch.display_name}
        for ch in result.scalars().all()
    ]
    return _ok(items)


@router.put("/{workspace_id}/corridor-hexes/{hex_id}")
async def update_corridor_hex(
    workspace_id: str, hex_id: str, data: CorridorHexUpdate,
    db: AsyncSession = Depends(get_db), user=Depends(_get_current_user_dep()),
):
    ch = await db.get(CorridorHex, hex_id)
    if not ch or ch.workspace_id != workspace_id or ch.deleted_at is not None:
        raise _error(404, 40402, "errors.corridor.not_found", "过道 Hex 不存在")
    ch.display_name = data.display_name
    await db.commit()
    return _ok({"id": ch.id, "display_name": ch.display_name})


@router.delete("/{workspace_id}/corridor-hexes/{hex_id}")
async def delete_corridor_hex(
    workspace_id: str, hex_id: str,
    db: AsyncSession = Depends(get_db), user=Depends(_get_current_user_dep()),
):
    ch = await db.get(CorridorHex, hex_id)
    if not ch or ch.workspace_id != workspace_id or ch.deleted_at is not None:
        raise _error(404, 40402, "errors.corridor.not_found", "过道 Hex 不存在")

    conns = await db.execute(
        select(HexConnection).where(and_(
            HexConnection.workspace_id == workspace_id, not_deleted(HexConnection),
            HexConnection.auto_created.is_(True),
        ))
    )
    for conn in conns.scalars().all():
        if (conn.hex_a_q == ch.hex_q and conn.hex_a_r == ch.hex_r) or \
           (conn.hex_b_q == ch.hex_q and conn.hex_b_r == ch.hex_r):
            conn.soft_delete()

    ch.soft_delete()
    await db.commit()

    from app.api.workspaces import broadcast_event
    broadcast_event(workspace_id, "corridor:hex_removed", {"id": hex_id})

    return _ok()


# ── Connection CRUD ──────────────────────────────────


class ConnectionCreate(BaseModel):
    hex_a_q: int
    hex_a_r: int
    hex_b_q: int
    hex_b_r: int
    direction: str = Field(default="both", pattern="^(both|a_to_b|b_to_a)$")


class ConnectionUpdate(BaseModel):
    direction: str = Field(pattern="^(both|a_to_b|b_to_a)$")


@router.post("/{workspace_id}/connections")
async def create_connection(
    workspace_id: str, data: ConnectionCreate,
    db: AsyncSession = Depends(get_db), user=Depends(_get_current_user_dep()),
):
    if not is_adjacent(data.hex_a_q, data.hex_a_r, data.hex_b_q, data.hex_b_r):
        raise _error(400, 40001, "errors.connection.not_adjacent", "只能连接相邻的 Hex")

    if not await _is_position_occupied(db, workspace_id, data.hex_a_q, data.hex_a_r):
        raise _error(400, 40002, "errors.connection.position_empty", "端点 A 位置为空")
    if not await _is_position_occupied(db, workspace_id, data.hex_b_q, data.hex_b_r):
        raise _error(400, 40003, "errors.connection.position_empty", "端点 B 位置为空")

    aq, ar, bq, br = ordered_pair(data.hex_a_q, data.hex_a_r, data.hex_b_q, data.hex_b_r)

    existing = await db.execute(
        select(HexConnection).where(and_(
            HexConnection.workspace_id == workspace_id, not_deleted(HexConnection),
            HexConnection.hex_a_q == aq, HexConnection.hex_a_r == ar,
            HexConnection.hex_b_q == bq, HexConnection.hex_b_r == br,
        )).limit(1)
    )
    if existing.scalar_one_or_none():
        raise _error(409, 40902, "errors.connection.already_exists", "该连接已存在")

    need_swap = (aq, ar) != (data.hex_a_q, data.hex_a_r)
    direction = data.direction
    if need_swap and direction == "a_to_b":
        direction = "b_to_a"
    elif need_swap and direction == "b_to_a":
        direction = "a_to_b"

    conn = HexConnection(
        workspace_id=workspace_id,
        hex_a_q=aq, hex_a_r=ar, hex_b_q=bq, hex_b_r=br,
        direction=direction, auto_created=False, created_by=user.id,
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)

    from app.api.workspaces import broadcast_event
    broadcast_event(workspace_id, "connection:created", {
        "id": conn.id, "hex_a_q": aq, "hex_a_r": ar, "hex_b_q": bq, "hex_b_r": br,
        "direction": conn.direction,
    })

    return _ok({
        "id": conn.id, "hex_a_q": aq, "hex_a_r": ar, "hex_b_q": bq, "hex_b_r": br,
        "direction": conn.direction,
    })


@router.get("/{workspace_id}/connections")
async def list_connections(
    workspace_id: str, db: AsyncSession = Depends(get_db), user=Depends(_get_current_user_dep()),
):
    result = await db.execute(
        select(HexConnection).where(
            and_(HexConnection.workspace_id == workspace_id, not_deleted(HexConnection))
        )
    )
    items = [
        {
            "id": c.id, "hex_a_q": c.hex_a_q, "hex_a_r": c.hex_a_r,
            "hex_b_q": c.hex_b_q, "hex_b_r": c.hex_b_r,
            "direction": c.direction, "auto_created": c.auto_created,
        }
        for c in result.scalars().all()
    ]
    return _ok(items)


@router.put("/{workspace_id}/connections/{conn_id}")
async def update_connection(
    workspace_id: str, conn_id: str, data: ConnectionUpdate,
    db: AsyncSession = Depends(get_db), user=Depends(_get_current_user_dep()),
):
    conn = await db.get(HexConnection, conn_id)
    if not conn or conn.workspace_id != workspace_id or conn.deleted_at is not None:
        raise _error(404, 40403, "errors.connection.not_found", "连接不存在")
    conn.direction = data.direction
    await db.commit()

    from app.api.workspaces import broadcast_event
    broadcast_event(workspace_id, "connection:updated", {"id": conn_id, "direction": data.direction})

    return _ok({"id": conn_id, "direction": data.direction})


@router.delete("/{workspace_id}/connections/{conn_id}")
async def delete_connection(
    workspace_id: str, conn_id: str,
    db: AsyncSession = Depends(get_db), user=Depends(_get_current_user_dep()),
):
    conn = await db.get(HexConnection, conn_id)
    if not conn or conn.workspace_id != workspace_id or conn.deleted_at is not None:
        raise _error(404, 40403, "errors.connection.not_found", "连接不存在")
    conn.soft_delete()
    await db.commit()

    from app.api.workspaces import broadcast_event
    broadcast_event(workspace_id, "connection:removed", {"id": conn_id})

    return _ok()


# ── Human Hex Management ─────────────────────────────


class HumanHexPlacement(BaseModel):
    hex_q: int
    hex_r: int


class HumanChannelConfig(BaseModel):
    channel_type: str = Field(pattern="^(feishu|slack|email)$")
    channel_config: dict


@router.put("/{workspace_id}/members/{user_id}/hex")
async def place_human_hex(
    workspace_id: str, user_id: str, data: HumanHexPlacement,
    db: AsyncSession = Depends(get_db), user=Depends(_get_current_user_dep()),
):
    member_q = await db.execute(
        select(WorkspaceMember).where(and_(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            not_deleted(WorkspaceMember),
        ))
    )
    member = member_q.scalar_one_or_none()
    if not member:
        raise _error(404, 40404, "errors.member.not_found", "成员不存在")

    if await _is_position_occupied(db, workspace_id, data.hex_q, data.hex_r):
        raise _error(409, 40903, "errors.human_hex.position_occupied", "该位置已被占用")

    member.hex_q = data.hex_q
    member.hex_r = data.hex_r
    await db.commit()

    from app.api.workspaces import broadcast_event
    broadcast_event(workspace_id, "human:hex_placed", {
        "user_id": user_id, "hex_q": data.hex_q, "hex_r": data.hex_r,
    })

    return _ok({"user_id": user_id, "hex_q": data.hex_q, "hex_r": data.hex_r})


@router.delete("/{workspace_id}/members/{user_id}/hex")
async def remove_human_hex(
    workspace_id: str, user_id: str,
    db: AsyncSession = Depends(get_db), user=Depends(_get_current_user_dep()),
):
    member_q = await db.execute(
        select(WorkspaceMember).where(and_(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            not_deleted(WorkspaceMember),
        ))
    )
    member = member_q.scalar_one_or_none()
    if not member:
        raise _error(404, 40404, "errors.member.not_found", "成员不存在")

    member.hex_q = None
    member.hex_r = None
    await db.commit()

    from app.api.workspaces import broadcast_event
    broadcast_event(workspace_id, "human:hex_removed", {"user_id": user_id})

    return _ok()


@router.put("/{workspace_id}/members/{user_id}/channel")
async def update_human_channel(
    workspace_id: str, user_id: str, data: HumanChannelConfig,
    db: AsyncSession = Depends(get_db), user=Depends(_get_current_user_dep()),
):
    member_q = await db.execute(
        select(WorkspaceMember).where(and_(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            not_deleted(WorkspaceMember),
        ))
    )
    member = member_q.scalar_one_or_none()
    if not member:
        raise _error(404, 40404, "errors.member.not_found", "成员不存在")

    member.channel_type = data.channel_type
    member.channel_config = json.dumps(data.channel_config)
    await db.commit()

    from app.api.workspaces import broadcast_event
    broadcast_event(workspace_id, "human:channel_updated", {
        "user_id": user_id, "channel_type": data.channel_type,
    })

    return _ok({"user_id": user_id, "channel_type": data.channel_type})


# ── Topology Query ───────────────────────────────────


@router.get("/{workspace_id}/topology")
async def get_topology(
    workspace_id: str, db: AsyncSession = Depends(get_db), user=Depends(_get_current_user_dep()),
):
    topo = await corridor_router.get_topology(db, workspace_id)
    return _ok({
        "nodes": [
            {"q": n.q, "r": n.r, "type": n.node_type, "entity_id": n.entity_id, "display_name": n.display_name}
            for n in topo.nodes
        ],
        "edges": [
            {
                "id": e.connection_id, "a_q": e.a_q, "a_r": e.a_r,
                "b_q": e.b_q, "b_r": e.b_r, "direction": e.direction, "auto_created": e.auto_created,
            }
            for e in topo.edges
        ],
    })
