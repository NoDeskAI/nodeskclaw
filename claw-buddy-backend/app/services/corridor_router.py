"""Corridor routing engine — BFS-based directed graph traversal for workspace topology."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import not_deleted
from app.models.corridor import CorridorHex, HexConnection
from app.models.instance import Instance
from app.models.workspace_member import WorkspaceMember


@dataclass
class ReachableEndpoint:
    hex_q: int
    hex_r: int
    endpoint_type: str  # "agent" | "human"
    entity_id: str  # instance_id or user_id


@dataclass
class TopologyNode:
    hex_q: int
    hex_r: int
    node_type: str  # "blackboard" | "agent" | "human" | "corridor"
    entity_id: str | None = None
    display_name: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class TopologyEdge:
    a_q: int
    a_r: int
    b_q: int
    b_r: int
    direction: str
    auto_created: bool


@dataclass
class Topology:
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]


async def _build_hex_map(workspace_id: str, db: AsyncSession) -> dict[tuple[int, int], TopologyNode]:
    """Build a mapping from (q, r) -> node info for all occupied hexes."""
    hex_map: dict[tuple[int, int], TopologyNode] = {}

    hex_map[(0, 0)] = TopologyNode(0, 0, "blackboard")

    agents_q = await db.execute(
        select(Instance).where(
            Instance.workspace_id == workspace_id,
            not_deleted(Instance),
        )
    )
    for agent in agents_q.scalars().all():
        q, r = agent.hex_position_q, agent.hex_position_r
        if q is not None and r is not None:
            hex_map[(q, r)] = TopologyNode(
                q, r, "agent", entity_id=agent.id,
                display_name=agent.agent_display_name or agent.name,
            )

    members_q = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            not_deleted(WorkspaceMember),
            WorkspaceMember.hex_q.isnot(None),
        )
    )
    for member in members_q.scalars().all():
        hex_map[(member.hex_q, member.hex_r)] = TopologyNode(
            member.hex_q, member.hex_r, "human", entity_id=member.user_id,
            extra={"channel_type": member.channel_type},
        )

    corridors_q = await db.execute(
        select(CorridorHex).where(
            CorridorHex.workspace_id == workspace_id,
            not_deleted(CorridorHex),
        )
    )
    for ch in corridors_q.scalars().all():
        hex_map[(ch.hex_q, ch.hex_r)] = TopologyNode(
            ch.hex_q, ch.hex_r, "corridor", entity_id=ch.id,
            display_name=ch.display_name,
        )

    return hex_map


async def _get_adjacency(workspace_id: str, db: AsyncSession) -> dict[tuple[int, int], list[tuple[tuple[int, int], str]]]:
    """Build directed adjacency list from hex_connections.

    Returns {(q, r): [((neighbor_q, neighbor_r), direction), ...]}
    where direction indicates the traversal direction relative to the edge.
    """
    conns_q = await db.execute(
        select(HexConnection).where(
            HexConnection.workspace_id == workspace_id,
            not_deleted(HexConnection),
        )
    )
    adj: dict[tuple[int, int], list[tuple[tuple[int, int], str]]] = {}
    for conn in conns_q.scalars().all():
        a = (conn.hex_a_q, conn.hex_a_r)
        b = (conn.hex_b_q, conn.hex_b_r)
        d = conn.direction

        if d == "both" or d == "a_to_b":
            adj.setdefault(a, []).append((b, d))
        if d == "both" or d == "b_to_a":
            adj.setdefault(b, []).append((a, d))

    return adj


async def get_reachable_endpoints(
    workspace_id: str, from_q: int, from_r: int, db: AsyncSession
) -> list[ReachableEndpoint]:
    """BFS from (from_q, from_r), corridor hexes relay, agent/human hexes terminate."""
    hex_map = await _build_hex_map(workspace_id, db)
    adj = await _get_adjacency(workspace_id, db)

    endpoints: list[ReachableEndpoint] = []
    visited: set[tuple[int, int]] = {(from_q, from_r)}
    queue: deque[tuple[int, int]] = deque([(from_q, from_r)])

    while queue:
        current = queue.popleft()
        for neighbor, _ in adj.get(current, []):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            node = hex_map.get(neighbor)
            if node is None:
                continue
            if node.node_type == "agent":
                endpoints.append(ReachableEndpoint(
                    node.hex_q, node.hex_r, "agent", node.entity_id or "",
                ))
            elif node.node_type == "human":
                endpoints.append(ReachableEndpoint(
                    node.hex_q, node.hex_r, "human", node.entity_id or "",
                ))
            elif node.node_type == "corridor":
                queue.append(neighbor)
            elif node.node_type == "blackboard":
                pass

    return endpoints


async def get_blackboard_audience(
    workspace_id: str, db: AsyncSession
) -> list[ReachableEndpoint]:
    """Get all endpoints reachable from the blackboard at (0, 0)."""
    return await get_reachable_endpoints(workspace_id, 0, 0, db)


async def can_reach(
    workspace_id: str, from_q: int, from_r: int, to_q: int, to_r: int, db: AsyncSession
) -> bool:
    """Check if there is a directed path from source to target."""
    hex_map = await _build_hex_map(workspace_id, db)
    adj = await _get_adjacency(workspace_id, db)

    target = (to_q, to_r)
    visited: set[tuple[int, int]] = {(from_q, from_r)}
    queue: deque[tuple[int, int]] = deque([(from_q, from_r)])

    while queue:
        current = queue.popleft()
        for neighbor, _ in adj.get(current, []):
            if neighbor == target:
                return True
            if neighbor in visited:
                continue
            visited.add(neighbor)
            node = hex_map.get(neighbor)
            if node and node.node_type == "corridor":
                queue.append(neighbor)

    return False


async def get_topology(workspace_id: str, db: AsyncSession) -> Topology:
    """Return the full topology graph for visualization."""
    hex_map = await _build_hex_map(workspace_id, db)

    conns_q = await db.execute(
        select(HexConnection).where(
            HexConnection.workspace_id == workspace_id,
            not_deleted(HexConnection),
        )
    )
    edges = [
        TopologyEdge(c.hex_a_q, c.hex_a_r, c.hex_b_q, c.hex_b_r, c.direction, c.auto_created)
        for c in conns_q.scalars().all()
    ]

    return Topology(nodes=list(hex_map.values()), edges=edges)


async def has_any_connections(workspace_id: str, db: AsyncSession) -> bool:
    """Check if the workspace has any connections configured (for backward compat)."""
    result = await db.execute(
        select(HexConnection.id).where(
            HexConnection.workspace_id == workspace_id,
            not_deleted(HexConnection),
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None
