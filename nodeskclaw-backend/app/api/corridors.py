"""Corridor API — CorridorHex CRUD, Connection CRUD, Human Hex, Topology query."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.workspaces import broadcast_event
from app.core.deps import get_current_org, get_db
from app.models.topology_audit_log import TopologyAuditLog
from app.models.base import not_deleted
from app.models.corridor import CorridorHex, HexConnection, HumanHex, is_adjacent, ordered_pair
from app.models.instance import Instance
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.schemas.corridor import (
    ConnectionCreate,
    ConnectionInfo,
    CorridorHexCreate,
    CorridorHexInfo,
    CorridorHexUpdate,
    HumanHexCreate,
    HumanHexInfo,
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


def _org_id(org) -> str:
    return org.id if hasattr(org, "id") else org.get("org_id", "")


def _actor(org_ctx) -> tuple[str, str]:
    """Return (actor_type, actor_id) from org_ctx (user, org) tuple."""
    user, org = org_ctx
    if user is not None and hasattr(user, "id"):
        return "user", str(user.id)
    return "org", _org_id(org)


async def _check_workspace(workspace_id: str, org, db: AsyncSession) -> Workspace:
    result = await db.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.org_id == _org_id(org),
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
        select(HumanHex.id).where(
            HumanHex.workspace_id == workspace_id,
            HumanHex.hex_q == q,
            HumanHex.hex_r == r,
            not_deleted(HumanHex),
        ).limit(1)
    )
    if human_q.scalar_one_or_none():
        return True
    return False


# ── Corridor Hex CRUD ──────────────────────────────────

@router.post("/{workspace_id}/corridor-hexes")
async def create_corridor_hex(
    workspace_id: str, body: CorridorHexCreate,
    org_ctx=Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    await _check_workspace(workspace_id, org, db)
    if await _is_hex_occupied(workspace_id, body.hex_q, body.hex_r, db):
        raise HTTPException(400, "hex position already occupied")

    ch = CorridorHex(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        hex_q=body.hex_q,
        hex_r=body.hex_r,
        display_name=body.display_name,
        created_by=user.id if user else None,
    )
    db.add(ch)

    await corridor_router.auto_connect_hex(workspace_id, body.hex_q, body.hex_r, user.id if user else None, db)

    await db.commit()
    await db.refresh(ch)
    actor_type, actor_id = _actor(org_ctx)
    broadcast_event(workspace_id, "corridor:hex_placed", {"hex_id": ch.id, "hex_q": ch.hex_q, "hex_r": ch.hex_r})
    audit = TopologyAuditLog(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        action="corridor_hex_created",
        target_type="corridor_hex",
        target_id=ch.id,
        new_value={"hex_q": ch.hex_q, "hex_r": ch.hex_r, "display_name": ch.display_name},
        actor_type=actor_type,
        actor_id=actor_id,
    )
    db.add(audit)
    await db.commit()
    return _ok(CorridorHexInfo(
        id=ch.id, workspace_id=ch.workspace_id,
        hex_q=ch.hex_q, hex_r=ch.hex_r,
        display_name=ch.display_name,
        created_by=ch.created_by, created_at=ch.created_at,
    ).model_dump())


async def _cascade_update_connections(
    workspace_id: str, old_q: int, old_r: int, new_q: int, new_r: int, db: AsyncSession,
):
    await corridor_router.cascade_delete_connections(workspace_id, old_q, old_r, db)


@router.get("/{workspace_id}/corridor-hexes")
async def list_corridor_hexes(
    workspace_id: str,
    org_ctx=Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    _, org = org_ctx
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
    org_ctx=Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    _, org = org_ctx
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

    if body.display_name is not None:
        ch.display_name = body.display_name

    position_changed = False
    old_q, old_r = ch.hex_q, ch.hex_r
    if body.hex_q is not None and body.hex_r is not None:
        new_q, new_r = body.hex_q, body.hex_r
        if (new_q, new_r) != (old_q, old_r):
            if await _is_hex_occupied(workspace_id, new_q, new_r, db):
                raise HTTPException(400, "hex position already occupied")
            ch.hex_q = new_q
            ch.hex_r = new_r
            position_changed = True

    await db.commit()

    if position_changed:
        await _cascade_update_connections(workspace_id, old_q, old_r, ch.hex_q, ch.hex_r, db)
        await corridor_router.auto_connect_hex(workspace_id, ch.hex_q, ch.hex_r, ch.created_by, db)
        await db.commit()

    actor_type, actor_id = _actor(org_ctx)
    event_data: dict = {"hex_id": ch.id, "display_name": ch.display_name}
    if position_changed:
        event_data.update({"hex_q": ch.hex_q, "hex_r": ch.hex_r})
    broadcast_event(workspace_id, "corridor:hex_updated", event_data)
    audit = TopologyAuditLog(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        action="corridor_hex_updated",
        target_type="corridor_hex",
        target_id=ch.id,
        new_value={"display_name": ch.display_name, "hex_q": ch.hex_q, "hex_r": ch.hex_r},
        actor_type=actor_type,
        actor_id=actor_id,
    )
    db.add(audit)
    await db.commit()
    return _ok(CorridorHexInfo(
        id=ch.id, workspace_id=ch.workspace_id,
        hex_q=ch.hex_q, hex_r=ch.hex_r,
        display_name=ch.display_name,
        created_by=ch.created_by, created_at=ch.created_at,
    ).model_dump())


@router.delete("/{workspace_id}/corridor-hexes/{hex_id}")
async def delete_corridor_hex(
    workspace_id: str, hex_id: str,
    org_ctx=Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    _, org = org_ctx
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
    actor_type, actor_id = _actor(org_ctx)
    broadcast_event(workspace_id, "corridor:hex_removed", {"hex_id": ch.id})
    audit = TopologyAuditLog(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        action="corridor_hex_deleted",
        target_type="corridor_hex",
        target_id=ch.id,
        new_value=None,
        actor_type=actor_type,
        actor_id=actor_id,
    )
    db.add(audit)
    await db.commit()
    return _ok(message="deleted")


# ── Connection CRUD ──────────────────────────────────────

@router.post("/{workspace_id}/connections")
async def create_connection(
    workspace_id: str, body: ConnectionCreate,
    org_ctx=Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
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

    conn = HexConnection(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        hex_a_q=aq, hex_a_r=ar, hex_b_q=bq, hex_b_r=br,
        direction="both", auto_created=False,
        created_by=user.id if user else None,
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    actor_type, actor_id = _actor(org_ctx)
    broadcast_event(workspace_id, "connection:created", {"conn_id": conn.id})
    audit = TopologyAuditLog(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        action="connection_created",
        target_type="connection",
        target_id=conn.id,
        new_value={
            "hex_a_q": conn.hex_a_q, "hex_a_r": conn.hex_a_r,
            "hex_b_q": conn.hex_b_q, "hex_b_r": conn.hex_b_r,
        },
        actor_type=actor_type,
        actor_id=actor_id,
    )
    db.add(audit)
    await db.commit()
    return _ok(ConnectionInfo(
        id=conn.id, workspace_id=conn.workspace_id,
        hex_a_q=conn.hex_a_q, hex_a_r=conn.hex_a_r,
        hex_b_q=conn.hex_b_q, hex_b_r=conn.hex_b_r,
        auto_created=conn.auto_created,
        created_by=conn.created_by, created_at=conn.created_at,
    ).model_dump())


@router.get("/{workspace_id}/connections")
async def list_connections(
    workspace_id: str,
    org_ctx=Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    _, org = org_ctx
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
            auto_created=c.auto_created,
            created_by=c.created_by, created_at=c.created_at,
        ).model_dump()
        for c in result.scalars().all()
    ]
    return _ok(items)


@router.delete("/{workspace_id}/connections/{conn_id}")
async def delete_connection(
    workspace_id: str, conn_id: str,
    org_ctx=Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    _, org = org_ctx
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
    actor_type, actor_id = _actor(org_ctx)
    broadcast_event(workspace_id, "connection:removed", {"conn_id": conn.id})
    audit = TopologyAuditLog(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        action="connection_deleted",
        target_type="connection",
        target_id=conn.id,
        new_value=None,
        actor_type=actor_type,
        actor_id=actor_id,
    )
    db.add(audit)
    await db.commit()
    return _ok(message="deleted")


# ── Human Hex CRUD ─────────────────────────────────────

@router.post("/{workspace_id}/human-hexes")
async def create_human_hex(
    workspace_id: str, body: HumanHexCreate,
    org_ctx=Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    _, org = org_ctx
    await _check_workspace(workspace_id, org, db)
    member_q = await db.execute(
        select(WorkspaceMember.id).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == body.user_id,
            not_deleted(WorkspaceMember),
        ).limit(1)
    )
    if not member_q.scalar_one_or_none():
        raise HTTPException(404, "member not found in this workspace")
    if await _is_hex_occupied(workspace_id, body.hex_q, body.hex_r, db):
        raise HTTPException(400, "hex position already occupied")
    actor_type, actor_id = _actor(org_ctx)
    hh = HumanHex(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        user_id=body.user_id,
        hex_q=body.hex_q,
        hex_r=body.hex_r,
        display_color=body.display_color,
        channel_type=body.channel_type,
        channel_config=body.channel_config,
        created_by=actor_id,
    )
    db.add(hh)
    await db.commit()
    broadcast_event(workspace_id, "human:hex_placed", {"hex_id": hh.id, "user_id": body.user_id, "hex_q": hh.hex_q, "hex_r": hh.hex_r})
    audit = TopologyAuditLog(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        action="human_hex_placed",
        target_type="human_hex",
        target_id=hh.id,
        new_value={"user_id": body.user_id, "hex_q": hh.hex_q, "hex_r": hh.hex_r},
        actor_type=actor_type,
        actor_id=actor_id,
    )
    db.add(audit)
    await db.commit()
    return _ok(HumanHexInfo(
        id=hh.id, workspace_id=hh.workspace_id, user_id=hh.user_id,
        hex_q=hh.hex_q, hex_r=hh.hex_r, display_color=hh.display_color,
        channel_type=hh.channel_type, channel_config=hh.channel_config,
        created_at=hh.created_at,
    ).model_dump(mode="json"))


@router.put("/{workspace_id}/human-hexes/{hex_id}")
async def update_human_hex(
    workspace_id: str, hex_id: str, body: HumanHexUpdate,
    org_ctx=Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    _, org = org_ctx
    await _check_workspace(workspace_id, org, db)
    result = await db.execute(
        select(HumanHex).where(
            HumanHex.id == hex_id,
            HumanHex.workspace_id == workspace_id,
            not_deleted(HumanHex),
        )
    )
    hh = result.scalar_one_or_none()
    if not hh:
        raise HTTPException(404, "human hex not found")
    new_q = body.hex_q if body.hex_q is not None else hh.hex_q
    new_r = body.hex_r if body.hex_r is not None else hh.hex_r
    position_changed = False
    old_q, old_r = hh.hex_q, hh.hex_r
    if (new_q, new_r) != (old_q, old_r):
        if await _is_hex_occupied(workspace_id, new_q, new_r, db):
            raise HTTPException(400, "hex position already occupied")
        hh.hex_q = new_q
        hh.hex_r = new_r
        position_changed = True
    if body.display_color is not None:
        hh.display_color = body.display_color
    if body.channel_type is not None:
        hh.channel_type = body.channel_type
    if body.channel_config is not None:
        hh.channel_config = body.channel_config
    await db.commit()
    if position_changed:
        await corridor_router.cascade_delete_connections(workspace_id, old_q, old_r, db)
        user = org_ctx[0]
        await corridor_router.auto_connect_hex(
            workspace_id, hh.hex_q, hh.hex_r, user.id if user else None, db,
        )
        await db.commit()
    actor_type, actor_id = _actor(org_ctx)
    broadcast_event(workspace_id, "human:hex_updated", {"hex_id": hex_id, "hex_q": hh.hex_q, "hex_r": hh.hex_r, "display_color": hh.display_color})
    audit = TopologyAuditLog(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        action="human_hex_updated",
        target_type="human_hex",
        target_id=hex_id,
        new_value={"hex_q": hh.hex_q, "hex_r": hh.hex_r, "display_color": hh.display_color},
        actor_type=actor_type,
        actor_id=actor_id,
    )
    db.add(audit)
    await db.commit()
    return _ok(HumanHexInfo(
        id=hh.id, workspace_id=hh.workspace_id, user_id=hh.user_id,
        hex_q=hh.hex_q, hex_r=hh.hex_r, display_color=hh.display_color,
        channel_type=hh.channel_type, channel_config=hh.channel_config,
        created_at=hh.created_at,
    ).model_dump(mode="json"))


@router.delete("/{workspace_id}/human-hexes/{hex_id}")
async def delete_human_hex(
    workspace_id: str, hex_id: str,
    org_ctx=Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    _, org = org_ctx
    await _check_workspace(workspace_id, org, db)
    result = await db.execute(
        select(HumanHex).where(
            HumanHex.id == hex_id,
            HumanHex.workspace_id == workspace_id,
            not_deleted(HumanHex),
        )
    )
    hh = result.scalar_one_or_none()
    if not hh:
        raise HTTPException(404, "human hex not found")
    hh.soft_delete()
    await db.commit()
    actor_type, actor_id = _actor(org_ctx)
    broadcast_event(workspace_id, "human:hex_removed", {"hex_id": hex_id})
    audit = TopologyAuditLog(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        action="human_hex_removed",
        target_type="human_hex",
        target_id=hex_id,
        new_value=None,
        actor_type=actor_type,
        actor_id=actor_id,
    )
    db.add(audit)
    await db.commit()
    return _ok(message="human hex removed")


# ── Topology ───────────────────────────────────────────

@router.get("/{workspace_id}/topology")
async def get_topology(
    workspace_id: str,
    org_ctx=Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    _, org = org_ctx
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
                auto_created=e.auto_created,
            )
            for e in topo.edges
        ],
    ).model_dump())


@router.get("/{workspace_id}/topology/health")
async def get_topology_health(
    workspace_id: str,
    org_ctx=Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    """Return topology health: islands, single points of failure, message flow stats."""
    _, org = org_ctx
    await _check_workspace(workspace_id, org, db)
    islands = await corridor_router.detect_islands(workspace_id, db)
    spof = await corridor_router.detect_single_points_of_failure(workspace_id, db)
    flow = await corridor_router.get_message_flow_stats(workspace_id, db)
    return _ok({
        "islands": islands,
        "single_points_of_failure": spof,
        "message_flow_stats": [
            {"sender_hex_key": p.sender_hex_key, "receiver_hex_key": p.receiver_hex_key, "count": p.count}
            for p in flow
        ],
    })


@router.get("/{workspace_id}/topology/message-flow")
async def get_topology_message_flow(
    workspace_id: str,
    org_ctx=Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    """Return message count per sender-receiver hex pair from workspace_messages."""
    _, org = org_ctx
    await _check_workspace(workspace_id, org, db)
    flow = await corridor_router.get_message_flow_stats(workspace_id, db)
    return _ok([
        {"sender_hex_key": p.sender_hex_key, "receiver_hex_key": p.receiver_hex_key, "count": p.count}
        for p in flow
    ])
