"""Workspace CRUD + Agent management + Blackboard service."""

import asyncio
import logging
from typing import Coroutine

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blackboard import Blackboard
from app.models.instance import Instance
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.schemas.workspace import (
    AddAgentRequest,
    AgentBrief,
    BlackboardInfo,
    BlackboardSectionPatch,
    BlackboardUpdate,
    UpdateAgentRequest,
    WorkspaceCreate,
    WorkspaceInfo,
    WorkspaceListItem,
    WorkspaceMemberInfo,
    WorkspaceUpdate,
)

logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task] = set()


def _fire_task(coro: Coroutine) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def _agent_brief(inst: Instance) -> AgentBrief:
    from app.services.sse_listener import sse_listener_manager
    return AgentBrief(
        instance_id=inst.id,
        name=inst.name,
        display_name=inst.agent_display_name,
        label=inst.agent_label,
        slug=inst.slug,
        status=inst.status,
        hex_q=inst.hex_position_q,
        hex_r=inst.hex_position_r,
        sse_connected=inst.id in sse_listener_manager.healthy_instances,
        theme_color=inst.agent_theme_color,
    )


# ── Workspace CRUD ───────────────────────────────────

async def create_workspace(db: AsyncSession, org_id: str, user_id: str, data: WorkspaceCreate) -> WorkspaceInfo:
    ws = Workspace(
        org_id=org_id,
        name=data.name,
        description=data.description,
        color=data.color,
        icon=data.icon,
        created_by=user_id,
    )
    db.add(ws)
    await db.flush()

    bb = Blackboard(workspace_id=ws.id)
    db.add(bb)

    member = WorkspaceMember(workspace_id=ws.id, user_id=user_id, role=WorkspaceRole.owner)
    db.add(member)

    await db.commit()
    await db.refresh(ws)
    return WorkspaceInfo(
        id=ws.id, org_id=ws.org_id, name=ws.name, description=ws.description,
        color=ws.color, icon=ws.icon, created_by=ws.created_by,
        agent_count=0, agents=[], created_at=ws.created_at, updated_at=ws.updated_at,
    )


async def list_workspaces(db: AsyncSession, org_id: str) -> list[WorkspaceListItem]:
    result = await db.execute(
        select(Workspace).where(
            Workspace.org_id == org_id,
            Workspace.deleted_at.is_(None),
        ).order_by(Workspace.created_at.desc())
    )
    workspaces = result.scalars().all()

    items = []
    for ws in workspaces:
        agents_result = await db.execute(
            select(Instance).where(
                Instance.workspace_id == ws.id,
                Instance.deleted_at.is_(None),
            )
        )
        agents = agents_result.scalars().all()
        items.append(WorkspaceListItem(
            id=ws.id, name=ws.name, description=ws.description,
            color=ws.color, icon=ws.icon,
            agent_count=len(agents),
            agents=[_agent_brief(a) for a in agents],
            created_at=ws.created_at,
        ))
    return items


async def get_workspace(db: AsyncSession, workspace_id: str) -> WorkspaceInfo | None:
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.deleted_at.is_(None))
    )
    ws = result.scalar_one_or_none()
    if ws is None:
        return None

    agents_result = await db.execute(
        select(Instance).where(
            Instance.workspace_id == workspace_id,
            Instance.deleted_at.is_(None),
        )
    )
    agents = agents_result.scalars().all()

    return WorkspaceInfo(
        id=ws.id, org_id=ws.org_id, name=ws.name, description=ws.description,
        color=ws.color, icon=ws.icon, created_by=ws.created_by,
        agent_count=len(agents),
        agents=[_agent_brief(a) for a in agents],
        created_at=ws.created_at, updated_at=ws.updated_at,
    )


async def update_workspace(db: AsyncSession, workspace_id: str, data: WorkspaceUpdate) -> WorkspaceInfo | None:
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.deleted_at.is_(None))
    )
    ws = result.scalar_one_or_none()
    if ws is None:
        return None

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(ws, field, value)
    await db.commit()
    return await get_workspace(db, workspace_id)


async def delete_workspace(db: AsyncSession, workspace_id: str) -> bool:
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.deleted_at.is_(None))
    )
    ws = result.scalar_one_or_none()
    if ws is None:
        return False

    agents_count = await db.execute(
        select(func.count()).select_from(Instance).where(
            Instance.workspace_id == workspace_id,
            Instance.deleted_at.is_(None),
        )
    )
    if agents_count.scalar() > 0:
        raise ValueError("请先移除工作区内的所有 Agent")

    ws.soft_delete()
    await db.commit()
    return True


# ── Agent management ─────────────────────────────────

async def add_agent(db: AsyncSession, workspace_id: str, data: AddAgentRequest, user_id: str) -> AgentBrief:
    result = await db.execute(
        select(Instance).where(Instance.id == data.instance_id, Instance.deleted_at.is_(None))
    )
    inst = result.scalar_one_or_none()
    if inst is None:
        raise ValueError("实例不存在")

    if data.hex_q is not None:
        inst.hex_position_q = data.hex_q
        inst.hex_position_r = data.hex_r or 0
    else:
        existing = await db.execute(
            select(func.count()).select_from(Instance).where(
                Instance.workspace_id == workspace_id,
                Instance.deleted_at.is_(None),
            )
        )
        count = existing.scalar() or 0
        pos = _spiral_next(count)
        inst.hex_position_q = pos[0]
        inst.hex_position_r = pos[1]

    inst.workspace_id = workspace_id
    inst.agent_display_name = data.display_name

    from app.services import corridor_router
    connected = await corridor_router.auto_connect_hex(
        workspace_id, inst.hex_position_q, inst.hex_position_r, user_id, db,
    )

    await db.commit()
    await db.refresh(inst)

    await _deploy_channel_plugin(inst, db, workspace_id)

    has_topo = await corridor_router.has_any_connections(workspace_id, db)
    if has_topo:
        await _notify_topology_status(workspace_id, inst, connected)

    await _broadcast_join_message(workspace_id, inst)
    _fire_task(_send_welcome_message(workspace_id, inst))

    return _agent_brief(inst)


def _spiral_next(index: int) -> tuple[int, int]:
    """Return the hex position for the Nth agent (0-indexed) using spiral layout."""
    if index == 0:
        return (1, 0)
    positions: list[tuple[int, int]] = []
    q, r, ring = 1, 0, 1
    directions = [(0, -1), (-1, 0), (-1, 1), (0, 1), (1, 0), (1, -1)]
    while len(positions) <= index:
        for dq, dr in directions:
            for _ in range(ring):
                if len(positions) > index:
                    break
                positions.append((q, r))
                q += dq
                r += dr
        ring += 1
        q += 1
    return positions[index]


async def remove_agent(db: AsyncSession, workspace_id: str, instance_id: str) -> bool:
    result = await db.execute(
        select(Instance).where(
            Instance.id == instance_id,
            Instance.workspace_id == workspace_id,
            Instance.deleted_at.is_(None),
        )
    )
    inst = result.scalar_one_or_none()
    if inst is None:
        return False

    await _broadcast_leave_message(workspace_id, inst)
    await _remove_channel_plugin(inst, db)

    inst.workspace_id = None
    inst.hex_position_q = 0
    inst.hex_position_r = 0
    inst.agent_display_name = None
    inst.agent_label = None

    await db.commit()
    return True


async def update_agent(
    db: AsyncSession, workspace_id: str, instance_id: str, data: UpdateAgentRequest,
) -> AgentBrief | None:
    result = await db.execute(
        select(Instance).where(
            Instance.id == instance_id,
            Instance.workspace_id == workspace_id,
            Instance.deleted_at.is_(None),
        )
    )
    inst = result.scalar_one_or_none()
    if inst is None:
        return None

    if data.display_name is not None:
        inst.agent_display_name = data.display_name or None
    if data.label is not None:
        inst.agent_label = data.label or None
    if data.theme_color is not None:
        inst.agent_theme_color = data.theme_color

    position_changed = False
    old_q, old_r = inst.hex_position_q, inst.hex_position_r
    if data.hex_q is not None and data.hex_r is not None:
        new_q, new_r = data.hex_q, data.hex_r
        if (new_q, new_r) != (old_q, old_r):
            inst.hex_position_q = new_q
            inst.hex_position_r = new_r
            position_changed = True
    elif data.hex_q is not None:
        inst.hex_position_q = data.hex_q
    elif data.hex_r is not None:
        inst.hex_position_r = data.hex_r

    await db.commit()

    if position_changed:
        from app.services import corridor_router
        await corridor_router.cascade_delete_connections(workspace_id, old_q, old_r, db)
        await corridor_router.auto_connect_hex(
            workspace_id, inst.hex_position_q, inst.hex_position_r, inst.created_by, db,
        )
        await db.commit()

    await db.refresh(inst)
    return _agent_brief(inst)


# ── Channel Plugin Deploy ────────────────────────────

async def _deploy_channel_plugin(inst: Instance, db: AsyncSession, workspace_id: str) -> None:
    """Deploy nodeskclaw channel plugin config + restart instance + connect SSE."""
    try:
        from app.services.llm_config_service import deploy_nodeskclaw_channel_plugin
        await deploy_nodeskclaw_channel_plugin(inst, db, workspace_id)
    except Exception as e:
        logger.error("部署 channel plugin 失败（非致命）: instance=%s error=%s", inst.name, e)
        return

    try:
        from app.services.llm_config_service import deploy_learning_channel_plugin
        await deploy_learning_channel_plugin(inst, db)
    except Exception as e:
        logger.warning("部署 learning plugin 失败（非致命）: instance=%s error=%s", inst.name, e)

    try:
        from app.services.instance_service import restart_instance
        await restart_instance(inst.id, db)
        logger.info("已重启实例以加载 channel plugin: %s", inst.name)
    except Exception as e:
        logger.warning("重启实例失败（非致命）: instance=%s error=%s", inst.name, e)

    if inst.ingress_domain:
        from app.services.sse_listener import sse_listener_manager
        await sse_listener_manager.connect(
            inst.id,
            inst.ingress_domain,
            delay=15,
            workspace_id=workspace_id,
        )


async def _remove_channel_plugin(inst: Instance, db: AsyncSession) -> None:
    """Disconnect SSE + remove nodeskclaw channel plugin config."""
    from app.services.sse_listener import sse_listener_manager
    await sse_listener_manager.disconnect(inst.id)

    try:
        from app.services.llm_config_service import remove_nodeskclaw_channel_plugin
        await remove_nodeskclaw_channel_plugin(inst, db)
    except Exception as e:
        logger.error("移除 channel plugin 失败（非致命）: instance=%s error=%s", inst.name, e)


_NODE_TYPE_LABELS = {
    "blackboard": "黑板",
    "corridor": "走廊",
    "agent": "Agent",
    "human": "成员",
}


async def _notify_topology_status(
    workspace_id: str, inst: Instance, connected: list,
) -> None:
    """Broadcast a system:info event about the agent's topology connection status."""
    from app.api.workspaces import broadcast_event
    from datetime import datetime, timezone

    agent_name = inst.agent_display_name or inst.name

    if connected:
        names = []
        for node in connected:
            label = _NODE_TYPE_LABELS.get(node.node_type, node.node_type)
            if node.display_name:
                names.append(f"{node.display_name}({label})")
            else:
                names.append(label)
        content = f"{agent_name} 已自动连接到: {', '.join(names)}。可在拓扑编辑器中调整。"
    else:
        content = (
            f"{agent_name} 当前位置没有相邻节点连接，"
            "除加入消息外不会参与工作区交互。"
            "请在拓扑编辑器中手动连接，或将 Agent 拖到已有节点旁边。"
        )

    broadcast_event(workspace_id, "system:info", {
        "id": f"sys-topo-{inst.id[:8]}-{int(datetime.now(timezone.utc).timestamp())}",
        "sender_type": "system",
        "sender_id": "system",
        "sender_name": "System",
        "content": content,
        "message_type": "system",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


WELCOME_MESSAGE = "你好！你刚刚加入了工作区，请向大家介绍一下你自己：你叫什么名字、你的能力和专长是什么。"
WELCOME_READY_TIMEOUT = 120
WELCOME_POLL_INTERVAL = 3
WELCOME_FALLBACK_DELAY = 10


async def _broadcast_join_message(workspace_id: str, inst: Instance) -> None:
    """Record and broadcast the 'joined workspace' system message immediately."""
    from app.api.workspaces import broadcast_event
    from app.core.deps import async_session_factory
    from app.services import workspace_message_service as msg_service

    agent_name = inst.agent_display_name or inst.name

    try:
        async with async_session_factory() as db:
            await msg_service.record_message(
                db,
                workspace_id=workspace_id,
                sender_type="system",
                sender_id="system",
                sender_name="System",
                content=f"{agent_name} 已加入工作区",
                message_type="system",
            )

        broadcast_event(workspace_id, "system:welcome", {
            "agent_name": agent_name,
            "instance_id": inst.id,
            "content": f"{agent_name} 已加入工作区",
        })
    except Exception as e:
        logger.warning("广播加入消息失败（非致命）: instance=%s error=%s", inst.name, e)


async def _broadcast_leave_message(workspace_id: str, inst: Instance) -> None:
    """Record and broadcast the 'left workspace' system message before cleanup."""
    from app.api.workspaces import broadcast_event
    from app.core.deps import async_session_factory
    from app.services import workspace_message_service as msg_service
    from datetime import datetime, timezone

    agent_name = inst.agent_display_name or inst.name
    msg_id = f"sys-leave-{inst.id[:8]}-{int(datetime.now(timezone.utc).timestamp())}"
    content = f"{agent_name} 已退出工作区"

    try:
        async with async_session_factory() as db:
            await msg_service.record_message(
                db,
                workspace_id=workspace_id,
                sender_type="system",
                sender_id="system",
                sender_name="System",
                content=content,
                message_type="system",
            )

        broadcast_event(workspace_id, "system:info", {
            "id": msg_id,
            "sender_type": "system",
            "sender_id": "system",
            "sender_name": "System",
            "content": content,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.warning("广播退出消息失败（非致命）: instance=%s error=%s", inst.name, e)


async def _send_welcome_message(workspace_id: str, inst: Instance) -> None:
    """Wait for the instance to be ready, then trigger Agent self-introduction."""
    agent_name = inst.agent_display_name or inst.name

    from app.services.sse_listener import sse_listener_manager
    has_sse_task = inst.id in sse_listener_manager.connected_instances

    if has_sse_task:
        elapsed = 0
        while elapsed < WELCOME_READY_TIMEOUT:
            if inst.id in sse_listener_manager.healthy_instances:
                break
            await asyncio.sleep(WELCOME_POLL_INTERVAL)
            elapsed += WELCOME_POLL_INTERVAL
        else:
            logger.warning(
                "Agent %s 在 %ds 内未就绪，放弃自我介绍",
                agent_name, WELCOME_READY_TIMEOUT,
            )
            return
        await asyncio.sleep(3)
    else:
        await asyncio.sleep(WELCOME_FALLBACK_DELAY)

    try:
        from app.services.collaboration_service import _invoke_target_agent
        await _invoke_target_agent(
            workspace_id=workspace_id,
            target_instance=inst,
            source_name="System",
            message=WELCOME_MESSAGE,
            depth=0,
        )
    except Exception as e:
        logger.warning("发送欢迎消息失败（非致命）: instance=%s error=%s", inst.name, e)


# ── Blackboard ───────────────────────────────────────

def _bb_to_info(bb: Blackboard) -> BlackboardInfo:
    return BlackboardInfo(
        id=bb.id, workspace_id=bb.workspace_id,
        content=bb.content, updated_at=bb.updated_at,
    )


async def get_blackboard(db: AsyncSession, workspace_id: str) -> BlackboardInfo | None:
    result = await db.execute(
        select(Blackboard).where(Blackboard.workspace_id == workspace_id)
    )
    bb = result.scalar_one_or_none()
    if bb is None:
        return None
    return _bb_to_info(bb)


async def update_blackboard(db: AsyncSession, workspace_id: str, data: BlackboardUpdate) -> BlackboardInfo | None:
    result = await db.execute(
        select(Blackboard).where(Blackboard.workspace_id == workspace_id)
    )
    bb = result.scalar_one_or_none()
    if bb is None:
        return None
    bb.content = data.content
    await db.commit()
    await db.refresh(bb)
    return _bb_to_info(bb)


def _patch_section(markdown: str, section: str, new_content: str) -> str:
    """Replace content under ``## {section}``, or append if not found."""
    lines = markdown.split("\n")
    heading = f"## {section}"
    start = end = -1
    for i, line in enumerate(lines):
        if line.strip() == heading:
            start = i + 1
        elif start >= 0 and line.startswith("## "):
            end = i
            break
    if start >= 0:
        if end < 0:
            end = len(lines)
        lines[start:end] = ["", new_content, ""]
    else:
        lines.extend(["", heading, "", new_content])
    return "\n".join(lines)


async def patch_blackboard_section(
    db: AsyncSession, workspace_id: str, data: BlackboardSectionPatch,
) -> BlackboardInfo | None:
    result = await db.execute(
        select(Blackboard).where(Blackboard.workspace_id == workspace_id)
    )
    bb = result.scalar_one_or_none()
    if bb is None:
        return None
    bb.content = _patch_section(bb.content, data.section, data.content)
    await db.commit()
    await db.refresh(bb)
    return _bb_to_info(bb)


# ── Workspace Members ────────────────────────────────

async def list_workspace_members(db: AsyncSession, workspace_id: str) -> list[WorkspaceMemberInfo]:
    from app.models.user import User
    result = await db.execute(
        select(WorkspaceMember, User).join(User, WorkspaceMember.user_id == User.id).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.deleted_at.is_(None),
        )
    )
    members = []
    for wm, user in result.all():
        members.append(WorkspaceMemberInfo(
            user_id=user.id, user_name=user.name,
            user_email=user.email, user_avatar_url=user.avatar_url,
            role=wm.role, created_at=wm.created_at,
        ))
    return members


async def add_workspace_member(
    db: AsyncSession, workspace_id: str, user_id: str, role: str = "editor",
) -> WorkspaceMemberInfo:
    from app.models.user import User
    existing = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError("用户已是工作区成员")

    wm = WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=role)
    db.add(wm)
    await db.commit()

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one()
    return WorkspaceMemberInfo(
        user_id=user.id, user_name=user.name,
        user_email=user.email, user_avatar_url=user.avatar_url,
        role=wm.role, created_at=wm.created_at,
    )


async def update_workspace_member_role(
    db: AsyncSession, workspace_id: str, user_id: str, role: str,
) -> bool:
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.deleted_at.is_(None),
        )
    )
    wm = result.scalar_one_or_none()
    if wm is None:
        return False
    wm.role = role
    await db.commit()
    return True


async def remove_workspace_member(db: AsyncSession, workspace_id: str, user_id: str) -> bool:
    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.deleted_at.is_(None),
        )
    )
    wm = result.scalar_one_or_none()
    if wm is None:
        return False
    wm.soft_delete()
    await db.commit()
    return True
