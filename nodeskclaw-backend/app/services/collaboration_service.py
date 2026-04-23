"""Collaboration message handling — shared by tunnel and (legacy) webhook."""

import asyncio
import logging
from typing import Coroutine

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import async_session_factory
from app.models.base import not_deleted
from app.models.corridor import HumanHex
from app.models.instance import Instance
from app.models.workspace import Workspace
from app.models.workspace_agent import WorkspaceAgent
from app.services import workspace_message_service as msg_service
from app.services import workspace_service

logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task] = set()


def _fire_task(coro: Coroutine) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


async def handle_collaboration_event(instance_id: str, payload: dict) -> None:
    """Entry point for tunnel-originated collaboration messages."""
    await handle_collaboration_message(
        workspace_id=payload.get("workspace_id", ""),
        source_instance_id=payload.get("source_instance_id", instance_id),
        target=payload.get("target", ""),
        text=payload.get("text", ""),
        depth=payload.get("depth", 0),
    )


async def handle_collaboration_message(
    *,
    workspace_id: str,
    source_instance_id: str,
    target: str,
    text: str,
    depth: int = 0,
) -> None:
    """Process an inbound collaboration message from a channel plugin.

    Routes all messages through the MessageBus pipeline for unified processing.
    Channel plugins cannot track session depth, so when depth=0 (the default
    from plugins), we derive the actual chain depth from recent DB messages.
    """
    if depth > msg_service.ABSOLUTE_MAX_COLLABORATION_DEPTH:
        logger.warning(
            "Collaboration depth exceeded absolute max (%d > %d) from instance %s",
            depth,
            msg_service.ABSOLUTE_MAX_COLLABORATION_DEPTH,
            source_instance_id,
        )
        return

    async with async_session_factory() as db:
        limit = await msg_service.get_collaboration_depth_limit(db, workspace_id)

        if depth == 0:
            inferred = await _infer_chain_depth(db, workspace_id, source_instance_id)
            if inferred is not None:
                depth = inferred

        if depth > limit:
            logger.warning(
                "Collaboration depth exceeded (%d > %d) from instance %s",
                depth, limit, source_instance_id,
            )
            return

        source_inst = await _get_instance(db, source_instance_id)
        if source_inst is None:
            logger.warning("Source instance not found: %s", source_instance_id)
            return

        source_name = source_inst.agent_display_name or source_inst.name

        resolved_target_id: str | None = None
        if target.startswith("agent:"):
            target_inst = await _find_agent_by_name_or_id(db, workspace_id, target[6:])
            if target_inst:
                resolved_target_id = target_inst.id
                from app.services import corridor_router
                target_hex = await corridor_router.get_agent_hex_in_workspace(
                    target_inst.id, workspace_id, db,
                )
                if target_hex is not None:
                    allowed, reason = await corridor_router.check_topology_access(
                        workspace_id, source_instance_id,
                        target_hex[0], target_hex[1], db,
                    )
                    if not allowed:
                        from app.api.workspaces import broadcast_event
                        broadcast_event(workspace_id, "agent:topology_blocked", {
                            "source_instance_id": source_instance_id,
                            "source_name": source_name,
                            "target": target,
                            "reason": reason,
                        })
                        return
        elif target.startswith("human:"):
            human_name = target[6:]
            hh = await _find_human_by_display_name(db, workspace_id, human_name)
            if hh:
                await msg_service.record_message(
                    db,
                    workspace_id=workspace_id,
                    sender_type="agent",
                    sender_id=source_instance_id,
                    sender_name=source_name,
                    content=text,
                    message_type="collaboration",
                    depth=depth,
                )
                from app.api.workspaces import broadcast_event
                broadcast_event(workspace_id, "agent:collaboration", {
                    "instance_id": source_instance_id,
                    "agent_name": source_name,
                    "target": target,
                    "content": text,
                })
                await _route_to_human(
                    db, workspace_id, source_instance_id, source_name, hh, text,
                )
                await db.commit()
                return
            else:
                logger.warning("Human target not found: %s in workspace %s", human_name, workspace_id)

        await msg_service.record_message(
            db,
            workspace_id=workspace_id,
            sender_type="agent",
            sender_id=source_instance_id,
            sender_name=source_name,
            content=text,
            message_type="collaboration",
            target_instance_id=resolved_target_id,
            depth=depth,
        )

        from app.api.workspaces import broadcast_event
        broadcast_event(workspace_id, "agent:collaboration", {
            "instance_id": source_instance_id,
            "agent_name": source_name,
            "target": target,
            "content": text,
        })

        from app.services.runtime.messaging.bus import message_bus
        from app.services.runtime.messaging.ingestion.agent import build_agent_collaboration_envelope

        envelope = build_agent_collaboration_envelope(
            workspace_id=workspace_id,
            source_instance_id=source_instance_id,
            source_name=source_name,
            target=target,
            content=text,
            depth=depth,
        )

        result = await message_bus.publish(envelope, db=db)
        await db.commit()
        if result.error:
            logger.error("MessageBus error in collaboration: %s", result.error)


async def _infer_chain_depth(
    db: AsyncSession, workspace_id: str, source_instance_id: str,
) -> int | None:
    """Derive collaboration chain depth from the most recent message TO this agent.

    When a collaboration message was recently delivered to *source_instance_id*,
    the current outbound message is a reply in the same chain, so depth should be
    previous_depth + 1.  Returns None if there is no recent inbound message
    (i.e. this is a brand-new conversation, depth stays 0).
    """
    from datetime import datetime as _dt, timedelta, timezone

    from app.models.workspace_message import WorkspaceMessage

    cutoff = _dt.now(timezone.utc) - timedelta(seconds=120)
    result = await db.execute(
        select(WorkspaceMessage.depth)
        .where(
            WorkspaceMessage.workspace_id == workspace_id,
            WorkspaceMessage.message_type == "collaboration",
            WorkspaceMessage.target_instance_id == source_instance_id,
            WorkspaceMessage.created_at >= cutoff,
            WorkspaceMessage.deleted_at.is_(None),
        )
        .order_by(WorkspaceMessage.created_at.desc())
        .limit(1)
    )
    last_depth = result.scalar_one_or_none()
    if last_depth is not None:
        return last_depth + 1
    return None


async def _route_to_human(
    db: AsyncSession,
    workspace_id: str,
    source_instance_id: str,
    source_name: str,
    hh: HumanHex,
    text: str,
) -> None:
    from app.services import corridor_router
    has_topo = await corridor_router.has_any_connections(workspace_id, db)
    src_hex = await corridor_router.get_agent_hex_in_workspace(
        source_instance_id, workspace_id, db,
    ) if has_topo else None
    if has_topo and src_hex is not None:
        can = await corridor_router.can_reach(
            workspace_id,
            src_hex[0], src_hex[1],
            hh.hex_q, hh.hex_r,
            db,
        )
        if not can:
            logger.info(
                "Corridor topology blocks %s -> human:%s",
                source_name, hh.display_name or hh.id,
            )
            return
    _fire_task(deliver_to_human(
        workspace_id=workspace_id,
        human_hex_id=hh.id,
        source_name=source_name,
        message=text,
    ))


# ── Human delivery ────────────────────────────────────


async def deliver_to_human(
    *,
    workspace_id: str,
    human_hex_id: str,
    source_name: str,
    message: str,
) -> None:
    """Deliver a message to a Human Hex via Feishu (or SSE fallback)."""
    from app.api.workspaces import broadcast_event
    from app.core.config import settings

    async with async_session_factory() as db:
        human_hex = await _get_human_hex(db, human_hex_id)
        if not human_hex:
            logger.warning("Human hex not found for delivery: %s", human_hex_id)
            return

        ws_q = await db.execute(
            select(Workspace.name).where(Workspace.id == workspace_id, not_deleted(Workspace))
        )
        workspace_name = ws_q.scalar_one_or_none() or "Unknown"

        receive_id: str | None = None
        receive_id_type: str | None = None

        channel_config = human_hex.channel_config or {}
        if human_hex.channel_type == "feishu" and channel_config.get("chat_id"):
            receive_id = channel_config["chat_id"]
            receive_id_type = "chat_id"
        else:
            from app.services.channel_adapters.feishu import get_feishu_open_id
            open_id = await get_feishu_open_id(human_hex.user_id, db)
            if open_id:
                receive_id = open_id
                receive_id_type = "open_id"

    delivered_via = "sse"
    if receive_id and receive_id_type and settings.FEISHU_APP_ID_PORTAL:
        from app.services.channel_adapters.feishu import (
            FeishuChannelAdapter,
            build_workspace_message_card,
        )

        adapter = FeishuChannelAdapter(
            app_id=settings.FEISHU_APP_ID_PORTAL,
            app_secret=settings.FEISHU_APP_SECRET_PORTAL,
        )
        card = build_workspace_message_card(
            workspace_name=workspace_name,
            workspace_id=workspace_id,
            source_name=source_name,
            content=message,
            human_hex_name=human_hex.display_name or "",
            portal_base_url=settings.PORTAL_BASE_URL,
        )
        ok = await adapter.send_card(
            receive_id=receive_id,
            receive_id_type=receive_id_type,
            card_content=card,
            workspace_id=workspace_id,
        )
        if ok:
            delivered_via = f"feishu:{receive_id_type}"
        else:
            logger.warning(
                "Feishu delivery failed for human_hex=%s, falling back to SSE",
                human_hex_id,
            )

    broadcast_event(workspace_id, "human:message_delivered", {
        "human_hex_id": human_hex_id,
        "user_id": human_hex.user_id if human_hex else "",
        "source_name": source_name,
        "content": message[:200],
        "delivered_via": delivered_via,
    })


# ── DB helpers ────────────────────────────────────────


async def _get_human_hex(db: AsyncSession, human_hex_id: str) -> HumanHex | None:
    result = await db.execute(
        select(HumanHex).where(
            HumanHex.id == human_hex_id,
            not_deleted(HumanHex),
        )
    )
    return result.scalar_one_or_none()


async def _find_human_by_display_name(
    db: AsyncSession, workspace_id: str, name: str,
) -> HumanHex | None:
    result = await db.execute(
        select(HumanHex).where(
            HumanHex.workspace_id == workspace_id,
            not_deleted(HumanHex),
        )
    )
    rows = result.scalars().all()
    name_lower = name.lower()
    for hh in rows:
        if (hh.display_name or "").lower() == name_lower:
            return hh
    return None


def looks_like_uuid(s: str) -> bool:
    return len(s) == 36 and s.count("-") == 4


_looks_like_uuid = looks_like_uuid


async def _get_instance(db: AsyncSession, instance_id: str) -> Instance | None:
    result = await db.execute(
        select(Instance).where(
            Instance.id == instance_id,
            Instance.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def find_agent_by_name_or_id(
    db: AsyncSession, workspace_id: str, identifier: str,
) -> Instance | None:
    result = await db.execute(
        select(Instance, WorkspaceAgent).join(
            WorkspaceAgent,
            (WorkspaceAgent.instance_id == Instance.id) & (WorkspaceAgent.deleted_at.is_(None)),
        ).where(
            WorkspaceAgent.workspace_id == workspace_id,
            Instance.status == "running",
            Instance.deleted_at.is_(None),
        )
    )
    rows = result.all()
    if _looks_like_uuid(identifier):
        for inst, wa in rows:
            if inst.id == identifier:
                return inst
    id_lower = identifier.lower()
    for inst, wa in rows:
        display = (wa.display_name or inst.name) if wa else (inst.agent_display_name or inst.name)
        if display.lower() == id_lower or inst.name.lower() == id_lower:
            return inst
    return None


_find_agent_by_name_or_id = find_agent_by_name_or_id


async def _get_workspace_agents(db: AsyncSession, workspace_id: str) -> list[Instance]:
    result = await db.execute(
        select(Instance, WorkspaceAgent).join(
            WorkspaceAgent,
            (WorkspaceAgent.instance_id == Instance.id) & (WorkspaceAgent.deleted_at.is_(None)),
        ).where(
            WorkspaceAgent.workspace_id == workspace_id,
            Instance.status == "running",
            Instance.deleted_at.is_(None),
        )
    )
    return [row[0] for row in result.all()]


async def _invoke_target_agent(
    *,
    workspace_id: str,
    target_instance: Instance,
    source_name: str,
    source_instance_id: str,
    message: str,
    depth: int,
) -> bool:
    """Invoke a target agent with a collaboration message via tunnel. Returns True on success."""
    from app.api.workspaces import broadcast_event
    from app.services.tunnel import tunnel_adapter
    from app.services.tunnel.protocol import TunnelMessageType

    agent_name = target_instance.agent_display_name or target_instance.name
    instance_id = target_instance.id

    if instance_id not in tunnel_adapter.connected_instances:
        logger.warning("Target agent %s not connected via tunnel", agent_name)
        return False

    async with async_session_factory() as db:
        ws_info = await workspace_service.get_workspace(db, workspace_id)
        recent_messages = await msg_service.get_recent_messages(db, workspace_id)
        from app.services.corridor_router import get_reachable_names
        reachable = await get_reachable_names(workspace_id, instance_id, db)

    members: list[dict] = []
    if ws_info and ws_info.agents:
        for a in ws_info.agents:
            members.append({
                "type": "AI 员工",
                "name": a.display_name or a.name,
                "id": a.instance_id,
            })

    context_prompt = msg_service.build_context_prompt(
        workspace_name=ws_info.name if ws_info else "Unknown",
        agent_display_name=agent_name,
        current_instance_id=instance_id,
        members=members,
        recent_messages=recent_messages,
        workspace_id=workspace_id,
        reachable_names=reachable,
    )

    messages_payload = [
        {"role": "system", "content": context_prompt},
        {"role": "user", "content": f"[{source_name} -> you]: {message}"},
    ]

    broadcast_event(workspace_id, "agent:typing", {
        "instance_id": instance_id,
        "agent_name": agent_name,
    })

    full_response = ""
    buffer = ""
    flushed = False

    try:
        chat_stream = await tunnel_adapter.send_chat_request(
            instance_id, messages_payload,
            workspace_id=workspace_id,
            stream=True,
        )
        async for chunk_msg in chat_stream:
            if chunk_msg.type == TunnelMessageType.CHAT_RESPONSE_ERROR:
                raw_error = chunk_msg.payload.get("error", "unknown")
                err_type = chunk_msg.payload.get("error_type")
                logger.error("Target agent %s returned error: %s", agent_name, raw_error)
                error_code = "llm_error" if err_type == "llm" else "stream_error"
                evt: dict = {
                    "instance_id": instance_id,
                    "agent_name": agent_name,
                    "error": error_code,
                    "error_detail": str(raw_error)[:256],
                }
                raw_body = chunk_msg.payload.get("error_raw")
                if raw_body:
                    evt["error_raw"] = str(raw_body)[:2048]
                broadcast_event(workspace_id, "agent:error", evt)
                return False
            if chunk_msg.type == TunnelMessageType.CHAT_RESPONSE_DONE:
                break
            content = chunk_msg.payload.get("content", "")
            if not content:
                continue

            full_response += content

            if not flushed:
                buffer += content
                if len(buffer) > 20:
                    if msg_service.is_no_reply(buffer.strip()):
                        broadcast_event(workspace_id, "agent:done", {
                            "instance_id": instance_id,
                            "agent_name": agent_name,
                        })
                        return True
                    broadcast_event(workspace_id, "agent:chunk", {
                        "instance_id": instance_id,
                        "agent_name": agent_name,
                        "content": buffer,
                    })
                    flushed = True
            else:
                broadcast_event(workspace_id, "agent:chunk", {
                    "instance_id": instance_id,
                    "agent_name": agent_name,
                    "content": content,
                })
    except Exception as e:
        logger.error("Target agent %s streaming failed: %s", agent_name, e)
        broadcast_event(workspace_id, "agent:error", {
            "instance_id": instance_id,
            "agent_name": agent_name,
            "error": "stream_error",
            "error_detail": str(e)[:256],
        })
        return False

    if not flushed and buffer:
        if msg_service.is_no_reply(buffer.strip()):
            broadcast_event(workspace_id, "agent:done", {
                "instance_id": instance_id,
                "agent_name": agent_name,
            })
            return True
        broadcast_event(workspace_id, "agent:chunk", {
            "instance_id": instance_id,
            "agent_name": agent_name,
            "content": buffer,
        })

    if full_response and not msg_service.is_no_reply(full_response.strip()):
        broadcast_event(workspace_id, "agent:done", {
            "instance_id": instance_id,
            "agent_name": agent_name,
            "full_content": full_response,
        })

        async with async_session_factory() as save_db:
            await msg_service.record_message(
                save_db,
                workspace_id=workspace_id,
                sender_type="agent",
                sender_id=instance_id,
                sender_name=agent_name,
                content=full_response,
                message_type="collaboration",
                target_instance_id=source_instance_id,
                depth=depth,
            )
    elif not full_response:
        broadcast_event(workspace_id, "agent:error", {
            "instance_id": instance_id,
            "agent_name": agent_name,
            "error": "empty_response",
        })
    else:
        broadcast_event(workspace_id, "agent:done", {
            "instance_id": instance_id,
            "agent_name": agent_name,
        })

    return True


async def send_system_message_to_agents(
    workspace_id: str,
    agent_ids: list[str],
    message: str,
    db: AsyncSession,
    mention_targets: list[str] | None = None,
) -> None:
    """Send a system-generated message to specific agents via the MessageBus."""
    from app.services.runtime.messaging.bus import message_bus
    from app.services.runtime.messaging.ingestion.system import build_system_envelope

    envelope = build_system_envelope(
        workspace_id=workspace_id,
        content=message,
        source_label="system_notify",
        targets=agent_ids,
        mention_targets=mention_targets,
    )

    result = await message_bus.publish(envelope, db=db)
    if result.error:
        logger.error(
            "send_system_message_to_agents: MessageBus error: %s", result.error,
        )
