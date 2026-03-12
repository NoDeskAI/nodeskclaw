"""NodeTypeRegistry — central registry for all node type definitions in the runtime platform."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import not_deleted

logger = logging.getLogger(__name__)


class RoutingRole(str, Enum):
    SINK = "sink"
    RELAY = "relay"
    SENSOR = "sensor"
    GATEWAY = "gateway"
    TRANSFORMER = "transformer"
    FILTER = "filter"


@dataclass(frozen=True)
class NodeTypeDefinitionSpec:
    type_id: str
    routing_role: RoutingRole
    transport: str | None = None
    card_schema: dict | None = None
    hooks: list[str] = field(default_factory=list)
    propagates: bool = False
    consumes: bool = False
    is_addressable: bool = True
    can_originate: bool = False
    description: str | None = None


class NodeTypeRegistry:
    def __init__(self) -> None:
        self._types: dict[str, NodeTypeDefinitionSpec] = {}

    def register(self, spec: NodeTypeDefinitionSpec) -> None:
        self._types[spec.type_id] = spec
        logger.debug("Registered node type: %s (role=%s)", spec.type_id, spec.routing_role.value)

    def get(self, type_id: str) -> NodeTypeDefinitionSpec | None:
        return self._types.get(type_id)

    def all_types(self) -> list[NodeTypeDefinitionSpec]:
        return list(self._types.values())

    def all_terminal_roles(self) -> list[str]:
        return [t.type_id for t in self._types.values() if t.consumes and not t.propagates]

    def all_relay_roles(self) -> list[str]:
        return [t.type_id for t in self._types.values() if t.propagates]

    def get_transport(self, type_id: str) -> str | None:
        spec = self._types.get(type_id)
        return spec.transport if spec else None

    def get_hooks(self, type_id: str) -> list[str]:
        spec = self._types.get(type_id)
        return list(spec.hooks) if spec else []

    def is_registered(self, type_id: str) -> bool:
        return type_id in self._types

    async def sync_to_db(self, db: AsyncSession) -> None:
        from app.models.node_type import NodeTypeDefinition

        for spec in self._types.values():
            result = await db.execute(
                select(NodeTypeDefinition).where(
                    NodeTypeDefinition.type_id == spec.type_id,
                    not_deleted(NodeTypeDefinition),
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.routing_role = spec.routing_role.value
                existing.transport = spec.transport
                existing.card_schema = spec.card_schema
                existing.hooks = spec.hooks
                existing.propagates = spec.propagates
                existing.consumes = spec.consumes
                existing.is_addressable = spec.is_addressable
                existing.can_originate = spec.can_originate
                existing.description = spec.description
            else:
                db.add(NodeTypeDefinition(
                    type_id=spec.type_id,
                    routing_role=spec.routing_role.value,
                    transport=spec.transport,
                    card_schema=spec.card_schema,
                    hooks=spec.hooks,
                    propagates=spec.propagates,
                    consumes=spec.consumes,
                    is_addressable=spec.is_addressable,
                    can_originate=spec.can_originate,
                    description=spec.description,
                ))
        await db.flush()

    async def load_from_db(self, db: AsyncSession) -> None:
        from app.models.node_type import NodeTypeDefinition

        result = await db.execute(
            select(NodeTypeDefinition).where(not_deleted(NodeTypeDefinition))
        )
        for row in result.scalars().all():
            spec = NodeTypeDefinitionSpec(
                type_id=row.type_id,
                routing_role=RoutingRole(row.routing_role),
                transport=row.transport,
                card_schema=row.card_schema,
                hooks=row.hooks or [],
                propagates=row.propagates,
                consumes=row.consumes,
                is_addressable=row.is_addressable,
                can_originate=row.can_originate,
                description=row.description,
            )
            self._types[spec.type_id] = spec


NODE_TYPE_REGISTRY = NodeTypeRegistry()

NODE_TYPE_REGISTRY.register(NodeTypeDefinitionSpec(
    type_id="agent",
    routing_role=RoutingRole.SINK,
    transport="agent",
    propagates=False,
    consumes=True,
    is_addressable=True,
    can_originate=True,
    hooks=["on_message_received"],
    description="AI agent node backed by a runtime (OpenClaw, ZeroClaw, Nanobot, etc.)",
))

NODE_TYPE_REGISTRY.register(NodeTypeDefinitionSpec(
    type_id="human",
    routing_role=RoutingRole.SINK,
    transport="channel",
    propagates=False,
    consumes=True,
    is_addressable=True,
    can_originate=True,
    hooks=["on_message_received"],
    description="Human operator node connected via a channel (SSE, Feishu, etc.)",
))

NODE_TYPE_REGISTRY.register(NodeTypeDefinitionSpec(
    type_id="corridor",
    routing_role=RoutingRole.RELAY,
    propagates=True,
    consumes=False,
    is_addressable=False,
    can_originate=False,
    description="Corridor relay node that forwards messages along the topology.",
))

NODE_TYPE_REGISTRY.register(NodeTypeDefinitionSpec(
    type_id="blackboard",
    routing_role=RoutingRole.SENSOR,
    propagates=True,
    consumes=False,
    is_addressable=True,
    can_originate=True,
    hooks=["on_message_passing"],
    description="Shared blackboard node providing workspace-wide context.",
))
