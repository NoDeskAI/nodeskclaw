"""Conversation service — topology-driven group chat management."""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import not_deleted
from app.models.conversation import Conversation
from app.services.corridor_router import _build_hex_map, _get_adjacency, TopologyNode

logger = logging.getLogger(__name__)


def _compute_member_hash(member_ids: list[str]) -> str:
    joined = ",".join(sorted(member_ids))
    return hashlib.sha256(joined.encode()).hexdigest()[:16]


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


def _generate_group_name(
    hub_nodes: list[TopologyNode],
    agent_nodes: list[TopologyNode],
    is_blackboard: bool,
) -> str:
    if is_blackboard:
        return "conversations.blackboardGroup"
    if hub_nodes:
        named = [n for n in hub_nodes if n.display_name]
        if named:
            return named[0].display_name + "群"
    return ", ".join(n.display_name or n.entity_id or "?" for n in agent_nodes)


async def sync_conversations_from_topology(
    workspace_id: str, db: AsyncSession,
) -> list[Conversation]:
    """Recompute all conversations from current topology using the 3-step algorithm."""

    hex_map = await _build_hex_map(workspace_id, db)
    adj = await _get_adjacency(workspace_id, db)

    hub_types = {"corridor", "blackboard"}
    hub_positions: set[tuple[int, int]] = set()
    agent_positions: set[tuple[int, int]] = set()

    for pos, node in hex_map.items():
        if node.node_type in hub_types:
            hub_positions.add(pos)
        elif node.node_type == "agent":
            agent_positions.add(pos)

    # --- Step 1: Hub-chain merge (Union-Find on hub subgraph) ---
    parent: dict[tuple[int, int], tuple[int, int]] = {p: p for p in hub_positions}

    def find(x: tuple[int, int]) -> tuple[int, int]:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: tuple[int, int], b: tuple[int, int]) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for pos in hub_positions:
        for neighbor in adj.get(pos, []):
            if neighbor in hub_positions:
                union(pos, neighbor)

    hub_chains: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for pos in hub_positions:
        hub_chains[find(pos)].append(pos)

    # --- Step 2: Hub Group generation ---
    computed_groups: list[dict] = []
    agent_covered_by: dict[tuple[int, int], list[int]] = defaultdict(list)

    for chain_root, chain_members in hub_chains.items():
        chain_set = set(chain_members)
        adjacent_agents: set[tuple[int, int]] = set()

        for hub_pos in chain_members:
            for neighbor in adj.get(hub_pos, []):
                if neighbor in agent_positions:
                    adjacent_agents.add(neighbor)
            for agent_pos in agent_positions:
                if hub_pos in set(adj.get(agent_pos, [])):
                    adjacent_agents.add(agent_pos)

        if len(adjacent_agents) < 2:
            continue

        is_blackboard = any(hex_map[p].node_type == "blackboard" for p in chain_members)
        hub_nodes = [hex_map[p] for p in chain_members]
        agent_nodes = [hex_map[p] for p in adjacent_agents]
        member_ids = sorted(hex_map[p].entity_id for p in adjacent_agents if hex_map[p].entity_id)

        group_idx = len(computed_groups)
        for ap in adjacent_agents:
            agent_covered_by[ap].append(group_idx)

        computed_groups.append({
            "member_ids": member_ids,
            "is_blackboard_group": is_blackboard,
            "name": _generate_group_name(hub_nodes, agent_nodes, is_blackboard),
        })

    # --- Step 3: Uncovered agent-agent edges ---
    uncovered_edges: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for agent_pos in agent_positions:
        for neighbor in adj.get(agent_pos, []):
            if neighbor not in agent_positions:
                continue
            if agent_pos >= neighbor:
                continue
            groups_a = set(agent_covered_by.get(agent_pos, []))
            groups_b = set(agent_covered_by.get(neighbor, []))
            if not (groups_a & groups_b):
                uncovered_edges.append((agent_pos, neighbor))

    if uncovered_edges:
        uf: dict[tuple[int, int], tuple[int, int]] = {}
        for a, b in uncovered_edges:
            uf.setdefault(a, a)
            uf.setdefault(b, b)

        def find_uf(x: tuple[int, int]) -> tuple[int, int]:
            while uf[x] != x:
                uf[x] = uf[uf[x]]
                x = uf[x]
            return x

        def union_uf(a: tuple[int, int], b: tuple[int, int]) -> None:
            ra, rb = find_uf(a), find_uf(b)
            if ra != rb:
                uf[ra] = rb

        for a, b in uncovered_edges:
            union_uf(a, b)

        components: dict[tuple[int, int], set[tuple[int, int]]] = defaultdict(set)
        for pos in uf:
            components[find_uf(pos)].add(pos)

        for _root, members in components.items():
            if len(members) < 2:
                continue
            agent_nodes = [hex_map[p] for p in members]
            member_ids = sorted(hex_map[p].entity_id for p in members if hex_map[p].entity_id)
            computed_groups.append({
                "member_ids": member_ids,
                "is_blackboard_group": False,
                "name": _generate_group_name([], agent_nodes, False),
            })

    # --- Match with existing conversations ---
    existing_q = await db.execute(
        select(Conversation).where(
            Conversation.workspace_id == workspace_id,
            not_deleted(Conversation),
        )
    )
    existing_convs = list(existing_q.scalars().all())

    # Build entity_id -> display_name mapping for system messages
    entity_name_map: dict[str, str] = {}
    for node in hex_map.values():
        if node.entity_id and node.display_name:
            entity_name_map[node.entity_id] = node.display_name

    all_old_entity_ids: set[str] = set()
    for conv in existing_convs:
        all_old_entity_ids.update(conv.member_node_ids or [])
    missing_ids = all_old_entity_ids - set(entity_name_map.keys())
    if missing_ids:
        from app.models.instance import Instance
        inst_q = await db.execute(
            select(Instance.id, Instance.name).where(Instance.id.in_(list(missing_ids)))
        )
        for inst_id, inst_name in inst_q.all():
            entity_name_map[inst_id] = inst_name

    existing_bb = None
    existing_non_bb: list[Conversation] = []
    for conv in existing_convs:
        if conv.is_blackboard_group:
            existing_bb = conv
        else:
            existing_non_bb.append(conv)

    matched_existing_ids: set[str] = set()
    result_conversations: list[Conversation] = []
    membership_changes: list[tuple[Conversation, set[str], set[str]]] = []

    for group in computed_groups:
        member_ids = group["member_ids"]
        member_hash = _compute_member_hash(member_ids)
        is_bb = group["is_blackboard_group"]
        name = group["name"]

        if is_bb and existing_bb:
            old_set = set(existing_bb.member_node_ids or [])
            existing_bb.member_node_ids = member_ids
            existing_bb.member_hash = member_hash
            existing_bb.name = name
            matched_existing_ids.add(existing_bb.id)
            result_conversations.append(existing_bb)
            new_set = set(member_ids)
            joined = new_set - old_set
            left = old_set - new_set
            if joined or left:
                membership_changes.append((existing_bb, joined, left))
            continue

        best_match: Conversation | None = None
        best_score = 0.0
        new_set = set(member_ids)

        for conv in existing_non_bb:
            if conv.id in matched_existing_ids:
                continue
            old_set = set(conv.member_node_ids or [])
            score = _jaccard(new_set, old_set)
            if score > best_score:
                best_score = score
                best_match = conv

        if best_match and best_score > 0:
            old_set = set(best_match.member_node_ids or [])
            best_match.member_node_ids = member_ids
            best_match.member_hash = member_hash
            best_match.name = name
            best_match.is_blackboard_group = is_bb
            matched_existing_ids.add(best_match.id)
            result_conversations.append(best_match)
            joined = new_set - old_set
            left = old_set - new_set
            if joined or left:
                membership_changes.append((best_match, joined, left))
        else:
            conv = Conversation(
                workspace_id=workspace_id,
                name=name,
                is_blackboard_group=is_bb,
                member_node_ids=member_ids,
                member_hash=member_hash,
            )
            db.add(conv)
            result_conversations.append(conv)

    for conv in existing_convs:
        if conv.id not in matched_existing_ids:
            left = set(conv.member_node_ids or [])
            if left:
                membership_changes.append((conv, set(), left))
            conv.soft_delete()

    # Generate system messages for membership changes
    from app.models.workspace_message import WorkspaceMessage

    broadcast_payloads: list[dict] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for conv, joined, left in membership_changes:
        parts: list[str] = []
        if joined:
            names = ", ".join(entity_name_map.get(eid, eid) for eid in sorted(joined))
            parts.append(f"{names} 加入了群聊")
        if left:
            names = ", ".join(entity_name_map.get(eid, eid) for eid in sorted(left))
            parts.append(f"{names} 离开了群聊")
        content = "; ".join(parts)

        msg = WorkspaceMessage(
            workspace_id=workspace_id,
            sender_type="system",
            sender_id="system",
            sender_name="System",
            content=content,
            message_type="system",
            conversation_id=conv.id,
        )
        db.add(msg)
        conv.last_message_at = func.now()
        conv.last_message_preview = content[:100]

        broadcast_payloads.append({
            "id": msg.id,
            "sender_type": "system",
            "sender_id": "system",
            "sender_name": "System",
            "content": content,
            "message_type": "system",
            "conversation_id": conv.id,
            "created_at": now_iso,
        })

    await db.flush()

    if broadcast_payloads:
        from app.api.workspaces import broadcast_event
        for payload in broadcast_payloads:
            broadcast_event(workspace_id, "system:info", payload)

    return result_conversations


async def get_blackboard_conversation(
    workspace_id: str, db: AsyncSession,
) -> Conversation | None:
    result = await db.execute(
        select(Conversation).where(
            Conversation.workspace_id == workspace_id,
            Conversation.is_blackboard_group.is_(True),
            not_deleted(Conversation),
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def list_conversations(
    workspace_id: str, db: AsyncSession,
) -> list[Conversation]:
    result = await db.execute(
        select(Conversation).where(
            Conversation.workspace_id == workspace_id,
            not_deleted(Conversation),
        ).order_by(
            Conversation.is_blackboard_group.desc(),
            Conversation.last_message_at.desc().nulls_last(),
        )
    )
    return list(result.scalars().all())


async def resolve_conversation_for_message(
    workspace_id: str,
    sender_id: str,
    target_id: str,
    db: AsyncSession,
    *,
    inherited_conversation_id: str | None = None,
) -> str | None:
    """Determine which conversation a message belongs to.

    Priority:
    1. inherited_conversation_id if target is a member of that conversation
    2. Common conversation between sender and target (tiebreaker: blackboard first, then most recent)
    3. Target's conversation (cross-group delegation)
    4. Fallback to blackboard conversation
    """
    all_convs_q = await db.execute(
        select(Conversation).where(
            Conversation.workspace_id == workspace_id,
            not_deleted(Conversation),
        )
    )
    all_convs = list(all_convs_q.scalars().all())

    sender_convs: list[Conversation] = []
    target_convs: list[Conversation] = []
    blackboard_conv: Conversation | None = None

    for conv in all_convs:
        members = conv.member_node_ids or []
        if sender_id in members:
            sender_convs.append(conv)
        if target_id in members:
            target_convs.append(conv)
        if conv.is_blackboard_group:
            blackboard_conv = conv

    if inherited_conversation_id:
        for conv in target_convs:
            if conv.id == inherited_conversation_id:
                return conv.id

    sender_conv_ids = {c.id for c in sender_convs}
    common = [c for c in target_convs if c.id in sender_conv_ids]

    if common:
        common.sort(key=lambda c: (
            not c.is_blackboard_group,
            c.last_message_at is None,
            c.last_message_at,
        ), reverse=False)
        best = min(common, key=lambda c: (
            not c.is_blackboard_group,
            c.last_message_at is None,
        ))
        return best.id

    if target_convs:
        target_convs.sort(key=lambda c: (
            not c.is_blackboard_group,
            c.last_message_at is None,
        ))
        return target_convs[0].id

    if blackboard_conv:
        return blackboard_conv.id

    return None


async def get_conversation_members(
    conversation_id: str, db: AsyncSession,
) -> list[str]:
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            not_deleted(Conversation),
        ).limit(1)
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        return []
    return conv.member_node_ids or []
