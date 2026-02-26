"""Collaboration message handling — shared by SSE listener and (legacy) webhook."""

import asyncio
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import async_session_factory
from app.models.instance import Instance
from app.services import workspace_message_service as msg_service
from app.services import workspace_service

logger = logging.getLogger(__name__)


async def handle_collaboration_message(
    *,
    workspace_id: str,
    source_instance_id: str,
    target: str,
    text: str,
    depth: int = 0,
) -> None:
    """Process an inbound collaboration message from a channel plugin.

    1. Validate depth limit
    2. Look up source instance
    3. Record message
    4. Broadcast SSE event to frontend
    5. Route to target agent(s)
    """
    if depth > msg_service.MAX_COLLABORATION_DEPTH:
        logger.warning(
            "Collaboration depth exceeded (%d > %d) from instance %s",
            depth, msg_service.MAX_COLLABORATION_DEPTH, source_instance_id,
        )
        return

    async with async_session_factory() as db:
        source_inst = await _get_instance(db, source_instance_id)
        if source_inst is None:
            logger.warning("Source instance not found: %s", source_instance_id)
            return

        source_name = source_inst.agent_display_name or source_inst.name

        await msg_service.record_message(
            db,
            workspace_id=workspace_id,
            sender_type="agent",
            sender_id=source_instance_id,
            sender_name=source_name,
            content=text,
            message_type="collaboration",
            target_instance_id=_extract_target_instance_id(target),
            depth=depth,
        )

        from app.api.workspaces import broadcast_event
        broadcast_event(workspace_id, "agent:collaboration", {
            "instance_id": source_instance_id,
            "agent_name": source_name,
            "target": target,
            "content": text,
        })

        from app.services import corridor_router as cr
        use_topology = await cr.has_any_connections(db, workspace_id)

        if target.startswith("agent:"):
            target_name = target[6:]
            target_inst = await _find_agent_by_name(db, workspace_id, target_name)
            if target_inst:
                if use_topology:
                    reachable = await cr.can_reach(
                        db, workspace_id,
                        source_inst.hex_position_q, source_inst.hex_position_r,
                        target_inst.hex_position_q, target_inst.hex_position_r,
                    )
                    if not reachable:
                        logger.warning(
                            "Agent %s cannot reach %s through corridor topology",
                            source_instance_id, target_inst.id,
                        )
                        return
                asyncio.create_task(
                    _invoke_target_agent(
                        workspace_id=workspace_id,
                        target_instance=target_inst,
                        source_name=source_name,
                        message=text,
                        depth=depth + 1,
                    )
                )
        elif target == "broadcast":
            if use_topology:
                endpoints = await cr.get_reachable_endpoints(
                    db, workspace_id,
                    source_inst.hex_position_q, source_inst.hex_position_r,
                )
                reachable_ids = {ep.entity_id for ep in endpoints if ep.endpoint_type == "agent"}
                agents = await _get_workspace_agents(db, workspace_id)
                agents = [a for a in agents if a.id in reachable_ids]
            else:
                agents = await _get_workspace_agents(db, workspace_id)
            for agent in agents:
                if agent.id != source_instance_id:
                    asyncio.create_task(
                        _invoke_target_agent(
                            workspace_id=workspace_id,
                            target_instance=agent,
                            source_name=source_name,
                            message=text,
                            depth=depth + 1,
                        )
                    )


# ── DB helpers ────────────────────────────────────────


async def _get_instance(db: AsyncSession, instance_id: str) -> Instance | None:
    result = await db.execute(
        select(Instance).where(
            Instance.id == instance_id,
            Instance.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def _find_agent_by_name(
    db: AsyncSession, workspace_id: str, agent_name: str,
) -> Instance | None:
    result = await db.execute(
        select(Instance).where(
            Instance.workspace_id == workspace_id,
            Instance.status == "running",
            Instance.deleted_at.is_(None),
        )
    )
    agents = result.scalars().all()
    for a in agents:
        display = a.agent_display_name or a.name
        if display.lower() == agent_name.lower() or a.name.lower() == agent_name.lower():
            return a
    return None


async def _get_workspace_agents(db: AsyncSession, workspace_id: str) -> list[Instance]:
    result = await db.execute(
        select(Instance).where(
            Instance.workspace_id == workspace_id,
            Instance.status == "running",
            Instance.deleted_at.is_(None),
        )
    )
    return list(result.scalars().all())


def _extract_target_instance_id(target: str) -> str | None:
    if target.startswith("agent:"):
        return target[6:]
    return None


async def _invoke_target_agent(
    *,
    workspace_id: str,
    target_instance: Instance,
    source_name: str,
    message: str,
    depth: int,
) -> None:
    """Invoke a target agent with a collaboration message."""
    import httpx

    from app.api.workspaces import broadcast_event

    agent_name = target_instance.agent_display_name or target_instance.name
    instance_id = target_instance.id

    async with async_session_factory() as db:
        ws_info = await workspace_service.get_workspace(db, workspace_id)
        recent_messages = await msg_service.get_recent_messages(db, workspace_id)

    members: list[dict] = []
    if ws_info and ws_info.agents:
        for a in ws_info.agents:
            members.append({
                "type": "Agent",
                "name": a.display_name or a.name,
                "id": a.instance_id,
            })

    context_prompt = msg_service.build_context_prompt(
        workspace_name=ws_info.name if ws_info else "Unknown",
        agent_display_name=agent_name,
        current_instance_id=instance_id,
        members=members,
        recent_messages=recent_messages,
    )

    messages_payload = [
        {"role": "system", "content": context_prompt},
        {"role": "user", "content": f"[{source_name} -> you]: {message}"},
    ]

    env_vars = json.loads(target_instance.env_vars or "{}")
    token = env_vars.get("OPENCLAW_GATEWAY_TOKEN", "")
    domain = target_instance.ingress_domain or ""
    base_url = f"https://{domain}" if domain else ""

    if not base_url or not token:
        logger.warning("Target agent %s missing connection info", agent_name)
        return

    broadcast_event(workspace_id, "agent:typing", {
        "instance_id": instance_id,
        "agent_name": agent_name,
    })

    full_response = ""
    buffer = ""
    flushed = False

    try:
        async with httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(verify=False, local_address="0.0.0.0"),
            timeout=120,
        ) as client:
            async with client.stream(
                "POST",
                f"{base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "X-OpenClaw-Session-Key": f"workspace:{workspace_id}",
                },
                json={"model": "gpt-4", "messages": messages_payload, "stream": True},
            ) as resp:
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    chunk_data = line[6:]
                    if chunk_data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(chunk_data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                    except json.JSONDecodeError:
                        continue
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
                                return
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
            "error": str(e),
        })
        return

    if not flushed and buffer:
        if msg_service.is_no_reply(buffer.strip()):
            broadcast_event(workspace_id, "agent:done", {
                "instance_id": instance_id,
                "agent_name": agent_name,
            })
            return
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
                depth=depth,
            )
    else:
        broadcast_event(workspace_id, "agent:done", {
            "instance_id": instance_id,
            "agent_name": agent_name,
        })
