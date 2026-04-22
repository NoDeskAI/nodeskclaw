"""RoutingMiddleware — generates a DeliveryPlan by invoking the topology-based corridor router."""

from __future__ import annotations

import logging

from app.services.runtime.messaging.delivery_plan import DeliveryPlan, DeliveryTarget
from app.services.runtime.messaging.pipeline import MessageMiddleware, NextFn, PipelineContext

logger = logging.getLogger(__name__)


async def _resolve_targets_by_name(
    names: list[str], workspace_id: str, db,
) -> list[DeliveryTarget]:
    """Resolve target names (display_name or node_id) to DeliveryTarget objects."""
    from app.models.base import not_deleted
    from app.models.node_card import NodeCard
    from app.services.runtime.registries.node_type_registry import NODE_TYPE_REGISTRY
    from sqlalchemy import case, or_, select

    targets: list[DeliveryTarget] = []
    seen_ids: set[str] = set()
    for name in names:
        stmt = (
            select(NodeCard)
            .where(
                NodeCard.workspace_id == workspace_id,
                not_deleted(NodeCard),
                or_(NodeCard.name == name, NodeCard.node_id == name),
            )
            .order_by(
                case((NodeCard.node_id == name, 0), else_=1),
                NodeCard.created_at.desc(),
            )
        )
        result = await db.execute(stmt)
        card = result.scalars().first()
        if card is None:
            logger.warning("Routing: target '%s' not found in workspace %s", name, workspace_id)
            continue
        if card.node_id in seen_ids:
            continue
        seen_ids.add(card.node_id)

        type_spec = NODE_TYPE_REGISTRY.get(card.node_type)
        transport = type_spec.transport if type_spec else ""
        targets.append(DeliveryTarget(
            node_id=card.node_id,
            node_type=card.node_type,
            transport=transport or "",
        ))
    return targets


def _endpoints_to_targets(endpoints) -> list[DeliveryTarget]:
    """Convert ReachableEndpoint list to deduplicated DeliveryTarget list."""
    from app.services.runtime.registries.node_type_registry import NODE_TYPE_REGISTRY

    targets: list[DeliveryTarget] = []
    seen: set[str] = set()
    for ep in endpoints:
        if ep.entity_id in seen:
            continue
        seen.add(ep.entity_id)
        type_spec = NODE_TYPE_REGISTRY.get(ep.endpoint_type)
        transport = type_spec.transport if type_spec else ""
        targets.append(DeliveryTarget(
            node_id=ep.entity_id,
            node_type=ep.endpoint_type,
            transport=transport or "",
        ))
    return targets


async def _resolve_broadcast(
    workspace_id: str, db, *, sender_id: str = "", sender_type: str = "",
    max_hops: int = 0, visited: list[str] | None = None,
) -> list[DeliveryTarget]:
    """BFS from sender (or fallback to all addressable) to find reachable endpoints."""
    from app.services.corridor_router import (
        get_all_addressable_nodes,
        get_reachable_endpoints,
        has_any_connections,
    )
    from app.services.runtime.messaging.envelope import SenderType
    from app.services.runtime.registries.node_type_registry import NODE_TYPE_REGISTRY

    has_topo = await has_any_connections(workspace_id, db)

    if has_topo and sender_id:
        from app.models.base import not_deleted
        from app.models.node_card import NodeCard
        from sqlalchemy import select

        src_q = await db.execute(
            select(NodeCard.hex_q, NodeCard.hex_r).where(
                NodeCard.node_id == sender_id,
                NodeCard.workspace_id == workspace_id,
                not_deleted(NodeCard),
            ).limit(1)
        )
        src_row = src_q.first()
        if src_row:
            visited_set = set(visited) if visited else None
            endpoints, _hooks = await get_reachable_endpoints(
                workspace_id, src_row.hex_q, src_row.hex_r, db,
                max_hops=max_hops, visited_ids=visited_set,
            )
            return _endpoints_to_targets(endpoints)
        else:
            if sender_type == SenderType.AGENT:
                logger.warning(
                    "Routing: agent %s has no hex in workspace %s, returning empty broadcast",
                    sender_id, workspace_id,
                )
                return []
            elif sender_type == SenderType.USER:
                visited_set = set(visited) if visited else None
                endpoints, _hooks = await get_reachable_endpoints(
                    workspace_id, 0, 0, db,
                    max_hops=max_hops, visited_ids=visited_set,
                )
                return _endpoints_to_targets(endpoints)

    addressable = await get_all_addressable_nodes(workspace_id, db)
    targets = []
    seen_ids: set[str] = set()
    for ep in addressable:
        if ep.entity_id in seen_ids:
            continue
        seen_ids.add(ep.entity_id)
        type_spec = NODE_TYPE_REGISTRY.get(ep.endpoint_type)
        if not (type_spec and type_spec.consumes):
            continue
        transport = type_spec.transport if type_spec else ""
        targets.append(DeliveryTarget(
            node_id=ep.entity_id,
            node_type=ep.endpoint_type,
            transport=transport or "",
        ))
    return targets


async def _resolve_anycast(
    workspace_id: str, db, *, sender_id: str = "", sender_type: str = "", max_hops: int = 0,
) -> list[DeliveryTarget]:
    """Select the single least-loaded reachable node that consumes messages."""
    import random

    from app.services.runtime.messaging.queue import get_queue_depth

    candidates = await _resolve_broadcast(
        workspace_id, db, sender_id=sender_id, sender_type=sender_type, max_hops=max_hops,
    )
    if not candidates:
        return []

    scored: list[tuple[int, DeliveryTarget]] = []
    for t in candidates:
        depth = await get_queue_depth(db, t.node_id)
        scored.append((depth, t))

    min_depth = min(d for d, _ in scored)
    best = [t for d, t in scored if d == min_depth]
    return [random.choice(best)]


def _simple_token_overlap(text_a: str, text_b: str) -> float:
    """Lightweight token-overlap similarity (no external embeddings needed)."""
    if not text_a or not text_b:
        return 0.0
    tokens_a = set(text_a.lower().split())
    tokens_b = set(text_b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    return len(intersection) / (len(tokens_a | tokens_b) or 1)


async def _apply_semantic_scoring(
    targets: list[DeliveryTarget],
    content: str,
    workspace_id: str,
    db,
) -> list[DeliveryTarget]:
    """Score and sort targets by relevance using topology + semantic similarity."""
    if not content or len(targets) <= 1:
        return targets

    from app.models.base import not_deleted
    from app.models.node_card import NodeCard
    from sqlalchemy import select

    scored: list[tuple[float, DeliveryTarget]] = []
    for target in targets:
        result = await db.execute(
            select(NodeCard.description, NodeCard.tags).where(
                NodeCard.node_id == target.node_id,
                NodeCard.workspace_id == workspace_id,
                not_deleted(NodeCard),
            )
        )
        row = result.first()
        description = (row[0] or "") if row else ""
        tags = (row[1] or []) if row else []
        tag_text = " ".join(str(t) for t in tags)
        node_text = f"{description} {tag_text}".strip()

        semantic_score = _simple_token_overlap(content, node_text)
        topology_score = 1.0
        relevance = topology_score * 0.6 + semantic_score * 0.4
        scored.append((relevance, target))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored]


class RoutingMiddleware(MessageMiddleware):
    async def process(self, ctx: PipelineContext, next_fn: NextFn) -> None:
        data = ctx.envelope.data
        if data is None:
            await next_fn(ctx)
            return

        db = ctx.db
        sender_id = data.sender.instance_id or data.sender.id
        max_hops = data.routing.ttl if data.routing.ttl > 0 else 0
        visited_list = data.routing.visited or []

        explicit_targets = data.routing.targets
        if not explicit_targets and data.routing.target:
            explicit_targets = [data.routing.target]

        routing_mode = data.routing.mode if hasattr(data.routing, "mode") and data.routing.mode else ""

        if explicit_targets:
            mode = "unicast" if len(explicit_targets) == 1 else "multicast"
            resolved: list[DeliveryTarget] = []
            if db is not None:
                resolved = await _resolve_targets_by_name(
                    explicit_targets, ctx.workspace_id, db,
                )
                resolved = await self._filter_unicast_by_topology(
                    resolved, ctx.workspace_id, data, db,
                )
            ctx.delivery_plan = DeliveryPlan(
                targets=explicit_targets,
                resolved_targets=resolved,
                mode=mode,
                workspace_id=ctx.workspace_id,
            )
        elif routing_mode == "anycast" and db is not None:
            resolved = await _resolve_anycast(
                ctx.workspace_id, db, sender_id=sender_id,
                sender_type=data.sender.type, max_hops=max_hops,
            )
            resolved = [t for t in resolved if t.node_id != sender_id]
            from app.services.runtime.route_cache import route_table
            topo_version = route_table.get_version(ctx.workspace_id)
            ctx.delivery_plan = DeliveryPlan(
                targets=[],
                resolved_targets=resolved,
                mode="anycast",
                workspace_id=ctx.workspace_id,
                topology_version=topo_version,
            )
        else:
            from app.services.runtime.route_cache import route_table

            resolved = route_table.get(ctx.workspace_id, sender_id)
            if resolved is None and db is not None:
                resolved = await _resolve_broadcast(
                    ctx.workspace_id, db,
                    sender_id=sender_id, sender_type=data.sender.type,
                    max_hops=max_hops, visited=visited_list,
                )
                route_table.put(ctx.workspace_id, resolved, sender_id)
            resolved = resolved or []
            resolved = [t for t in resolved if t.node_id != sender_id]

            topo_version = route_table.get_version(ctx.workspace_id)
            ctx.delivery_plan = DeliveryPlan(
                targets=[],
                resolved_targets=resolved,
                mode="broadcast",
                workspace_id=ctx.workspace_id,
                topology_version=topo_version,
            )

        if ctx.delivery_plan.resolved_targets and db is not None:
            ctx.delivery_plan.resolved_targets = await _apply_semantic_scoring(
                ctx.delivery_plan.resolved_targets,
                ctx.envelope.data.content if ctx.envelope.data else "",
                ctx.workspace_id,
                db,
            )

            ctx.delivery_plan.resolved_targets = await self._apply_backpressure(
                ctx.delivery_plan.resolved_targets, data.priority, db,
            )

        ctx.extra["backpressure_dropped"] = ctx.extra.get("backpressure_dropped", [])
        ctx.extra["hooks_to_fire"] = []
        if ctx.delivery_plan.mode in ("broadcast", "anycast") and db is not None:
            try:
                from app.services.corridor_router import get_reachable_endpoints

                from app.models.base import not_deleted
                from app.models.node_card import NodeCard
                from sqlalchemy import select

                src_q = await db.execute(
                    select(NodeCard.hex_q, NodeCard.hex_r).where(
                        NodeCard.node_id == sender_id,
                        NodeCard.workspace_id == ctx.workspace_id,
                        not_deleted(NodeCard),
                    ).limit(1)
                )
                src_row = src_q.first()
                if src_row:
                    visited_set = set(visited_list) if visited_list else None
                    _eps, hooks = await get_reachable_endpoints(
                        ctx.workspace_id, src_row.hex_q, src_row.hex_r, db,
                        max_hops=max_hops, visited_ids=visited_set,
                    )
                    ctx.extra["hooks_to_fire"] = [
                        {"node_id": h.node_id, "node_type": h.node_type, "hook": h.hook_name}
                        for h in hooks
                    ]
            except Exception as e:
                logger.warning("Failed to collect BFS hooks: %s", e)

        logger.debug(
            "Routing: mode=%s resolved=%d targets for envelope %s (hooks=%d)",
            ctx.delivery_plan.mode,
            len(ctx.delivery_plan.resolved_targets),
            ctx.envelope.id,
            len(ctx.extra.get("hooks_to_fire", [])),
        )

        await next_fn(ctx)

    @staticmethod
    async def _apply_backpressure(
        targets: list[DeliveryTarget],
        msg_priority,
        db,
    ) -> list[DeliveryTarget]:
        from app.services.runtime.messaging.envelope import Priority
        from app.services.runtime.messaging.queue import get_backpressure_level, get_queue_depth

        kept: list[DeliveryTarget] = []
        for t in targets:
            depth = await get_queue_depth(db, t.node_id)
            level = get_backpressure_level(depth)

            if level == "FULL":
                kept.append(t)
            elif level == "NORMAL_ONLY":
                if msg_priority != Priority.BACKGROUND:
                    kept.append(t)
            elif level == "CRITICAL_ONLY":
                if msg_priority == Priority.CRITICAL:
                    kept.append(t)
        return kept

    @staticmethod
    async def _filter_unicast_by_topology(
        resolved: list[DeliveryTarget],
        workspace_id: str,
        data,
        db,
    ) -> list[DeliveryTarget]:
        from app.services.runtime.messaging.envelope import IntentType, SenderType

        if not resolved or data.sender.type != SenderType.AGENT:
            return resolved

        if data.intent == IntentType.COLLABORATE:
            return resolved

        from app.services.corridor_router import get_reachable_endpoints, has_any_connections
        from app.models.base import not_deleted
        from app.models.node_card import NodeCard
        from sqlalchemy import select

        if not await has_any_connections(workspace_id, db):
            return resolved

        sender_id = data.sender.instance_id or data.sender.id
        src_q = await db.execute(
            select(NodeCard.hex_q, NodeCard.hex_r).where(
                NodeCard.node_id == sender_id,
                NodeCard.workspace_id == workspace_id,
                not_deleted(NodeCard),
            ).limit(1)
        )
        src_row = src_q.first()
        if src_row is None or src_row.hex_q is None or src_row.hex_r is None:
            logger.warning(
                "Routing: agent sender %s has no hex coordinates in workspace %s, skipping topology filter",
                sender_id, workspace_id,
            )
            return resolved

        endpoints, _hooks = await get_reachable_endpoints(
            workspace_id, src_row.hex_q, src_row.hex_r, db,
        )
        reachable_ids = {ep.entity_id for ep in endpoints}

        kept: list[DeliveryTarget] = []
        for t in resolved:
            if t.node_id in reachable_ids:
                kept.append(t)
            else:
                logger.warning(
                    "Routing: target %s unreachable from agent %s via topology, dropped",
                    t.node_id, sender_id,
                )
        return kept
