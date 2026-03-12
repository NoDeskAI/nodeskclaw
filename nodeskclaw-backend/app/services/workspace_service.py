"""Workspace CRUD + Agent management + Blackboard service."""

import asyncio
import logging
from typing import Coroutine

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blackboard import Blackboard
from app.models.instance import Instance
from app.models.workspace import Workspace
from app.models.workspace_agent import WorkspaceAgent
from app.services.runtime import node_card as node_card_service
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.models.workspace_objective import WorkspaceObjective
from app.models.workspace_schedule import WorkspaceSchedule
from app.models.workspace_task import WorkspaceTask
from app.schemas.workspace import (
    AddAgentRequest,
    AgentBrief,
    BlackboardInfo,
    BlackboardSectionPatch,
    BlackboardUpdate,
    ObjectiveCreate,
    ObjectiveInfo,
    ObjectiveUpdate,
    TaskCreate,
    TaskInfo,
    TaskUpdate,
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


def _agent_for_broadcast(inst: Instance, wa: WorkspaceAgent):
    """Object with agent_display_name for broadcast helpers that expect inst."""
    return type("_AgentDisplay", (), {
        "id": inst.id,
        "name": inst.name,
        "agent_display_name": wa.display_name,
    })()


def _agent_brief(inst: Instance, wa: WorkspaceAgent) -> AgentBrief:
    from app.services.sse_listener import sse_listener_manager
    return AgentBrief(
        instance_id=inst.id,
        name=inst.name,
        display_name=wa.display_name,
        label=wa.label,
        slug=inst.slug,
        status=inst.status,
        hex_q=wa.hex_q,
        hex_r=wa.hex_r,
        sse_connected=inst.id in sse_listener_manager.healthy_instances,
        theme_color=wa.theme_color,
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

    await node_card_service.create_node_card(
        db,
        node_type="blackboard",
        node_id=bb.id if bb.id else ws.id,
        workspace_id=ws.id,
        hex_q=0,
        hex_r=0,
        name="Blackboard",
    )

    member = WorkspaceMember(workspace_id=ws.id, user_id=user_id, role=WorkspaceRole.owner, is_admin=True)
    db.add(member)

    schedule = WorkspaceSchedule(
        workspace_id=ws.id,
        name="任务巡检",
        cron_expr="0 */4 * * *",
        message_template="请检查黑板待办任务队列，接取并执行优先级最高的任务。完成后汇报进展。",
        is_active=True,
    )
    db.add(schedule)

    await db.commit()
    await db.refresh(ws)

    if data.template_id:
        await _apply_template_to_workspace(db, ws.id, data.template_id, user_id)

    return WorkspaceInfo(
        id=ws.id, org_id=ws.org_id, name=ws.name, description=ws.description,
        color=ws.color, icon=ws.icon, created_by=ws.created_by,
        agent_count=0, agents=[], created_at=ws.created_at, updated_at=ws.updated_at,
    )


async def _apply_template_to_workspace(
    db: AsyncSession, workspace_id: str, template_id: str, user_id: str,
) -> None:
    """Apply workspace template layout (corridors, connections, blackboard) to a new workspace."""
    import uuid

    from app.models.base import not_deleted
    from app.models.corridor import CorridorHex, HexConnection, ordered_pair
    from app.models.workspace_template import WorkspaceTemplate

    result = await db.execute(
        select(WorkspaceTemplate).where(
            WorkspaceTemplate.id == template_id,
            not_deleted(WorkspaceTemplate),
        )
    )
    tpl = result.scalar_one_or_none()
    if tpl is None:
        logger.warning("Workspace template %s not found, skipping", template_id)
        return

    topo = tpl.topology_snapshot or {}
    bb_snap = tpl.blackboard_snapshot or {}

    for node in topo.get("nodes", []):
        if node.get("node_type") == "corridor":
            ch = CorridorHex(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                hex_q=node.get("hex_q", 0),
                hex_r=node.get("hex_r", 0),
                display_name=node.get("display_name", ""),
                created_by=user_id,
            )
            db.add(ch)

    await db.flush()

    for edge in topo.get("edges", []):
        aq, ar, bq, br = ordered_pair(
            edge.get("a_q", 0), edge.get("a_r", 0),
            edge.get("b_q", 0), edge.get("b_r", 0),
        )
        conn = HexConnection(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            hex_a_q=aq, hex_a_r=ar,
            hex_b_q=bq, hex_b_r=br,
            direction=edge.get("direction", "both"),
            auto_created=edge.get("auto_created", False),
            created_by=user_id,
        )
        db.add(conn)

    if "content" in bb_snap:
        bb_result = await db.execute(
            select(Blackboard).where(Blackboard.workspace_id == workspace_id)
        )
        bb_row = bb_result.scalar_one_or_none()
        if bb_row:
            bb_row.content = bb_snap["content"]

    await db.commit()


async def list_workspaces(
    db: AsyncSession, org_id: str, user_id: str | None = None,
) -> list[WorkspaceListItem]:
    from app.models.org_membership import OrgMembership, OrgRole

    stmt = select(Workspace).where(
        Workspace.org_id == org_id,
        Workspace.deleted_at.is_(None),
    )

    if user_id:
        is_org_admin = (await db.execute(
            select(OrgMembership.role).where(
                OrgMembership.user_id == user_id,
                OrgMembership.org_id == org_id,
                OrgMembership.deleted_at.is_(None),
            )
        )).scalar_one_or_none()

        if is_org_admin != OrgRole.admin:
            member_ws_ids = select(WorkspaceMember.workspace_id).where(
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.deleted_at.is_(None),
            )
            stmt = stmt.where(Workspace.id.in_(member_ws_ids))

    result = await db.execute(stmt.order_by(Workspace.created_at.desc()))
    workspaces = result.scalars().all()

    items = []
    for ws in workspaces:
        agents_result = await db.execute(
            select(Instance, WorkspaceAgent).join(
                WorkspaceAgent,
                (WorkspaceAgent.instance_id == Instance.id) & (WorkspaceAgent.deleted_at.is_(None)),
            ).where(
                WorkspaceAgent.workspace_id == ws.id,
                Instance.deleted_at.is_(None),
            )
        )
        agents = agents_result.all()
        items.append(WorkspaceListItem(
            id=ws.id, name=ws.name, description=ws.description,
            color=ws.color, icon=ws.icon,
            agent_count=len(agents),
            agents=[_agent_brief(inst, wa) for inst, wa in agents],
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
        select(Instance, WorkspaceAgent).join(
            WorkspaceAgent,
            (WorkspaceAgent.instance_id == Instance.id) & (WorkspaceAgent.deleted_at.is_(None)),
        ).where(
            WorkspaceAgent.workspace_id == workspace_id,
            Instance.deleted_at.is_(None),
        )
    )
    agents = agents_result.all()

    return WorkspaceInfo(
        id=ws.id, org_id=ws.org_id, name=ws.name, description=ws.description,
        color=ws.color, icon=ws.icon, created_by=ws.created_by,
        agent_count=len(agents),
        agents=[_agent_brief(inst, wa) for inst, wa in agents],
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
        select(func.count()).select_from(WorkspaceAgent).where(
            WorkspaceAgent.workspace_id == workspace_id,
            WorkspaceAgent.deleted_at.is_(None),
        )
    )
    if (agents_count.scalar() or 0) > 0:
        raise ValueError("请先移除办公室内的所有 AI 员工")

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

    existing_wa = await db.execute(
        select(WorkspaceAgent).where(
            WorkspaceAgent.workspace_id == workspace_id,
            WorkspaceAgent.instance_id == data.instance_id,
            WorkspaceAgent.deleted_at.is_(None),
        )
    )
    if existing_wa.scalar_one_or_none():
        raise ValueError("该员工已在此办公室中")

    if data.hex_q is not None:
        hex_q, hex_r = data.hex_q, data.hex_r or 0
    else:
        existing_count = await db.execute(
            select(func.count()).select_from(WorkspaceAgent).where(
                WorkspaceAgent.workspace_id == workspace_id,
                WorkspaceAgent.deleted_at.is_(None),
            )
        )
        count = existing_count.scalar() or 0
        hex_q, hex_r = _spiral_next(count)

    wa = WorkspaceAgent(
        workspace_id=workspace_id,
        instance_id=inst.id,
        hex_q=hex_q,
        hex_r=hex_r,
        display_name=data.display_name,
    )
    db.add(wa)
    await db.flush()

    await node_card_service.create_node_card(
        db,
        node_type="agent",
        node_id=inst.id,
        workspace_id=workspace_id,
        hex_q=hex_q,
        hex_r=hex_r,
        name=data.display_name or inst.name,
        metadata={"runtime": inst.runtime, "instance_id": inst.id},
    )

    from app.services import corridor_router
    connected = await corridor_router.auto_connect_hex(
        workspace_id, wa.hex_q, wa.hex_r, user_id, db,
    )

    await db.commit()
    await db.refresh(wa)
    await db.refresh(inst)

    if data.install_gene_slugs:
        from app.services.gene_service import install_gene_prerestart
        for slug in data.install_gene_slugs:
            try:
                await install_gene_prerestart(inst.id, slug)
            except Exception as e:
                logger.error("基因安装失败，回滚工作区加入: instance=%s gene=%s error=%s", inst.name, slug, e)
                wa.soft_delete()
                await db.commit()
                raise ValueError(f"基因 {slug} 安装失败: {e}") from e

    await _deploy_channel_plugin(inst, db, workspace_id)

    has_topo = await corridor_router.has_any_connections(workspace_id, db)
    if has_topo:
        await _notify_topology_status(workspace_id, _agent_for_broadcast(inst, wa), connected)

    await _broadcast_join_message(workspace_id, _agent_for_broadcast(inst, wa))
    _fire_task(_send_welcome_message(workspace_id, inst))

    return _agent_brief(inst, wa)


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
        select(WorkspaceAgent, Instance).join(
            Instance,
            (Instance.id == WorkspaceAgent.instance_id) & (Instance.deleted_at.is_(None)),
        ).where(
            WorkspaceAgent.workspace_id == workspace_id,
            WorkspaceAgent.instance_id == instance_id,
            WorkspaceAgent.deleted_at.is_(None),
        )
    )
    row = result.one_or_none()
    if row is None:
        return False
    wa, inst = row

    await _broadcast_leave_message(workspace_id, _agent_for_broadcast(inst, wa))

    from app.models.corridor import HexConnection
    from app.models.base import not_deleted
    hex_q, hex_r = wa.hex_q, wa.hex_r
    conn_result = await db.execute(
        select(HexConnection).where(
            HexConnection.workspace_id == workspace_id,
            not_deleted(HexConnection),
            ((HexConnection.hex_a_q == hex_q) & (HexConnection.hex_a_r == hex_r))
            | ((HexConnection.hex_b_q == hex_q) & (HexConnection.hex_b_r == hex_r)),
        )
    )
    for conn in conn_result.scalars().all():
        conn.soft_delete()

    await _remove_channel_plugin(inst, db, workspace_id)
    wa.soft_delete()
    await node_card_service.soft_delete_node_card(
        db, node_id=instance_id, workspace_id=workspace_id,
    )
    await db.commit()
    return True


async def update_agent(
    db: AsyncSession, workspace_id: str, instance_id: str, data: UpdateAgentRequest,
) -> AgentBrief | None:
    result = await db.execute(
        select(WorkspaceAgent, Instance).join(
            Instance,
            (Instance.id == WorkspaceAgent.instance_id) & (Instance.deleted_at.is_(None)),
        ).where(
            WorkspaceAgent.workspace_id == workspace_id,
            WorkspaceAgent.instance_id == instance_id,
            WorkspaceAgent.deleted_at.is_(None),
        )
    )
    row = result.one_or_none()
    if row is None:
        return None
    wa, inst = row

    if data.display_name is not None:
        wa.display_name = data.display_name or None
    if data.label is not None:
        wa.label = data.label or None
    if data.theme_color is not None:
        wa.theme_color = data.theme_color

    position_changed = False
    old_q, old_r = wa.hex_q, wa.hex_r
    if data.hex_q is not None and data.hex_r is not None:
        new_q, new_r = data.hex_q, data.hex_r
        if (new_q, new_r) != (old_q, old_r):
            wa.hex_q = new_q
            wa.hex_r = new_r
            position_changed = True
    elif data.hex_q is not None:
        wa.hex_q = data.hex_q
    elif data.hex_r is not None:
        wa.hex_r = data.hex_r

    await db.commit()

    if position_changed:
        from app.services import corridor_router
        await corridor_router.cascade_delete_connections(workspace_id, old_q, old_r, db)
        await corridor_router.auto_connect_hex(
            workspace_id, wa.hex_q, wa.hex_r, inst.created_by, db,
        )
        await db.commit()

    await db.refresh(wa)
    await db.refresh(inst)
    return _agent_brief(inst, wa)


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


async def _remove_channel_plugin(inst: Instance, db: AsyncSession, workspace_id: str) -> None:
    """Disconnect SSE + remove channel plugin config for this workspace (or full cleanup if last)."""
    from app.services.sse_listener import sse_listener_manager

    remaining = await db.execute(
        select(func.count()).select_from(WorkspaceAgent).where(
            WorkspaceAgent.instance_id == inst.id,
            WorkspaceAgent.workspace_id != workspace_id,
            WorkspaceAgent.deleted_at.is_(None),
        )
    )
    remaining_count = remaining.scalar() or 0

    if remaining_count == 0:
        await sse_listener_manager.disconnect(inst.id)
        try:
            from app.services.llm_config_service import remove_nodeskclaw_channel_plugin
            await remove_nodeskclaw_channel_plugin(inst, db)
        except Exception as e:
            logger.error("移除 channel plugin 失败（非致命）: instance=%s error=%s", inst.name, e)
    else:
        sse_listener_manager.remove_workspace(inst.id, workspace_id)
        try:
            from app.services.llm_config_service import remove_workspace_channel_account
            await remove_workspace_channel_account(inst, db, workspace_id)
        except Exception as e:
            logger.error(
                "移除工作区 channel 账户失败（非致命）: instance=%s workspace=%s error=%s",
                inst.name, workspace_id, e,
            )


_NODE_TYPE_LABELS = {
    "blackboard": "黑板",
    "corridor": "走廊",
    "agent": "AI 员工",
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
            "请在拓扑编辑器中手动连接，或将 AI 员工拖到已有节点旁边。"
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


WELCOME_MESSAGE = "你好！你刚刚加入了赛博办公室，请向大家介绍一下你自己：你叫什么名字、你的能力和专长是什么。"
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
                content=f"{agent_name} 已加入办公室",
                message_type="system",
            )

        broadcast_event(workspace_id, "system:welcome", {
            "agent_name": agent_name,
            "instance_id": inst.id,
            "content": f"{agent_name} 已加入办公室",
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
    content = f"{agent_name} 已退出办公室"

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
            source_instance_id="system",
            message=WELCOME_MESSAGE,
            depth=0,
        )
    except Exception as e:
        logger.warning("发送欢迎消息失败（非致命）: instance=%s error=%s", inst.name, e)


# ── Blackboard ───────────────────────────────────────

def _task_to_info(t: WorkspaceTask, assignee_name: str | None = None) -> TaskInfo:
    return TaskInfo(
        id=t.id, workspace_id=t.workspace_id, title=t.title,
        description=t.description, status=t.status, priority=t.priority,
        assignee_instance_id=t.assignee_instance_id, assignee_name=assignee_name,
        created_by_instance_id=t.created_by_instance_id,
        estimated_value=t.estimated_value, actual_value=t.actual_value,
        token_cost=t.token_cost, blocker_reason=t.blocker_reason,
        completed_at=t.completed_at, archived_at=t.archived_at,
        created_at=t.created_at, updated_at=t.updated_at,
    )

def _obj_to_info(o: WorkspaceObjective, children: list[ObjectiveInfo] | None = None) -> ObjectiveInfo:
    return ObjectiveInfo(
        id=o.id, workspace_id=o.workspace_id, title=o.title,
        description=o.description, progress=o.progress,
        obj_type=o.obj_type, parent_id=o.parent_id,
        children=children or [],
        created_by=o.created_by,
        created_at=o.created_at, updated_at=o.updated_at,
    )


async def get_blackboard(db: AsyncSession, workspace_id: str) -> BlackboardInfo | None:
    result = await db.execute(
        select(Blackboard).where(Blackboard.workspace_id == workspace_id)
    )
    bb = result.scalar_one_or_none()
    if bb is None:
        return None

    task_rows = (await db.execute(
        select(WorkspaceTask).where(
            WorkspaceTask.workspace_id == workspace_id,
            WorkspaceTask.deleted_at.is_(None),
            WorkspaceTask.archived_at.is_(None),
        ).order_by(WorkspaceTask.created_at.desc())
    )).scalars().all()

    instance_ids = {t.assignee_instance_id for t in task_rows if t.assignee_instance_id}
    assignee_map: dict[str, str] = {}
    if instance_ids:
        insts = (await db.execute(
            select(Instance.id, Instance.name).where(Instance.id.in_(instance_ids))
        )).all()
        assignee_map = {r.id: r.name for r in insts}

    tasks = [_task_to_info(t, assignee_map.get(t.assignee_instance_id)) for t in task_rows]

    obj_rows = (await db.execute(
        select(WorkspaceObjective).where(
            WorkspaceObjective.workspace_id == workspace_id,
            WorkspaceObjective.deleted_at.is_(None),
        ).order_by(WorkspaceObjective.created_at.desc())
    )).scalars().all()
    objectives = [_obj_to_info(o) for o in obj_rows]

    return BlackboardInfo(
        id=bb.id, workspace_id=bb.workspace_id,
        content=bb.content, tasks=tasks, objectives=objectives,
        updated_at=bb.updated_at,
    )


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
    return BlackboardInfo(
        id=bb.id, workspace_id=bb.workspace_id,
        content=bb.content, tasks=[], objectives=[],
        updated_at=bb.updated_at,
    )


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
    return BlackboardInfo(
        id=bb.id, workspace_id=bb.workspace_id,
        content=bb.content, tasks=[], objectives=[],
        updated_at=bb.updated_at,
    )


# ── Tasks ────────────────────────────────────────────

VALID_TASK_STATUSES = {"pending", "in_progress", "done", "blocked", "archived"}
VALID_TASK_PRIORITIES = {"low", "medium", "high", "urgent"}


async def list_tasks(
    db: AsyncSession, workspace_id: str,
    status: str | None = None, exclude_archived: bool = True,
) -> list[TaskInfo]:
    q = select(WorkspaceTask).where(
        WorkspaceTask.workspace_id == workspace_id,
        WorkspaceTask.deleted_at.is_(None),
    )
    if exclude_archived:
        q = q.where(WorkspaceTask.archived_at.is_(None))
    if status:
        q = q.where(WorkspaceTask.status == status)
    q = q.order_by(WorkspaceTask.created_at.desc())
    rows = (await db.execute(q)).scalars().all()

    instance_ids = {t.assignee_instance_id for t in rows if t.assignee_instance_id}
    assignee_map: dict[str, str] = {}
    if instance_ids:
        insts = (await db.execute(
            select(Instance.id, Instance.name).where(Instance.id.in_(instance_ids))
        )).all()
        assignee_map = {r.id: r.name for r in insts}

    return [_task_to_info(t, assignee_map.get(t.assignee_instance_id)) for t in rows]


async def create_task(
    db: AsyncSession, workspace_id: str, data: TaskCreate,
    created_by_instance_id: str | None = None,
) -> TaskInfo:
    task = WorkspaceTask(
        workspace_id=workspace_id,
        title=data.title,
        description=data.description,
        priority=data.priority if data.priority in VALID_TASK_PRIORITIES else "medium",
        assignee_instance_id=data.assignee_id,
        created_by_instance_id=created_by_instance_id,
        estimated_value=data.estimated_value,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    assignee_name = None
    if task.assignee_instance_id:
        inst = (await db.execute(
            select(Instance.name).where(Instance.id == task.assignee_instance_id)
        )).scalar_one_or_none()
        assignee_name = inst
    return _task_to_info(task, assignee_name)


async def update_task(
    db: AsyncSession, workspace_id: str, task_id: str, data: TaskUpdate,
) -> TaskInfo | None:
    from datetime import datetime, timezone as tz

    result = await db.execute(
        select(WorkspaceTask).where(
            WorkspaceTask.id == task_id,
            WorkspaceTask.workspace_id == workspace_id,
            WorkspaceTask.deleted_at.is_(None),
        )
    )
    task = result.scalar_one_or_none()
    if task is None:
        return None

    old_status = task.status

    if data.title is not None:
        task.title = data.title
    if data.description is not None:
        task.description = data.description
    if data.status is not None and data.status in VALID_TASK_STATUSES:
        task.status = data.status
        if data.status == "done" and task.completed_at is None:
            task.completed_at = datetime.now(tz.utc)
        if data.status == "archived" and task.archived_at is None:
            task.archived_at = datetime.now(tz.utc)
    if data.priority is not None and data.priority in VALID_TASK_PRIORITIES:
        task.priority = data.priority
    if data.assignee_id is not None:
        task.assignee_instance_id = data.assignee_id
    if data.estimated_value is not None:
        task.estimated_value = data.estimated_value
    if data.actual_value is not None:
        task.actual_value = data.actual_value
    if data.token_cost is not None:
        task.token_cost = data.token_cost
    if data.blocker_reason is not None:
        task.blocker_reason = data.blocker_reason

    await db.commit()
    await db.refresh(task)

    assignee_name = None
    if task.assignee_instance_id:
        inst = (await db.execute(
            select(Instance.name).where(Instance.id == task.assignee_instance_id)
        )).scalar_one_or_none()
        assignee_name = inst

    new_status = task.status
    status_changed = old_status != new_status

    info = _task_to_info(task, assignee_name)
    return info, status_changed, old_status, new_status


async def archive_task(db: AsyncSession, workspace_id: str, task_id: str) -> TaskInfo | None:
    from datetime import datetime, timezone as tz

    result = await db.execute(
        select(WorkspaceTask).where(
            WorkspaceTask.id == task_id,
            WorkspaceTask.workspace_id == workspace_id,
            WorkspaceTask.deleted_at.is_(None),
        )
    )
    task = result.scalar_one_or_none()
    if task is None:
        return None
    task.status = "archived"
    task.archived_at = datetime.now(tz.utc)
    await db.commit()
    await db.refresh(task)
    return _task_to_info(task)


# ── Objectives ───────────────────────────────────────

async def list_objectives(db: AsyncSession, workspace_id: str, flat: bool = False) -> list[ObjectiveInfo]:
    rows = (await db.execute(
        select(WorkspaceObjective).where(
            WorkspaceObjective.workspace_id == workspace_id,
            WorkspaceObjective.deleted_at.is_(None),
        ).order_by(WorkspaceObjective.created_at.desc())
    )).scalars().all()

    if flat:
        return [_obj_to_info(o) for o in rows]

    by_parent: dict[str | None, list[WorkspaceObjective]] = {}
    for o in rows:
        by_parent.setdefault(o.parent_id, []).append(o)

    def _build(parent_key: str | None) -> list[ObjectiveInfo]:
        items = by_parent.get(parent_key, [])
        result = []
        for o in items:
            child_infos = _build(o.id)
            result.append(_obj_to_info(o, children=child_infos))
        return result

    return _build(None)


async def create_objective(
    db: AsyncSession, workspace_id: str, data: ObjectiveCreate, user_id: str | None = None,
) -> ObjectiveInfo:
    obj = WorkspaceObjective(
        workspace_id=workspace_id,
        title=data.title,
        description=data.description,
        obj_type=data.obj_type,
        parent_id=data.parent_id,
        created_by=user_id,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return _obj_to_info(obj)


async def update_objective(
    db: AsyncSession, workspace_id: str, objective_id: str, data: ObjectiveUpdate,
) -> ObjectiveInfo | None:
    result = await db.execute(
        select(WorkspaceObjective).where(
            WorkspaceObjective.id == objective_id,
            WorkspaceObjective.workspace_id == workspace_id,
            WorkspaceObjective.deleted_at.is_(None),
        )
    )
    obj = result.scalar_one_or_none()
    if obj is None:
        return None
    if data.title is not None:
        obj.title = data.title
    if data.description is not None:
        obj.description = data.description
    if data.progress is not None:
        obj.progress = max(0.0, min(1.0, data.progress))
    if data.obj_type is not None:
        obj.obj_type = data.obj_type
    if data.parent_id is not None:
        obj.parent_id = data.parent_id
    await db.commit()
    await db.refresh(obj)
    return _obj_to_info(obj)


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
            role=wm.role, is_admin=wm.is_admin,
            permissions=wm.permissions or [],
            created_at=wm.created_at,
        ))
    return members


async def add_workspace_member(
    db: AsyncSession,
    workspace_id: str,
    user_id: str,
    permissions: list[str] | None = None,
    is_admin: bool = False,
) -> WorkspaceMemberInfo:
    from app.models.user import User
    from app.models.workspace_member import WORKSPACE_PERMISSIONS

    existing = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError("用户已是办公室成员")

    perms = [p for p in (permissions or []) if p in WORKSPACE_PERMISSIONS]
    wm = WorkspaceMember(
        workspace_id=workspace_id,
        user_id=user_id,
        role="editor",
        is_admin=is_admin,
        permissions=perms,
    )
    db.add(wm)
    await db.commit()

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one()
    return WorkspaceMemberInfo(
        user_id=user.id, user_name=user.name,
        user_email=user.email, user_avatar_url=user.avatar_url,
        role=wm.role, is_admin=wm.is_admin,
        permissions=wm.permissions or [],
        created_at=wm.created_at,
    )


async def update_workspace_member_permissions(
    db: AsyncSession,
    workspace_id: str,
    user_id: str,
    permissions: list[str] | None = None,
    is_admin: bool | None = None,
) -> bool:
    from app.models.workspace_member import WORKSPACE_PERMISSIONS

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
    if permissions is not None:
        wm.permissions = [p for p in permissions if p in WORKSPACE_PERMISSIONS]
    if is_admin is not None:
        wm.is_admin = is_admin
    await db.commit()
    return True


async def remove_workspace_member(
    db: AsyncSession, workspace_id: str, user_id: str, operator_name: str = "",
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

    from app.models.corridor import HumanHex
    from app.models.base import not_deleted
    hh_result = await db.execute(
        select(HumanHex).where(
            HumanHex.workspace_id == workspace_id,
            HumanHex.user_id == user_id,
            not_deleted(HumanHex),
        )
    )
    human_hexes = list(hh_result.scalars().all())

    if human_hexes and operator_name:
        try:
            from app.services.collaboration_service import deliver_to_human
            await deliver_to_human(
                workspace_id=workspace_id,
                human_hex_id=human_hexes[0].id,
                source_name="System",
                message=f"你已被 {operator_name} 移出办公室",
            )
        except Exception as e:
            logger.warning("发送移除通知失败（非致命）: %s", e)

    from app.api.workspaces import broadcast_event
    for hh in human_hexes:
        hh.soft_delete()
        broadcast_event(workspace_id, "human:hex_removed", {"hex_id": hh.id})

    wm.soft_delete()
    await db.commit()
    return True
