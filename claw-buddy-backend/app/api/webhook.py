"""Webhook API — receives callbacks from OpenClaw channel plugins."""

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import async_session_factory
from app.models.instance import Instance
from app.schemas.workspace import WebhookPayload
from app.services import workspace_message_service as msg_service
from app.services import workspace_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/clawbuddy")
async def webhook_clawbuddy(payload: WebhookPayload, request: Request):
    """Receive outbound messages from the clawbuddy channel plugin.

    Called when an Agent uses `send -t clawbuddy` to communicate with
    other agents in the workspace.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization")
    api_token = auth_header[7:]

    if payload.depth > msg_service.MAX_COLLABORATION_DEPTH:
        logger.warning(
            "Collaboration depth exceeded (%d > %d) from instance %s",
            payload.depth, msg_service.MAX_COLLABORATION_DEPTH,
            payload.source_instance_id,
        )
        return {"ok": True, "message": "depth limit exceeded, message recorded but not forwarded"}

    async with async_session_factory() as db:
        source_inst = await _get_instance(db, payload.source_instance_id)
        if source_inst is None:
            raise HTTPException(status_code=404, detail="Source instance not found")

        env_vars = json.loads(source_inst.env_vars or "{}")
        expected_token = env_vars.get("OPENCLAW_GATEWAY_TOKEN", "")
        if not expected_token or api_token != expected_token:
            raise HTTPException(status_code=403, detail="Invalid API token")

        workspace_id = payload.workspace_id
        source_name = source_inst.agent_display_name or source_inst.name

        await msg_service.record_message(
            db,
            workspace_id=workspace_id,
            sender_type="agent",
            sender_id=payload.source_instance_id,
            sender_name=source_name,
            content=payload.text,
            message_type="collaboration",
            target_instance_id=_extract_target_instance_id(payload.target),
            depth=payload.depth,
        )

        from app.api.workspaces import broadcast_event
        broadcast_event(workspace_id, "agent:collaboration", {
            "instance_id": payload.source_instance_id,
            "agent_name": source_name,
            "target": payload.target,
            "content": payload.text,
        })

        if payload.target.startswith("agent:"):
            target_name = payload.target[6:]
            target_inst = await _find_agent_by_name(db, workspace_id, target_name)
            if target_inst:
                asyncio.create_task(
                    _invoke_target_agent(
                        workspace_id=workspace_id,
                        target_instance=target_inst,
                        source_name=source_name,
                        message=payload.text,
                        depth=payload.depth + 1,
                    )
                )
        elif payload.target == "broadcast":
            agents = await _get_workspace_agents(db, workspace_id)
            for agent in agents:
                if agent.id != payload.source_instance_id:
                    asyncio.create_task(
                        _invoke_target_agent(
                            workspace_id=workspace_id,
                            target_instance=agent,
                            source_name=source_name,
                            message=payload.text,
                            depth=payload.depth + 1,
                        )
                    )

    return {"ok": True}


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
):
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
        async with httpx.AsyncClient(timeout=120) as client:
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
