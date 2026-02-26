"""Corridor router — BFS-based directed graph traversal for workspace topology."""

import logging
from collections import deque
from dataclasses import dataclass, field

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import not_deleted
from app.models.corridor import CorridorHex, HexConnection
from app.models.instance import Instance
from app.models.workspace_member import WorkspaceMember

logger = logging.getLogger(__name__)


@dataclass
class TopologyNode:
    q: int
    r: int
    node_type: str  # "blackboard" | "agent" | "human" | "corridor"
    entity_id: str | None = None
    display_name: str | None = None


@dataclass
class TopologyEdge:
    a_q: int
    a_r: int
    b_q: int
    b_r: int
    direction: str
    auto_created: bool
    connection_id: str


@dataclass
class ReachableEndpoint:
    q: int
    r: int
    endpoint_type: str  # "agent" | "human"
    entity_id: str
    display_name: str | None = None


@dataclass
class Topology:
    nodes: list[TopologyNode] = field(default_factory=list)
    edges: list[TopologyEdge] = field(default_factory=list)


async def _load_occupied_map(db: AsyncSession, workspace_id: str) -> dict[tuple[int, int], TopologyNode]:
    """Build a map of all occupied hex positions in the workspace."""
    occupied: dict[tuple[int, int], TopologyNode] = {}

    occupied[(0, 0)] = TopologyNode(q=0, r=0, node_type="blackboard")

    agents_q = await db.execute(
        select(Instance).where(
            and_(Instance.workspace_id == workspace_id, not_deleted(Instance))
        )
    )
    for inst in agents_q.scalars().all():
        pos = (inst.hex_position_q, inst.hex_position_r)
        if pos == (0, 0):
            continue
        occupied[pos] = TopologyNode(
            q=pos[0], r=pos[1], node_type="agent",
            entity_id=inst.id, display_name=inst.agent_display_name or inst.name,
        )

    corridors_q = await db.execute(
        select(CorridorHex).where(
            and_(CorridorHex.workspace_id == workspace_id, not_deleted(CorridorHex))
        )
    )
    for ch in corridors_q.scalars().all():
        pos = (ch.hex_q, ch.hex_r)
        occupied[pos] = TopologyNode(
            q=pos[0], r=pos[1], node_type="corridor",
            entity_id=ch.id, display_name=ch.display_name,
        )

    humans_q = await db.execute(
        select(WorkspaceMember).where(
            and_(
                WorkspaceMember.workspace_id == workspace_id,
                not_deleted(WorkspaceMember),
                WorkspaceMember.hex_q.isnot(None),
            )
        )
    )
    for hm in humans_q.scalars().all():
        pos = (hm.hex_q, hm.hex_r)
        occupied[pos] = TopologyNode(
            q=pos[0], r=pos[1], node_type="human",
            entity_id=hm.user_id, display_name=None,
        )

    return occupied


async def _load_adjacency(
    db: AsyncSession, workspace_id: str,
) -> dict[tuple[int, int], list[tuple[tuple[int, int], str, str]]]:
    """Build adjacency list from hex_connections. Returns {pos: [(neighbor_pos, direction, conn_id)]}."""
    adj: dict[tuple[int, int], list[tuple[tuple[int, int], str, str]]] = {}

    conns_q = await db.execute(
        select(HexConnection).where(
            and_(HexConnection.workspace_id == workspace_id, not_deleted(HexConnection))
        )
    )
    for conn in conns_q.scalars().all():
        a = (conn.hex_a_q, conn.hex_a_r)
        b = (conn.hex_b_q, conn.hex_b_r)

        if conn.direction in ("both", "a_to_b"):
            adj.setdefault(a, []).append((b, conn.direction, conn.id))
        if conn.direction in ("both", "b_to_a"):
            adj.setdefault(b, []).append((a, conn.direction, conn.id))

    return adj


async def get_reachable_endpoints(
    db: AsyncSession, workspace_id: str, from_q: int, from_r: int,
) -> list[ReachableEndpoint]:
    """BFS from (from_q, from_r), return all reachable agent/human endpoints."""
    occupied = await _load_occupied_map(db, workspace_id)
    adj = await _load_adjacency(db, workspace_id)

    endpoints: list[ReachableEndpoint] = []
    visited: set[tuple[int, int]] = {(from_q, from_r)}
    queue: deque[tuple[int, int]] = deque()

    for neighbor_pos, _, _ in adj.get((from_q, from_r), []):
        if neighbor_pos not in visited:
            visited.add(neighbor_pos)
            queue.append(neighbor_pos)

    while queue:
        pos = queue.popleft()
        node = occupied.get(pos)
        if node is None:
            continue

        if node.node_type in ("agent", "human"):
            endpoints.append(ReachableEndpoint(
                q=pos[0], r=pos[1], endpoint_type=node.node_type,
                entity_id=node.entity_id or "", display_name=node.display_name,
            ))
        elif node.node_type == "corridor":
            for neighbor_pos, _, _ in adj.get(pos, []):
                if neighbor_pos not in visited:
                    visited.add(neighbor_pos)
                    queue.append(neighbor_pos)

    return endpoints


async def get_blackboard_audience(
    db: AsyncSession, workspace_id: str,
) -> list[ReachableEndpoint]:
    """Get all endpoints reachable from the blackboard at (0, 0)."""
    return await get_reachable_endpoints(db, workspace_id, 0, 0)


async def can_reach(
    db: AsyncSession, workspace_id: str,
    from_q: int, from_r: int, to_q: int, to_r: int,
) -> bool:
    """Check if (from_q, from_r) can reach (to_q, to_r) through the corridor graph."""
    endpoints = await get_reachable_endpoints(db, workspace_id, from_q, from_r)
    return any(ep.q == to_q and ep.r == to_r for ep in endpoints)


async def get_topology(db: AsyncSession, workspace_id: str) -> Topology:
    """Return the full topology (nodes + edges) for visualization."""
    occupied = await _load_occupied_map(db, workspace_id)
    nodes = list(occupied.values())

    conns_q = await db.execute(
        select(HexConnection).where(
            and_(HexConnection.workspace_id == workspace_id, not_deleted(HexConnection))
        )
    )
    edges = [
        TopologyEdge(
            a_q=c.hex_a_q, a_r=c.hex_a_r, b_q=c.hex_b_q, b_r=c.hex_b_r,
            direction=c.direction, auto_created=c.auto_created, connection_id=c.id,
        )
        for c in conns_q.scalars().all()
    ]

    return Topology(nodes=nodes, edges=edges)


async def has_any_connections(db: AsyncSession, workspace_id: str) -> bool:
    """Check if the workspace has any corridor connections (for backward compat)."""
    result = await db.execute(
        select(HexConnection.id).where(
            and_(HexConnection.workspace_id == workspace_id, not_deleted(HexConnection))
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None
