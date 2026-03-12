"""Runtime Admin API — node type registration, transport adapters, registry inspection."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_org, get_db
from app.services.runtime.registries.node_type_registry import NODE_TYPE_REGISTRY
from app.services.runtime.registries.transport_registry import TRANSPORT_REGISTRY
from app.services.runtime.registries.runtime_registry import RUNTIME_REGISTRY
from app.services.runtime.registries.compute_registry import COMPUTE_REGISTRY
from app.services.runtime.registries.context_bridge_registry import CONTEXT_BRIDGE_REGISTRY
from app.services.runtime.registries.channel_registry import CHANNEL_REGISTRY

logger = logging.getLogger(__name__)
router = APIRouter()


def _ok(data: Any = None, message: str = "success"):
    return {"code": 0, "message": message, "data": data}


@router.get("/node-types")
async def list_node_types(org_ctx=Depends(get_current_org)):
    types = []
    for spec in NODE_TYPE_REGISTRY.all_types():
        types.append({
            "type_id": spec.type_id,
            "routing_role": spec.routing_role.value,
            "transport": spec.transport,
            "propagates": spec.propagates,
            "consumes": spec.consumes,
            "is_addressable": spec.is_addressable,
            "can_originate": spec.can_originate,
            "description": spec.description,
        })
    return _ok(types)


class RegisterNodeTypeRequest(BaseModel):
    type_id: str
    routing_role: str
    transport: str = "agent"
    propagates: bool = False
    consumes: bool = True
    is_addressable: bool = True
    can_originate: bool = False
    description: str = ""
    card_schema: dict | None = None
    hooks: list[str] | None = None


@router.post("/node-types")
async def register_node_type(
    body: RegisterNodeTypeRequest,
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    from app.services.runtime.registries.node_type_registry import (
        NodeTypeDefinitionSpec,
        RoutingRole,
    )

    if NODE_TYPE_REGISTRY.is_registered(body.type_id):
        return _ok(message=f"node type '{body.type_id}' already registered")

    try:
        role = RoutingRole(body.routing_role)
    except ValueError:
        return {"code": 1, "message": f"invalid routing_role: {body.routing_role}", "data": None}

    spec = NodeTypeDefinitionSpec(
        type_id=body.type_id,
        routing_role=role,
        transport=body.transport,
        card_schema=body.card_schema or {},
        hooks=body.hooks or [],
        propagates=body.propagates,
        consumes=body.consumes,
        is_addressable=body.is_addressable,
        can_originate=body.can_originate,
        description=body.description,
    )
    NODE_TYPE_REGISTRY.register(spec)
    await NODE_TYPE_REGISTRY.sync_to_db(db)
    await db.commit()
    return _ok({"type_id": body.type_id})


@router.get("/transport-adapters")
async def list_transport_adapters(org_ctx=Depends(get_current_org)):
    adapters = []
    for spec in TRANSPORT_REGISTRY.all_transports():
        adapters.append({
            "transport_id": spec.transport_id,
            "description": spec.description,
        })
    return _ok(adapters)


@router.get("/runtime-adapters")
async def list_runtime_adapters(org_ctx=Depends(get_current_org)):
    runtimes = []
    for spec in RUNTIME_REGISTRY.all_runtimes():
        runtimes.append({
            "runtime_id": spec.runtime_id,
            "description": spec.description,
            "display_name": spec.display_name,
            "display_description": spec.display_description,
            "display_tags": list(spec.display_tags),
            "display_powered_by": spec.display_powered_by,
            "order": spec.order,
        })
    runtimes.sort(key=lambda r: r["order"])
    return _ok(runtimes)


@router.get("/compute-providers")
async def list_compute_providers(org_ctx=Depends(get_current_org)):
    providers = []
    for spec in COMPUTE_REGISTRY.all_providers():
        providers.append({
            "compute_id": spec.compute_id,
            "description": spec.description,
        })
    return _ok(providers)


@router.get("/context-bridges")
async def list_context_bridges(org_ctx=Depends(get_current_org)):
    bridges = []
    for spec in CONTEXT_BRIDGE_REGISTRY.all_bridges():
        bridges.append({
            "bridge_id": spec.bridge_id,
            "description": spec.description,
        })
    return _ok(bridges)


@router.get("/channels")
async def list_channels(org_ctx=Depends(get_current_org)):
    channels = []
    for spec in CHANNEL_REGISTRY.all_channels():
        channels.append({
            "channel_id": spec.channel_id,
            "description": spec.description,
        })
    return _ok(channels)


@router.get("/hooks")
async def list_hooks(org_ctx=Depends(get_current_org)):
    from app.services.runtime.hooks.manager import node_hook_manager

    global_events = list(node_hook_manager._global_hooks.keys())
    type_events: dict[str, list[str]] = {}
    for node_type, events in node_hook_manager._type_hooks.items():
        type_events[node_type] = list(events.keys())

    return _ok({
        "global_events": global_events,
        "type_events": type_events,
    })


@router.get("/middleware-pipeline")
async def get_pipeline_info(org_ctx=Depends(get_current_org)):
    from app.services.runtime.messaging.bus import MessageBus

    bus = MessageBus()
    middlewares = [
        type(m).__name__
        for m in bus._pipeline._middlewares
    ]
    return _ok({"middlewares": middlewares})
