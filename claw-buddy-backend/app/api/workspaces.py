"""Workspace API — CRUD, Agent management, Blackboard, Context, Members, Chat, SSE."""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_org, get_db
from app.schemas.workspace import (
    AddAgentRequest,
    AgentShareConfigUpdate,
    AgentSubscriptionUpdate,
    BlackboardUpdate,
    ChatMessageRequest,
    ContextEntryCreate,
    UpdateAgentRequest,
    WorkspaceCreate,
    WorkspaceMemberAdd,
    WorkspaceMemberUpdate,
    WorkspaceUpdate,
)
from app.services import context_service, workspace_service

logger = logging.getLogger(__name__)
router = APIRouter()


def _ok(data=None, message: str = "success"):
    return {"code": 0, "message": message, "data": data}


# ── helpers ──────────────────────────────────────────

def _get_current_user_dep():
    from app.core.security import get_current_user
    return get_current_user


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
        raise HTTPException(status_code=404, detail="工作区不存在")
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
        raise HTTPException(status_code=404, detail="工作区不存在")
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
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="工作区不存在")
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
        raise HTTPException(status_code=400, detail=str(e))
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
        raise HTTPException(status_code=404, detail="Agent 不存在")
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
        raise HTTPException(status_code=404, detail="Agent 不在该工作区中")
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
        raise HTTPException(status_code=404, detail="黑板不存在")
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
        raise HTTPException(status_code=404, detail="黑板不存在")
    return _ok(bb.model_dump(mode="json"))


# ── Context CRUD ─────────────────────────────────────

@router.get("/{workspace_id}/context")
async def list_context(
    workspace_id: str,
    entry_type: str | None = None,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    entries = await context_service.list_context_entries(db, workspace_id, limit, entry_type)
    return _ok([e.model_dump(mode="json") for e in entries])


@router.post("/{workspace_id}/context")
async def create_context(
    workspace_id: str,
    data: ContextEntryCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    entry = await context_service.create_context_entry(
        db, workspace_id, "manual", data,
    )
    return _ok(entry.model_dump(mode="json"))


@router.delete("/{workspace_id}/context/{entry_id}")
async def delete_context(
    workspace_id: str,
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    ok = await context_service.delete_context_entry(db, entry_id)
    if not ok:
        raise HTTPException(status_code=404, detail="条目不存在")
    return _ok(message="已删除")


# ── Agent Share Config ───────────────────────────────

@router.get("/{workspace_id}/agents/{instance_id}/share-config")
async def get_share_config(
    workspace_id: str,
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    cfg = await context_service.get_share_config(db, instance_id, workspace_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail="配置不存在")
    return _ok(cfg.model_dump(mode="json"))


@router.put("/{workspace_id}/agents/{instance_id}/share-config")
async def update_share_config(
    workspace_id: str,
    instance_id: str,
    data: AgentShareConfigUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    cfg = await context_service.update_share_config(db, instance_id, workspace_id, data)
    if cfg is None:
        raise HTTPException(status_code=404, detail="配置不存在")
    return _ok(cfg.model_dump(mode="json"))


# ── Agent Subscription ───────────────────────────────

@router.get("/{workspace_id}/agents/{instance_id}/subscription")
async def get_subscription(
    workspace_id: str,
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    sub = await context_service.get_subscription(db, instance_id, workspace_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="订阅不存在")
    return _ok(sub.model_dump(mode="json"))


@router.put("/{workspace_id}/agents/{instance_id}/subscription")
async def update_subscription(
    workspace_id: str,
    instance_id: str,
    data: AgentSubscriptionUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    sub = await context_service.update_subscription(db, instance_id, workspace_id, data)
    if sub is None:
        raise HTTPException(status_code=404, detail="订阅不存在")
    return _ok(sub.model_dump(mode="json"))


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
        raise HTTPException(status_code=400, detail=str(e))
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
        raise HTTPException(status_code=404, detail="成员不存在")
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
        raise HTTPException(status_code=404, detail="成员不存在")
    return _ok(message="已移除")


# ── Chat Proxy ───────────────────────────────────────

@router.post("/{workspace_id}/agents/{instance_id}/chat")
async def agent_chat(
    workspace_id: str,
    instance_id: str,
    data: ChatMessageRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_dep()),
):
    from app.models.instance import Instance
    from sqlalchemy import select as sa_select

    result = await db.execute(
        sa_select(Instance).where(
            Instance.id == instance_id,
            Instance.workspace_id == workspace_id,
            Instance.deleted_at.is_(None),
        )
    )
    inst = result.scalar_one_or_none()
    if inst is None:
        raise HTTPException(status_code=404, detail="Agent 不在该工作区中")

    context_entries = await context_service.get_relevant_context(db, instance_id, workspace_id)
    share_config = await context_service.get_share_config(db, instance_id, workspace_id)

    ws_info = await workspace_service.get_workspace(db, workspace_id)

    context_text = _format_context(context_entries)
    share_instruction = _build_share_instruction(
        ws_info, share_config,
    )
    system_content = f"{context_text}\n\n{share_instruction}" if context_text else share_instruction

    messages = [{"role": "system", "content": system_content}]
    messages.extend(data.history)
    messages.append({"role": "user", "content": data.message})

    env_vars = json.loads(inst.env_vars or '{}')
    token = env_vars.get('OPENCLAW_GATEWAY_TOKEN', '')
    domain = inst.ingress_domain or ''
    base_url = f"https://{domain}" if domain else ""

    if not base_url or not token:
        raise HTTPException(status_code=400, detail="Agent 实例缺少访问地址或 Token")

    async def stream():
        import httpx

        full_response = ""
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{base_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"model": "gpt-4", "messages": messages, "stream": True},
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        chunk_data = line[6:]
                        if chunk_data == "[DONE]":
                            yield f"data: [DONE]\n\n"
                            break
                        try:
                            chunk = json.loads(chunk_data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                full_response += content
                                clean = context_service.strip_share_markers(content)
                                if clean:
                                    yield f"data: {json.dumps({'content': clean})}\n\n"
                        except json.JSONDecodeError:
                            pass

        if full_response:
            from app.core.deps import async_session_factory
            async with async_session_factory() as parse_db:
                await context_service.parse_and_publish(
                    parse_db, workspace_id, instance_id, full_response,
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
    user=Depends(_get_current_user_dep()),
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

def _format_context(entries: list) -> str:
    if not entries:
        return ""
    lines = ["[工作区上下文]", "以下是同事 Agent 最近分享的信息：", ""]
    for e in entries[:10]:
        lines.append(f"- [{e.entry_type}] {e.content}")
    return "\n".join(lines)


def _build_share_instruction(ws_info, share_config) -> str:
    agents_list = ""
    if ws_info and ws_info.agents:
        agents_list = "\n".join(
            f"  - {a.display_name or a.name} (负责 {a.name})" for a in ws_info.agents
        )

    freq_map = {
        "proactive": "主动分享所有你认为有价值的信息",
        "conservative": "只在有重要结果或需要协助时分享",
        "minimal": "仅在完成关键任务时分享结果",
    }
    freq = "proactive"
    if share_config and share_config.share_frequency:
        freq = share_config.share_frequency
    freq_instruction = freq_map.get(freq, freq_map["proactive"])

    instruction = f"""[工作区协作指令]
你正在工作区「{ws_info.name if ws_info else '未知'}」中工作，同事 Agent 包括：
{agents_list or '  （暂无其他 Agent）'}

当你认为某些信息对同事有价值时，请在回复中使用以下标记分享：
  [SHARE:result] 你的工作成果
  [SHARE:knowledge] 你发现的事实或知识
  [SHARE:request:目标Agent名] 你需要某个Agent协助的事项
  [SHARE:activity] 你当前正在做的事情

分享策略：{freq_instruction}
"""
    if share_config and share_config.custom_instruction:
        instruction += f"\n补充指令：{share_config.custom_instruction}\n"

    return instruction
