"""Corridor routing engine — BFS-based bidirectional graph traversal for workspace topology."""

from __future__ import annotations

import logging
import uuid
from collections import deque
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import not_deleted
from app.models.corridor import CorridorHex, HexConnection, HumanHex, ordered_pair
from app.models.instance import Instance
from app.models.workspace_member import WorkspaceMember
from app.models.workspace_message import WorkspaceMessage

logger = logging.getLogger(__name__)


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

    human_hexes_q = await db.execute(
        select(HumanHex).where(
            HumanHex.workspace_id == workspace_id,
            not_deleted(HumanHex),
        )
    )
    for hh in human_hexes_q.scalars().all():
        hex_map[(hh.hex_q, hh.hex_r)] = TopologyNode(
            hh.hex_q, hh.hex_r, "human", entity_id=hh.id,
            extra={"user_id": hh.user_id, "display_color": hh.display_color,
                   "channel_type": hh.channel_type, "channel_config": hh.channel_config},
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


async def _get_adjacency(workspace_id: str, db: AsyncSession) -> dict[tuple[int, int], list[tuple[int, int]]]:
    """Build bidirectional adjacency list from hex_connections.

    All connections are treated as bidirectional (direction control removed in this version).
    Returns {(q, r): [(neighbor_q, neighbor_r), ...]}
    """
    conns_q = await db.execute(
        select(HexConnection).where(
            HexConnection.workspace_id == workspace_id,
            not_deleted(HexConnection),
        )
    )
    adj: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for conn in conns_q.scalars().all():
        a = (conn.hex_a_q, conn.hex_a_r)
        b = (conn.hex_b_q, conn.hex_b_r)
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)

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
        for neighbor in adj.get(current, []):
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
    """Check if there is a path from source to target."""
    hex_map = await _build_hex_map(workspace_id, db)
    adj = await _get_adjacency(workspace_id, db)

    target = (to_q, to_r)
    visited: set[tuple[int, int]] = {(from_q, from_r)}
    queue: deque[tuple[int, int]] = deque([(from_q, from_r)])

    while queue:
        current = queue.popleft()
        for neighbor in adj.get(current, []):
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
        TopologyEdge(c.hex_a_q, c.hex_a_r, c.hex_b_q, c.hex_b_r, c.auto_created)
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


async def cascade_delete_connections(
    workspace_id: str, q: int, r: int, db: AsyncSession,
) -> None:
    """Soft-delete all hex connections referencing the given position."""
    conns = await db.execute(
        select(HexConnection).where(
            HexConnection.workspace_id == workspace_id,
            not_deleted(HexConnection),
            (
                ((HexConnection.hex_a_q == q) & (HexConnection.hex_a_r == r))
                | ((HexConnection.hex_b_q == q) & (HexConnection.hex_b_r == r))
            ),
        )
    )
    for conn in conns.scalars().all():
        conn.soft_delete()


async def auto_connect_hex(
    workspace_id: str, q: int, r: int, created_by: str | None, db: AsyncSession,
) -> list[TopologyNode]:
    """Auto-create bidirectional connections to all adjacent occupied hexes.

    Returns the list of neighbor TopologyNodes that were connected (including
    already-connected ones).
    """
    hex_map = await _build_hex_map(workspace_id, db)
    offsets = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, -1), (-1, 1)]
    connected: list[TopologyNode] = []

    for dq, dr in offsets:
        nq, nr = q + dq, r + dr
        neighbor = hex_map.get((nq, nr))
        if neighbor is None:
            continue
        connected.append(neighbor)

        aq, ar, bq, br = ordered_pair(q, r, nq, nr)
        existing = await db.execute(
            select(HexConnection).where(
                HexConnection.workspace_id == workspace_id,
                HexConnection.hex_a_q == aq, HexConnection.hex_a_r == ar,
                HexConnection.hex_b_q == bq, HexConnection.hex_b_r == br,
            ).limit(1)
        )
        row = existing.scalar_one_or_none()
        if row is not None:
            if row.deleted_at is not None:
                row.deleted_at = None
                row.auto_created = True
            continue
        conn = HexConnection(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            hex_a_q=aq, hex_a_r=ar, hex_b_q=bq, hex_b_r=br,
            direction="both", auto_created=True,
            created_by=created_by,
        )
        db.add(conn)

    return connected


async def detect_islands(
    workspace_id: str, db: AsyncSession
) -> list[list[str]]:
    """Detect topology islands — return list of mutually disconnected node groups.

    Each group is a list of hex keys as "q,r" strings. Uses BFS from each unvisited node.
    """
    hex_map = await _build_hex_map(workspace_id, db)
    adj = await _get_adjacency(workspace_id, db)

    all_nodes = set(hex_map.keys())
    visited: set[tuple[int, int]] = set()
    islands: list[list[str]] = []

    for start in all_nodes:
        if start in visited:
            continue
        component: list[str] = []
        queue: deque[tuple[int, int]] = deque([start])
        visited.add(start)
        while queue:
            current = queue.popleft()
            component.append(f"{current[0]},{current[1]}")
            for neighbor in adj.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        islands.append(component)

    return islands


async def detect_single_points_of_failure(
    workspace_id: str, db: AsyncSession
) -> list[str]:
    """Detect single points of failure — nodes whose removal would split the topology.

    Returns list of hex keys as "q,r" strings (articulation points).
    """
    hex_map = await _build_hex_map(workspace_id, db)
    adj = await _get_adjacency(workspace_id, db)
    all_nodes = set(hex_map.keys())

    if len(all_nodes) <= 1:
        return []

    spof: list[str] = []

    for node in all_nodes:
        if node not in adj:
            continue
        removed = {k: [n for n in v if n != node] for k, v in adj.items() if k != node}

        remaining = set(removed.keys())
        if not remaining:
            continue

        start = next(iter(remaining))
        visited: set[tuple[int, int]] = {start}
        queue: deque[tuple[int, int]] = deque([start])
        while queue:
            current = queue.popleft()
            for neighbor in removed.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        if len(visited) < len(remaining):
            spof.append(f"{node[0]},{node[1]}")

    return spof


@dataclass
class MessageFlowPair:
    sender_hex_key: str
    receiver_hex_key: str
    count: int


async def get_message_flow_stats(
    workspace_id: str, db: AsyncSession
) -> list[MessageFlowPair]:
    """Count messages per sender-receiver hex pair from workspace_messages.

    Maps sender_id/sender_type and target_instance_id to hex positions.
    Only includes pairs where both sender and receiver have hex positions in this workspace.
    """
    agents_q = await db.execute(
        select(Instance.id, Instance.hex_position_q, Instance.hex_position_r).where(
            Instance.workspace_id == workspace_id,
            not_deleted(Instance),
        )
    )
    agent_hex: dict[str, tuple[int, int]] = {
        row.id: (row.hex_position_q, row.hex_position_r)
        for row in agents_q.all()
    }

    human_hexes_q = await db.execute(
        select(HumanHex.id, HumanHex.user_id, HumanHex.hex_q, HumanHex.hex_r).where(
            HumanHex.workspace_id == workspace_id,
            not_deleted(HumanHex),
        )
    )
    human_hex: dict[str, tuple[int, int]] = {}
    for row in human_hexes_q.all():
        human_hex[row.user_id] = (row.hex_q, row.hex_r)

    msgs_q = await db.execute(
        select(
            WorkspaceMessage.sender_id,
            WorkspaceMessage.sender_type,
            WorkspaceMessage.target_instance_id,
            func.count(WorkspaceMessage.id).label("cnt"),
        )
        .where(
            WorkspaceMessage.workspace_id == workspace_id,
            not_deleted(WorkspaceMessage),
        )
        .group_by(
            WorkspaceMessage.sender_id,
            WorkspaceMessage.sender_type,
            WorkspaceMessage.target_instance_id,
        )
    )

    pair_counts: dict[tuple[str, str], int] = {}
    for row in msgs_q.all():
        if row.sender_type == "agent":
            sender_hex = agent_hex.get(row.sender_id)
        else:
            sender_hex = human_hex.get(row.sender_id)
        if sender_hex is None:
            continue
        sender_key = f"{sender_hex[0]},{sender_hex[1]}"

        if row.target_instance_id:
            receiver_hex = agent_hex.get(row.target_instance_id)
            if receiver_hex is None:
                continue
            receiver_key = f"{receiver_hex[0]},{receiver_hex[1]}"
        else:
            continue

        key = (sender_key, receiver_key)
        pair_counts[key] = pair_counts.get(key, 0) + row.cnt

    return [
        MessageFlowPair(sender_hex_key=k[0], receiver_hex_key=k[1], count=v)
        for k, v in pair_counts.items()
    ]
