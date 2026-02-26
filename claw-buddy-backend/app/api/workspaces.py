"""Workspace API — CRUD, Agent management, Blackboard, Context, Members, Chat, SSE."""

import asyncio
import json
import logging
from datetime import timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import async_session_factory, get_current_org, get_db
from app.models.instance import Instance
from app.schemas.workspace import (
    AddAgentRequest,
    BlackboardUpdate,
    ChatMessageRequest,
    UpdateAgentRequest,
    WorkspaceChatRequest,
    WorkspaceCreate,
    WorkspaceMemberAdd,
    WorkspaceMemberUpdate,
    WorkspaceUpdate,
)
from app.services import workspace_service
from app.services import workspace_message_service as msg_service

logger = logging.getLogger(__name__)
router = APIRouter()


def _ok(data=None, message: str = "success"):
    return {"code": 0, "message": message, "data": data}


def _error(status_code: int, error_code: int, message_key: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error_code": error_code,
            "message_key": message_key,
            "message": message,
        },
    )


# ── helpers ──────────────────────────────────────────

def _get_current_user_dep():
    from app.core.security import get_current_user
    return get_current_user


def _get_current_user_from_query_dep():
    from app.core.security import get_current_user_from_query
    return get_current_user_from_query


# ── Workspace CRUD ───────────────────────────────────

@router.post("")
async def create_workspace(
    data: WorkspaceCreate,
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    ws = await workspace_service.create_workspace(db, org.id, user.id, data)
    return _ok(ws.model_dump(mode="json"))


@router.get("")
async def list_workspaces(
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    items = await workspace_service.list_workspaces(db, org.id)
    return _ok([i.model_dump(mode="json") for i in items])


@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    ws = await workspace_service.get_workspace(db, workspace_id)
    if ws is None:
        raise _error(404, 40430, "errors.workspace.not_found", "工作区不存在")
    return _ok(ws.model_dump(mode="json"))


@router.put("/{workspace_id}")
async def update_workspace(
    workspace_id: str,
    data: WorkspaceUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    ws = await workspace_service.update_workspace(db, workspace_id, data)
    if ws is None:
        raise _error(404, 40430, "errors.workspace.not_found", "工作区不存在")
    return _ok(ws.model_dump(mode="json"))


@router.delete("/{workspace_id}")
async def delete_workspace(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    try:
        ok = await workspace_service.delete_workspace(db, workspace_id)
    except ValueError as e:
        raise _error(400, 40030, "errors.workspace.delete_invalid", str(e))
    if not ok:
        raise _error(404, 40430, "errors.workspace.not_found", "工作区不存在")
    return _ok(message="已删除")


# ── Agent Management ─────────────────────────────────

@router.post("/{workspace_id}/agents")
async def add_agent(
    workspace_id: str,
    data: AddAgentRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    try:
        agent = await workspace_service.add_agent(db, workspace_id, data)
    except ValueError as e:
        raise _error(400, 40031, "errors.workspace.add_agent_invalid", str(e))
    return _ok(agent.model_dump(mode="json"))


@router.put("/{workspace_id}/agents/{instance_id}")
async def update_agent(
    workspace_id: str,
    instance_id: str,
    data: UpdateAgentRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    agent = await workspace_service.update_agent(db, workspace_id, instance_id, data)
    if agent is None:
        raise _error(404, 40431, "errors.workspace.agent_not_found", "Agent 不存在")
    return _ok(agent.model_dump(mode="json"))


@router.delete("/{workspace_id}/agents/{instance_id}")
async def remove_agent(
    workspace_id: str,
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    ok = await workspace_service.remove_agent(db, workspace_id, instance_id)
    if not ok:
        raise _error(404, 40432, "errors.workspace.agent_not_in_workspace", "Agent 不在该工作区中")
    return _ok(message="已移除")


# ── Blackboard ───────────────────────────────────────

@router.get("/{workspace_id}/blackboard")
async def get_blackboard(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    bb = await workspace_service.get_blackboard(db, workspace_id)
    if bb is None:
        raise _error(404, 40433, "errors.workspace.blackboard_not_found", "黑板不存在")
    return _ok(bb.model_dump(mode="json"))


@router.put("/{workspace_id}/blackboard")
async def update_blackboard(
    workspace_id: str,
    data: BlackboardUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    bb = await workspace_service.update_blackboard(db, workspace_id, data)
    if bb is None:
        raise _error(404, 40433, "errors.workspace.blackboard_not_found", "黑板不存在")
    return _ok(bb.model_dump(mode="json"))


# ── Workspace Members ────────────────────────────────

@router.get("/{workspace_id}/members")
async def list_members(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    members = await workspace_service.list_workspace_members(db, workspace_id)
    return _ok([m.model_dump(mode="json") for m in members])


@router.post("/{workspace_id}/members")
async def add_member(
    workspace_id: str,
    data: WorkspaceMemberAdd,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    try:
        member = await workspace_service.add_workspace_member(
            db, workspace_id, data.user_id, data.role,
        )
    except ValueError as e:
        raise _error(400, 40032, "errors.workspace.add_member_invalid", str(e))
    return _ok(member.model_dump(mode="json"))


@router.put("/{workspace_id}/members/{user_id}")
async def update_member(
    workspace_id: str,
    user_id: str,
    data: WorkspaceMemberUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    ok = await workspace_service.update_workspace_member_role(db, workspace_id, user_id, data.role)
    if not ok:
        raise _error(404, 40434, "errors.workspace.member_not_found", "成员不存在")
    return _ok(message="已更新")


@router.delete("/{workspace_id}/members/{user_id}")
async def remove_member(
    workspace_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    ok = await workspace_service.remove_workspace_member(db, workspace_id, user_id)
    if not ok:
        raise _error(404, 40434, "errors.workspace.member_not_found", "成员不存在")
    return _ok(message="已移除")


# ── Group Chat (Broadcast) ───────────────────────────

@router.post("/{workspace_id}/chat")
async def workspace_chat(
    workspace_id: str,
    data: WorkspaceChatRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    """Workspace-level group chat: broadcast user message to all agents."""
    ws_info = await workspace_service.get_workspace(db, workspace_id)
    if ws_info is None:
        raise _error(404, 40430, "errors.workspace.not_found", "工作区不存在")

    await msg_service.record_message(
        db,
        workspace_id=workspace_id,
        sender_type="user",
        sender_id=user.id,
        sender_name=user.name,
        content=data.message,
    )

    from app.services import corridor_router as cr
    use_topology = await cr.has_any_connections(db, workspace_id)

    if use_topology:
        endpoints = await cr.get_blackboard_audience(db, workspace_id)
        agent_endpoints = [ep for ep in endpoints if ep.endpoint_type == "agent"]
        agent_ids = {ep.entity_id for ep in agent_endpoints}
        running_agents = [
            a for a in await _get_running_agents(db, workspace_id) if a.id in agent_ids
        ]
    else:
        running_agents = await _get_running_agents(db, workspace_id)

    if not running_agents:
        broadcast_event(workspace_id, "system:info", {"message": "工作区内没有运行中的 Agent"})
        return _ok({"status": "no_agents"})

    members = _build_members_list(ws_info, user)
    recent_messages = await msg_service.get_recent_messages(db, workspace_id)

    for inst in running_agents:
        asyncio.create_task(
            _stream_agent_response(
                workspace_id=workspace_id,
                instance=inst,
                members=members,
                recent_messages=recent_messages,
                user_name=user.name,
                user_message=data.message,
                ws_name=ws_info.name,
                mentions=data.mentions,
            )
        )

    return _ok({"status": "broadcasting", "agent_count": len(running_agents)})


class SystemMessageRequest(BaseModel):
    content: str


@router.post("/{workspace_id}/system-message")
async def post_system_message(
    workspace_id: str,
    data: SystemMessageRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    """Persist a system message (slash command result, etc.) without triggering agent responses."""
    msg = await msg_service.record_message(
        db,
        workspace_id=workspace_id,
        sender_type="system",
        sender_id=user.id,
        sender_name=user.name,
        content=data.content,
        message_type="system",
    )
    broadcast_event(workspace_id, "system:info", {
        "id": msg.id,
        "sender_type": "system",
        "sender_id": user.id,
        "sender_name": user.name,
        "content": data.content,
        "message_type": "system",
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    })
    return _ok({"id": msg.id})


@router.get("/{workspace_id}/messages")
async def list_workspace_messages(
    workspace_id: str,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    """List recent workspace messages for chat history."""
    messages = await msg_service.get_recent_messages(db, workspace_id, limit)
    return _ok([
        {
            "id": m.id,
            "workspace_id": m.workspace_id,
            "sender_type": m.sender_type,
            "sender_id": m.sender_id,
            "sender_name": m.sender_name,
            "content": m.content,
            "message_type": m.message_type,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ])


# ── Legacy Chat Proxy (deprecated) ──────────────────

@router.post("/{workspace_id}/agents/{instance_id}/chat")
async def agent_chat(
    workspace_id: str,
    instance_id: str,
    data: ChatMessageRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    """Single-agent chat (deprecated, use workspace_chat instead)."""
    result = await db.execute(
        sa_select(Instance).where(
            Instance.id == instance_id,
            Instance.workspace_id == workspace_id,
            Instance.deleted_at.is_(None),
        )
    )
    inst = result.scalar_one_or_none()
    if inst is None:
        raise _error(404, 40432, "errors.workspace.agent_not_in_workspace", "Agent 不在该工作区中")

    ws_info = await workspace_service.get_workspace(db, workspace_id)
    recent_messages = await msg_service.get_recent_messages(db, workspace_id)
    members = _build_members_list(ws_info, user)

    agent_name = inst.agent_display_name or inst.name
    context_prompt = msg_service.build_context_prompt(
        workspace_name=ws_info.name if ws_info else "Unknown",
        agent_display_name=agent_name,
        current_instance_id=instance_id,
        members=members,
        recent_messages=recent_messages,
    )

    messages = [
        {"role": "system", "content": context_prompt},
        {"role": "user", "content": data.message},
    ]

    base_url, token = _get_instance_connection(inst)
    if not base_url or not token:
        raise _error(400, 40033, "errors.workspace.agent_connection_missing", "Agent 实例缺少访问地址或 Token")

    async def stream():
        full_response = ""
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
                json={"model": "gpt-4", "messages": messages, "stream": True},
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        chunk_data = line[6:]
                        if chunk_data == "[DONE]":
                            yield "data: [DONE]\n\n"
                            break
                        try:
                            chunk = json.loads(chunk_data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response += content
                                yield f"data: {json.dumps({'content': content})}\n\n"
                        except json.JSONDecodeError:
                            pass

        if full_response and not msg_service.is_no_reply(full_response):
            async with async_session_factory() as save_db:
                await msg_service.record_message(
                    save_db,
                    workspace_id=workspace_id,
                    sender_type="agent",
                    sender_id=instance_id,
                    sender_name=agent_name,
                    content=full_response,
                )

    return StreamingResponse(stream(), media_type="text/event-stream")


# ── SSE Event Stream ─────────────────────────────────

_workspace_queues: dict[str, set[asyncio.Queue]] = {}


def broadcast_event(workspace_id: str, event_type: str, data: dict):
    queues = _workspace_queues.get(workspace_id, set())
    for q in queues:
        q.put_nowait({"event": event_type, "data": data})


@router.get("/{workspace_id}/events")
async def workspace_events(
    workspace_id: str,
    user=Depends(_get_current_user_from_query_dep()),
):
    queue: asyncio.Queue = asyncio.Queue()
    if workspace_id not in _workspace_queues:
        _workspace_queues[workspace_id] = set()
    _workspace_queues[workspace_id].add(queue)

    async def stream():
        try:
            yield f"data: {json.dumps({'event': 'connected'})}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"event: {msg['event']}\ndata: {json.dumps(msg['data'])}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _workspace_queues.get(workspace_id, set()).discard(queue)

    return StreamingResponse(stream(), media_type="text/event-stream")


# ── SSE Token ────────────────────────────────────────

@router.post("/sse-token")
async def create_sse_token(
    user=Depends(_get_current_user_dep()),
):
    from app.core.security import create_access_token
    token = create_access_token(
        subject=user.id,
        extra_claims={"scope": "sse"},
        expires_delta=timedelta(minutes=5),
    )
    return _ok({"sse_token": token, "expires_in": 300})


# ── Private helpers ──────────────────────────────────

async def _get_running_agents(db: AsyncSession, workspace_id: str) -> list[Instance]:
    result = await db.execute(
        sa_select(Instance).where(
            Instance.workspace_id == workspace_id,
            Instance.status == "running",
            Instance.deleted_at.is_(None),
        )
    )
    return list(result.scalars().all())


def _get_instance_connection(inst: Instance) -> tuple[str, str]:
    env_vars = json.loads(inst.env_vars or "{}")
    token = env_vars.get("OPENCLAW_GATEWAY_TOKEN", "")
    domain = inst.ingress_domain or ""
    base_url = f"https://{domain}" if domain else ""
    return base_url, token


def _build_members_list(ws_info, user) -> list[dict]:
    members = []
    if ws_info and ws_info.agents:
        for a in ws_info.agents:
            members.append({
                "type": "Agent",
                "name": a.display_name or a.name,
                "id": a.instance_id,
            })
    members.append({"type": "User", "name": user.name, "id": user.id})
    return members


NO_REPLY_BUFFER_SIZE = 20


async def _stream_agent_response(
    *,
    workspace_id: str,
    instance: Instance,
    members: list[dict],
    recent_messages: list,
    user_name: str,
    user_message: str,
    ws_name: str,
    mentions: list[str] | None = None,
):
    """Stream a single agent's response and relay via SSE broadcast.

    Buffers initial characters to detect NO_REPLY before pushing to frontend.
    Each agent runs in its own asyncio.Task so they execute in parallel.
    """
    agent_name = instance.agent_display_name or instance.name
    instance_id = instance.id

    context_prompt = msg_service.build_context_prompt(
        workspace_name=ws_name,
        agent_display_name=agent_name,
        current_instance_id=instance_id,
        members=members,
        recent_messages=recent_messages,
    )

    if mentions and len(mentions) > 0:
        is_mentioned = instance_id in mentions
        if is_mentioned:
            context_prompt += "\n[重要] 用户在消息中 @提及了你，请务必回复。\n"
        else:
            context_prompt += "\n[提示] 用户没有 @提及你。如果消息与你无关，请回复 NO_REPLY。\n"

    messages = [
        {"role": "system", "content": context_prompt},
        {"role": "user", "content": f"[{user_name}]: {user_message}"},
    ]

    base_url, token = _get_instance_connection(instance)
    if not base_url or not token:
        logger.warning("Agent %s (%s) 缺少连接信息，跳过", agent_name, instance_id)
        return

    broadcast_event(workspace_id, "agent:typing", {
        "instance_id": instance_id,
        "agent_name": agent_name,
    })

    buffer = ""
    flushed = False
    full_response = ""

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
                json={"model": "gpt-4", "messages": messages, "stream": True},
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
                        if len(buffer) > NO_REPLY_BUFFER_SIZE:
                            if msg_service.is_no_reply(buffer.strip()):
                                logger.info("Agent %s replied NO_REPLY, discarding", agent_name)
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
        logger.error("Agent %s streaming failed: %s", agent_name, e)
        broadcast_event(workspace_id, "agent:error", {
            "instance_id": instance_id,
            "agent_name": agent_name,
            "error": str(e),
        })
        return

    if not flushed and buffer:
        if msg_service.is_no_reply(buffer.strip()):
            logger.info("Agent %s replied NO_REPLY (short response), discarding", agent_name)
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
            )
    else:
        broadcast_event(workspace_id, "agent:done", {
            "instance_id": instance_id,
            "agent_name": agent_name,
        })
