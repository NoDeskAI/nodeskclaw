"""Corridor API — CorridorHex CRUD, Connection CRUD, Human Hex, Topology query."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_org, get_db
from app.models.base import not_deleted
from app.models.corridor import CorridorHex, HexConnection, is_adjacent, ordered_pair
from app.models.instance import Instance
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.schemas.corridor import (
    ConnectionCreate,
    ConnectionInfo,
    ConnectionUpdate,
    CorridorHexCreate,
    CorridorHexInfo,
    CorridorHexUpdate,
    HumanChannelUpdate,
    HumanHexUpdate,
    TopologyEdgeInfo,
    TopologyInfo,
    TopologyNodeInfo,
)
from app.services import corridor_router

logger = logging.getLogger(__name__)
router = APIRouter()


def _ok(data=None, message: str = "success"):
    return {"code": 0, "message": message, "data": data}


async def _check_workspace(workspace_id: str, org: dict, db: AsyncSession) -> Workspace:
    result = await db.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.org_id == org["org_id"],
            not_deleted(Workspace),
        )
    )
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail="workspace not found")
    return ws


async def _is_hex_occupied(workspace_id: str, q: int, r: int, db: AsyncSession) -> bool:
    if (q, r) == (0, 0):
        return True
    agent_q = await db.execute(
        select(Instance.id).where(
            Instance.workspace_id == workspace_id,
            Instance.hex_position_q == q,
            Instance.hex_position_r == r,
            not_deleted(Instance),
        ).limit(1)
    )
    if agent_q.scalar_one_or_none():
        return True
    corridor_q = await db.execute(
        select(CorridorHex.id).where(
            CorridorHex.workspace_id == workspace_id,
            CorridorHex.hex_q == q,
            CorridorHex.hex_r == r,
            not_deleted(CorridorHex),
        ).limit(1)
    )
    if corridor_q.scalar_one_or_none():
        return True
    human_q = await db.execute(
        select(WorkspaceMember.id).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.hex_q == q,
            WorkspaceMember.hex_r == r,
            not_deleted(WorkspaceMember),
        ).limit(1)
    )
    if human_q.scalar_one_or_none():
        return True
    return False


# ── Corridor Hex CRUD ──────────────────────────────────

@router.post("/{workspace_id}/corridor-hexes")
async def create_corridor_hex(
    workspace_id: str, body: CorridorHexCreate,
    org: dict = Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    await _check_workspace(workspace_id, org, db)
    if await _is_hex_occupied(workspace_id, body.hex_q, body.hex_r, db):
        raise HTTPException(400, "hex position already occupied")

    ch = CorridorHex(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        hex_q=body.hex_q,
        hex_r=body.hex_r,
        display_name=body.display_name,
        created_by=org.get("user_id"),
    )
    db.add(ch)

    await _auto_connect_corridor(workspace_id, body.hex_q, body.hex_r, org.get("user_id"), db)

    await db.commit()
    await db.refresh(ch)
    return _ok(CorridorHexInfo(
        id=ch.id, workspace_id=ch.workspace_id,
        hex_q=ch.hex_q, hex_r=ch.hex_r,
        display_name=ch.display_name,
        created_by=ch.created_by, created_at=ch.created_at,
    ).model_dump())


async def _auto_connect_corridor(
    workspace_id: str, q: int, r: int, user_id: str | None, db: AsyncSession,
):
    """Auto-create bidirectional connections to all adjacent occupied hexes."""
    offsets = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, -1), (-1, 1)]
    for dq, dr in offsets:
        nq, nr = q + dq, r + dr
        if await _is_hex_occupied(workspace_id, nq, nr, db):
            aq, ar, bq, br = ordered_pair(q, r, nq, nr)
            existing = await db.execute(
                select(HexConnection.id).where(
                    HexConnection.workspace_id == workspace_id,
                    HexConnection.hex_a_q == aq, HexConnection.hex_a_r == ar,
                    HexConnection.hex_b_q == bq, HexConnection.hex_b_r == br,
                    not_deleted(HexConnection),
                ).limit(1)
            )
            if existing.scalar_one_or_none():
                continue
            conn = HexConnection(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                hex_a_q=aq, hex_a_r=ar, hex_b_q=bq, hex_b_r=br,
                direction="both", auto_created=True,
                created_by=user_id,
            )
            db.add(conn)


@router.get("/{workspace_id}/corridor-hexes")
async def list_corridor_hexes(
    workspace_id: str,
    org: dict = Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    await _check_workspace(workspace_id, org, db)
    result = await db.execute(
        select(CorridorHex).where(
            CorridorHex.workspace_id == workspace_id,
            not_deleted(CorridorHex),
        )
    )
    items = [
        CorridorHexInfo(
            id=c.id, workspace_id=c.workspace_id,
            hex_q=c.hex_q, hex_r=c.hex_r,
            display_name=c.display_name,
            created_by=c.created_by, created_at=c.created_at,
        ).model_dump()
        for c in result.scalars().all()
    ]
    return _ok(items)


@router.put("/{workspace_id}/corridor-hexes/{hex_id}")
async def update_corridor_hex(
    workspace_id: str, hex_id: str, body: CorridorHexUpdate,
    org: dict = Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    await _check_workspace(workspace_id, org, db)
    result = await db.execute(
        select(CorridorHex).where(
            CorridorHex.id == hex_id,
            CorridorHex.workspace_id == workspace_id,
            not_deleted(CorridorHex),
        )
    )
    ch = result.scalar_one_or_none()
    if not ch:
        raise HTTPException(404, "corridor hex not found")
    ch.display_name = body.display_name
    await db.commit()
    return _ok({"id": ch.id, "display_name": ch.display_name})


@router.delete("/{workspace_id}/corridor-hexes/{hex_id}")
async def delete_corridor_hex(
    workspace_id: str, hex_id: str,
    org: dict = Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    await _check_workspace(workspace_id, org, db)
    result = await db.execute(
        select(CorridorHex).where(
            CorridorHex.id == hex_id,
            CorridorHex.workspace_id == workspace_id,
            not_deleted(CorridorHex),
        )
    )
    ch = result.scalar_one_or_none()
    if not ch:
        raise HTTPException(404, "corridor hex not found")

    conns = await db.execute(
        select(HexConnection).where(
            HexConnection.workspace_id == workspace_id,
            HexConnection.auto_created.is_(True),
            not_deleted(HexConnection),
            (
                ((HexConnection.hex_a_q == ch.hex_q) & (HexConnection.hex_a_r == ch.hex_r))
                | ((HexConnection.hex_b_q == ch.hex_q) & (HexConnection.hex_b_r == ch.hex_r))
            ),
        )
    )
    for conn in conns.scalars().all():
        conn.soft_delete()

    ch.soft_delete()
    await db.commit()
    return _ok(message="deleted")


# ── Connection CRUD ──────────────────────────────────────

@router.post("/{workspace_id}/connections")
async def create_connection(
    workspace_id: str, body: ConnectionCreate,
    org: dict = Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    await _check_workspace(workspace_id, org, db)
    if not is_adjacent(body.hex_a_q, body.hex_a_r, body.hex_b_q, body.hex_b_r):
        raise HTTPException(400, "hexes must be adjacent")
    if not await _is_hex_occupied(workspace_id, body.hex_a_q, body.hex_a_r, db):
        raise HTTPException(400, "hex A is not occupied")
    if not await _is_hex_occupied(workspace_id, body.hex_b_q, body.hex_b_r, db):
        raise HTTPException(400, "hex B is not occupied")

    aq, ar, bq, br = ordered_pair(body.hex_a_q, body.hex_a_r, body.hex_b_q, body.hex_b_r)
    existing = await db.execute(
        select(HexConnection).where(
            HexConnection.workspace_id == workspace_id,
            HexConnection.hex_a_q == aq, HexConnection.hex_a_r == ar,
            HexConnection.hex_b_q == bq, HexConnection.hex_b_r == br,
            not_deleted(HexConnection),
        ).limit(1)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "connection already exists")

    direction = body.direction
    if (body.hex_a_q, body.hex_a_r) != (aq, ar) and direction != "both":
        direction = "b_to_a" if direction == "a_to_b" else "a_to_b"

    conn = HexConnection(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        hex_a_q=aq, hex_a_r=ar, hex_b_q=bq, hex_b_r=br,
        direction=direction, auto_created=False,
        created_by=org.get("user_id"),
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return _ok(ConnectionInfo(
        id=conn.id, workspace_id=conn.workspace_id,
        hex_a_q=conn.hex_a_q, hex_a_r=conn.hex_a_r,
        hex_b_q=conn.hex_b_q, hex_b_r=conn.hex_b_r,
        direction=conn.direction, auto_created=conn.auto_created,
        created_by=conn.created_by, created_at=conn.created_at,
    ).model_dump())


@router.get("/{workspace_id}/connections")
async def list_connections(
    workspace_id: str,
    org: dict = Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    await _check_workspace(workspace_id, org, db)
    result = await db.execute(
        select(HexConnection).where(
            HexConnection.workspace_id == workspace_id,
            not_deleted(HexConnection),
        )
    )
    items = [
        ConnectionInfo(
            id=c.id, workspace_id=c.workspace_id,
            hex_a_q=c.hex_a_q, hex_a_r=c.hex_a_r,
            hex_b_q=c.hex_b_q, hex_b_r=c.hex_b_r,
            direction=c.direction, auto_created=c.auto_created,
            created_by=c.created_by, created_at=c.created_at,
        ).model_dump()
        for c in result.scalars().all()
    ]
    return _ok(items)


@router.put("/{workspace_id}/connections/{conn_id}")
async def update_connection(
    workspace_id: str, conn_id: str, body: ConnectionUpdate,
    org: dict = Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    await _check_workspace(workspace_id, org, db)
    result = await db.execute(
        select(HexConnection).where(
            HexConnection.id == conn_id,
            HexConnection.workspace_id == workspace_id,
            not_deleted(HexConnection),
        )
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(404, "connection not found")
    conn.direction = body.direction
    await db.commit()
    return _ok({"id": conn.id, "direction": conn.direction})


@router.delete("/{workspace_id}/connections/{conn_id}")
async def delete_connection(
    workspace_id: str, conn_id: str,
    org: dict = Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    await _check_workspace(workspace_id, org, db)
    result = await db.execute(
        select(HexConnection).where(
            HexConnection.id == conn_id,
            HexConnection.workspace_id == workspace_id,
            not_deleted(HexConnection),
        )
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(404, "connection not found")
    conn.soft_delete()
    await db.commit()
    return _ok(message="deleted")


# ── Human Hex ──────────────────────────────────────────

@router.put("/{workspace_id}/members/{user_id}/hex")
async def set_human_hex(
    workspace_id: str, user_id: str, body: HumanHexUpdate,
    org: dict = Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    await _check_workspace(workspace_id, org, db)
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            not_deleted(WorkspaceMember),
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(404, "member not found")
    if await _is_hex_occupied(workspace_id, body.hex_q, body.hex_r, db):
        if not (member.hex_q == body.hex_q and member.hex_r == body.hex_r):
            raise HTTPException(400, "hex position already occupied")
    member.hex_q = body.hex_q
    member.hex_r = body.hex_r
    await db.commit()
    return _ok({"user_id": user_id, "hex_q": member.hex_q, "hex_r": member.hex_r})


@router.delete("/{workspace_id}/members/{user_id}/hex")
async def remove_human_hex(
    workspace_id: str, user_id: str,
    org: dict = Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    await _check_workspace(workspace_id, org, db)
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            not_deleted(WorkspaceMember),
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(404, "member not found")
    member.hex_q = None
    member.hex_r = None
    await db.commit()
    return _ok(message="human hex removed")


@router.put("/{workspace_id}/members/{user_id}/channel")
async def set_human_channel(
    workspace_id: str, user_id: str, body: HumanChannelUpdate,
    org: dict = Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    await _check_workspace(workspace_id, org, db)
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            not_deleted(WorkspaceMember),
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(404, "member not found")
    member.channel_type = body.channel_type
    member.channel_config = body.channel_config
    await db.commit()
    return _ok({"user_id": user_id, "channel_type": member.channel_type})


# ── Topology ───────────────────────────────────────────

@router.get("/{workspace_id}/topology")
async def get_topology(
    workspace_id: str,
    org: dict = Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    await _check_workspace(workspace_id, org, db)
    topo = await corridor_router.get_topology(workspace_id, db)
    return _ok(TopologyInfo(
        nodes=[
            TopologyNodeInfo(
                hex_q=n.hex_q, hex_r=n.hex_r, node_type=n.node_type,
                entity_id=n.entity_id, display_name=n.display_name, extra=n.extra,
            )
            for n in topo.nodes
        ],
        edges=[
            TopologyEdgeInfo(
                a_q=e.a_q, a_r=e.a_r, b_q=e.b_q, b_r=e.b_r,
                direction=e.direction, auto_created=e.auto_created,
            )
            for e in topo.edges
        ],
    ).model_dump())
