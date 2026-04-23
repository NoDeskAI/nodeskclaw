"""Corridor routing engine — type-agnostic BFS-based directed graph traversal for workspace topology.

v2: Reads from both node_cards (primary) and legacy tables (fallback during transition).
    Uses NodeTypeRegistry for routing decisions instead of hardcoded type checks.
    Supports directed edges via HexConnection.direction field.
"""

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
from app.models.node_card import NodeCard
from app.models.workspace_agent import WorkspaceAgent
from app.models.workspace_message import WorkspaceMessage
from app.services.runtime.registries.node_type_registry import NODE_TYPE_REGISTRY

logger = logging.getLogger(__name__)


@dataclass
class ReachableEndpoint:
    hex_q: int
    hex_r: int
    endpoint_type: str
    entity_id: str
    display_name: str = ""


@dataclass
class TopologyNode:
    hex_q: int
    hex_r: int
    node_type: str
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
    direction: str = "both"


@dataclass
class Topology:
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]


async def _build_hex_map(workspace_id: str, db: AsyncSession) -> dict[tuple[int, int], TopologyNode]:
    """Build a mapping from (q, r) -> node info.

    Reads from node_cards first; falls back to legacy tables for nodes not yet migrated.
    """
    hex_map: dict[tuple[int, int], TopologyNode] = {}

    cards_q = await db.execute(
        select(NodeCard).where(
            NodeCard.workspace_id == workspace_id,
            not_deleted(NodeCard),
        )
    )
    for card in cards_q.scalars().all():
        meta = card.metadata_ or {}
        extra = {}
        if card.node_type == "human":
            extra = {
                "user_id": meta.get("user_id"),
                "display_color": meta.get("display_color", "#f59e0b"),
                "channel_type": meta.get("channel_type"),
                "channel_config": meta.get("channel_config"),
            }
        hex_map[(card.hex_q, card.hex_r)] = TopologyNode(
            card.hex_q, card.hex_r, card.node_type,
            entity_id=card.node_id,
            display_name=card.name,
            extra=extra,
        )

    if hex_map:
        return hex_map

    hex_map[(0, 0)] = TopologyNode(0, 0, "blackboard")

    agents_q = await db.execute(
        select(Instance, WorkspaceAgent).join(
            WorkspaceAgent,
            (WorkspaceAgent.instance_id == Instance.id) & (WorkspaceAgent.deleted_at.is_(None)),
        ).where(
            WorkspaceAgent.workspace_id == workspace_id,
            not_deleted(Instance),
        )
    )
    for agent, wa in agents_q.all():
        q, r = wa.hex_q, wa.hex_r
        if q is not None and r is not None:
            hex_map[(q, r)] = TopologyNode(
                q, r, "agent", entity_id=agent.id,
                display_name=wa.display_name or agent.name,
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
            display_name=hh.display_name,
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


async def _get_adjacency(
    workspace_id: str, db: AsyncSession,
) -> dict[tuple[int, int], list[tuple[int, int]]]:
    """Build adjacency list from hex_connections, respecting direction field.

    direction="both": bidirectional edges.
    direction="a_to_b": only a->b edge.
    direction="b_to_a": only b->a edge.
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
        direction = conn.direction or "both"

        if direction in ("both", "a_to_b"):
            adj.setdefault(a, []).append(b)
        if direction in ("both", "b_to_a"):
            adj.setdefault(b, []).append(a)

    return adj


def _should_propagate(node_type: str) -> bool:
    type_def = NODE_TYPE_REGISTRY.get(node_type)
    if type_def is not None:
        return type_def.propagates
    return node_type in ("corridor", "blackboard")


def _should_consume(node_type: str) -> bool:
    type_def = NODE_TYPE_REGISTRY.get(node_type)
    if type_def is not None:
        return type_def.consumes
    return node_type in ("agent", "human", "blackboard")


def _is_addressable(node_type: str) -> bool:
    type_def = NODE_TYPE_REGISTRY.get(node_type)
    if type_def is not None:
        return type_def.is_addressable
    return node_type != "corridor"


@dataclass
class HookToFire:
    node_id: str
    node_type: str
    hook_name: str
    hex_q: int
    hex_r: int


async def get_reachable_endpoints(
    workspace_id: str,
    from_q: int,
    from_r: int,
    db: AsyncSession,
    *,
    max_hops: int = 0,
    visited_ids: set[str] | None = None,
) -> tuple[list[ReachableEndpoint], list[HookToFire]]:
    """BFS from (from_q, from_r) using registry-driven routing rules.

    Args:
        max_hops: stop expanding beyond this depth (0 = unlimited).
        visited_ids: entity_ids already visited (for cycle prevention in delegation chains).

    Returns (endpoints, hooks_to_fire).
    """
    hex_map = await _build_hex_map(workspace_id, db)
    adj = await _get_adjacency(workspace_id, db)

    skip_entity_ids = visited_ids or set()

    endpoints: list[ReachableEndpoint] = []
    hooks_to_fire: list[HookToFire] = []
    seen_entity_ids: set[str] = set()
    visited: set[tuple[int, int]] = {(from_q, from_r)}
    queue: deque[tuple[tuple[int, int], int]] = deque([((from_q, from_r), 0)])

    while queue:
        current, hops = queue.popleft()
        for neighbor in adj.get(current, []):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            node = hex_map.get(neighbor)
            if node is None:
                continue

            entity_id = node.entity_id or ""
            if entity_id in skip_entity_ids:
                continue

            type_def = NODE_TYPE_REGISTRY.get(node.node_type)

            if _should_consume(node.node_type):
                if not (entity_id and entity_id in seen_entity_ids):
                    if entity_id:
                        seen_entity_ids.add(entity_id)
                    endpoints.append(ReachableEndpoint(
                        node.hex_q, node.hex_r, node.node_type,
                        entity_id,
                        display_name=node.display_name or "",
                    ))

            if _should_propagate(node.node_type):
                if max_hops <= 0 or hops + 1 < max_hops:
                    queue.append((neighbor, hops + 1))

            if type_def and "on_message_passing" in (type_def.hooks or []):
                hooks_to_fire.append(HookToFire(
                    node_id=entity_id,
                    node_type=node.node_type,
                    hook_name="on_message_passing",
                    hex_q=node.hex_q,
                    hex_r=node.hex_r,
                ))

    return endpoints, hooks_to_fire


async def get_agent_hex_in_workspace(
    instance_id: str, workspace_id: str, db: AsyncSession,
) -> tuple[int, int] | None:
    card_q = await db.execute(
        select(NodeCard.hex_q, NodeCard.hex_r).where(
            NodeCard.node_id == instance_id,
            NodeCard.workspace_id == workspace_id,
            NodeCard.node_type == "agent",
            not_deleted(NodeCard),
        ).limit(1)
    )
    row = card_q.first()
    if row:
        return (row.hex_q, row.hex_r)

    wa = await db.execute(
        select(WorkspaceAgent.hex_q, WorkspaceAgent.hex_r)
        .where(
            WorkspaceAgent.instance_id == instance_id,
            WorkspaceAgent.workspace_id == workspace_id,
            not_deleted(WorkspaceAgent),
        )
        .limit(1)
    )
    row = wa.first()
    return (row.hex_q, row.hex_r) if row else None


async def get_blackboard_audience(
    workspace_id: str, db: AsyncSession,
) -> list[ReachableEndpoint]:
    endpoints, _hooks = await get_reachable_endpoints(workspace_id, 0, 0, db)
    return endpoints


async def can_reach(
    workspace_id: str, from_q: int, from_r: int, to_q: int, to_r: int, db: AsyncSession,
) -> bool:
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
            if node and _should_propagate(node.node_type):
                queue.append(neighbor)

    return False


async def check_topology_access(
    workspace_id: str,
    caller_node_id: str,
    target_hex_q: int,
    target_hex_r: int,
    db: AsyncSession,
) -> tuple[bool, str]:
    if not await has_any_connections(workspace_id, db):
        return True, "no_topology"

    card_q = await db.execute(
        select(NodeCard.hex_q, NodeCard.hex_r).where(
            NodeCard.node_id == caller_node_id,
            NodeCard.workspace_id == workspace_id,
            not_deleted(NodeCard),
        ).limit(1)
    )
    row = card_q.first()
    if row is None:
        return False, "caller_not_on_topology"

    reachable = await can_reach(
        workspace_id, row.hex_q, row.hex_r, target_hex_q, target_hex_r, db,
    )
    if not reachable:
        return False, "target_unreachable"
    return True, "ok"


async def check_blackboard_access(
    workspace_id: str, caller_node_id: str, db: AsyncSession,
) -> tuple[bool, str]:
    allowed, reason = await check_topology_access(workspace_id, caller_node_id, 0, 0, db)
    if not allowed and reason == "target_unreachable":
        reason = "blackboard_unreachable"
    return allowed, reason


async def get_reachable_names(
    workspace_id: str, instance_id: str, db: AsyncSession,
) -> list[str] | None:
    """Return display names of members reachable from *instance_id* via topology.

    Returns None when there is no topology (flat workspace) or when the agent
    has no hex coordinates, meaning all members are reachable and no prompt
    constraint should be injected.  Returns an empty list when the agent is
    positioned on the grid but has no reachable neighbors (isolated).
    """
    if not await has_any_connections(workspace_id, db):
        return None

    coords = await get_agent_hex_in_workspace(instance_id, workspace_id, db)
    if coords is None:
        return None

    endpoints, _hooks = await get_reachable_endpoints(
        workspace_id, coords[0], coords[1], db,
    )
    return [ep.display_name for ep in endpoints if ep.display_name]


async def get_topology(workspace_id: str, db: AsyncSession) -> Topology:
    hex_map = await _build_hex_map(workspace_id, db)

    conns_q = await db.execute(
        select(HexConnection).where(
            HexConnection.workspace_id == workspace_id,
            not_deleted(HexConnection),
        )
    )
    edges = [
        TopologyEdge(
            c.hex_a_q, c.hex_a_r, c.hex_b_q, c.hex_b_r,
            c.auto_created, direction=c.direction or "both",
        )
        for c in conns_q.scalars().all()
    ]

    return Topology(nodes=list(hex_map.values()), edges=edges)


async def has_any_connections(workspace_id: str, db: AsyncSession) -> bool:
    result = await db.execute(
        select(HexConnection.id).where(
            HexConnection.workspace_id == workspace_id,
            not_deleted(HexConnection),
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def has_no_connections(workspace_id: str, db: AsyncSession) -> bool:
    return not await has_any_connections(workspace_id, db)


async def get_all_addressable_nodes(
    workspace_id: str, db: AsyncSession,
) -> list[ReachableEndpoint]:
    """Fallback when no topology exists: return all addressable nodes."""
    hex_map = await _build_hex_map(workspace_id, db)
    return [
        ReachableEndpoint(
            node.hex_q, node.hex_r, node.node_type,
            node.entity_id or "",
            display_name=node.display_name or "",
        )
        for node in hex_map.values()
        if _is_addressable(node.node_type)
    ]


async def cascade_delete_connections(
    workspace_id: str, q: int, r: int, db: AsyncSession,
) -> None:
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
    workspace_id: str, db: AsyncSession,
) -> list[list[str]]:
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
    workspace_id: str, db: AsyncSession,
) -> list[str]:
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
    workspace_id: str, db: AsyncSession,
) -> list[MessageFlowPair]:
    agents_q = await db.execute(
        select(Instance.id, WorkspaceAgent.hex_q, WorkspaceAgent.hex_r).join(
            WorkspaceAgent,
            (WorkspaceAgent.instance_id == Instance.id) & (WorkspaceAgent.deleted_at.is_(None)),
        ).where(
            WorkspaceAgent.workspace_id == workspace_id,
            not_deleted(Instance),
        )
    )
    agent_hex: dict[str, tuple[int, int]] = {
        row.id: (row.hex_q, row.hex_r)
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
