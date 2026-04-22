"""WorkspaceMessage service — record and retrieve group chat messages."""

import logging
from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace_message import WorkspaceMessage

logger = logging.getLogger(__name__)

NO_REPLY_TOKEN = "NO_REPLY"
_NO_REPLY_VARIANTS = frozenset({"no_reply", "no reply", "noreply"})
DEFAULT_COLLABORATION_DEPTH = 3
ABSOLUTE_MAX_COLLABORATION_DEPTH = 20


async def get_collaboration_depth_limit(db: AsyncSession, workspace_id: str) -> int:
    """从 workspace 所属组织读取协作深度限制，查不到则回退默认值。"""
    from app.models.organization import Organization
    from app.models.workspace import Workspace

    result = await db.execute(
        select(Organization.max_collaboration_depth)
        .join(Workspace, Workspace.org_id == Organization.id)
        .where(Workspace.id == workspace_id)
    )
    value = result.scalar_one_or_none()
    if value is None:
        return DEFAULT_COLLABORATION_DEPTH
    return min(value, ABSOLUTE_MAX_COLLABORATION_DEPTH)


async def record_message(
    db: AsyncSession,
    *,
    workspace_id: str,
    sender_type: str,
    sender_id: str,
    sender_name: str,
    content: str,
    message_type: str = "chat",
    target_instance_id: str | None = None,
    depth: int = 0,
    attachments: list[dict] | None = None,
) -> WorkspaceMessage:
    msg = WorkspaceMessage(
        workspace_id=workspace_id,
        sender_type=sender_type,
        sender_id=sender_id,
        sender_name=sender_name,
        content=content,
        message_type=message_type,
        target_instance_id=target_instance_id,
        depth=depth,
        attachments=attachments,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


async def get_recent_messages(
    db: AsyncSession,
    workspace_id: str,
    limit: int = 50,
) -> list[WorkspaceMessage]:
    result = await db.execute(
        select(WorkspaceMessage)
        .where(
            WorkspaceMessage.workspace_id == workspace_id,
            WorkspaceMessage.deleted_at.is_(None),
        )
        .order_by(WorkspaceMessage.created_at.desc())
        .limit(limit)
    )
    messages = list(result.scalars().all())
    messages.reverse()
    return messages


async def search_messages(
    db: AsyncSession,
    workspace_id: str,
    *,
    q: str | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    limit: int = 200,
) -> list[WorkspaceMessage]:
    stmt = (
        select(WorkspaceMessage)
        .where(
            WorkspaceMessage.workspace_id == workspace_id,
            WorkspaceMessage.deleted_at.is_(None),
        )
    )

    keyword = (q or "").strip()
    if keyword:
        pattern = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                WorkspaceMessage.content.ilike(pattern),
                WorkspaceMessage.sender_name.ilike(pattern),
            )
        )

    if from_at:
        stmt = stmt.where(WorkspaceMessage.created_at >= from_at)
    if to_at:
        stmt = stmt.where(WorkspaceMessage.created_at <= to_at)

    result = await db.execute(
        stmt.order_by(WorkspaceMessage.created_at.desc()).limit(limit)
    )
    messages = list(result.scalars().all())
    messages.reverse()
    return messages


async def get_collaboration_timeline(
    db: AsyncSession,
    workspace_id: str,
    limit: int = 100,
    since: datetime | None = None,
) -> list[WorkspaceMessage]:
    q = (
        select(WorkspaceMessage)
        .where(
            WorkspaceMessage.workspace_id == workspace_id,
            WorkspaceMessage.message_type == "collaboration",
            WorkspaceMessage.deleted_at.is_(None),
        )
    )
    if since:
        q = q.where(WorkspaceMessage.created_at > since)
    result = await db.execute(q.order_by(WorkspaceMessage.created_at.desc()).limit(limit))
    messages = list(result.scalars().all())
    messages.reverse()
    return messages


async def get_agent_collaboration_messages(
    db: AsyncSession,
    workspace_id: str,
    instance_id: str,
    limit: int = 50,
) -> list[WorkspaceMessage]:
    result = await db.execute(
        select(WorkspaceMessage)
        .where(
            WorkspaceMessage.workspace_id == workspace_id,
            WorkspaceMessage.message_type == "collaboration",
            WorkspaceMessage.deleted_at.is_(None),
            or_(
                WorkspaceMessage.sender_id == instance_id,
                WorkspaceMessage.target_instance_id == instance_id,
            ),
        )
        .order_by(WorkspaceMessage.created_at.desc())
        .limit(limit)
    )
    messages = list(result.scalars().all())
    messages.reverse()
    return messages


async def clear_workspace_messages(
    db: AsyncSession,
    workspace_id: str,
) -> int:
    result = await db.execute(
        update(WorkspaceMessage)
        .where(
            WorkspaceMessage.workspace_id == workspace_id,
            WorkspaceMessage.deleted_at.is_(None),
        )
        .values(deleted_at=func.now())
    )
    await db.commit()
    return result.rowcount or 0


def build_context_prompt(
    workspace_name: str,
    agent_display_name: str,
    current_instance_id: str,
    members: list[dict],
    recent_messages: list[WorkspaceMessage],
    workspace_id: str = "",
) -> str:
    """Build the system prompt context injected into each Agent call."""
    members_text = "\n".join(
        f"- [{m['type']}] {m['name']}" for m in members
    )

    all_messages = recent_messages

    if all_messages:
        msg_lines = []
        for m in all_messages[-30:]:
            ts = m.created_at.strftime("%H:%M") if isinstance(m.created_at, datetime) else ""
            line = f"[{ts} {m.sender_name}]: {m.content}"
            if m.attachments:
                for idx, att in enumerate(m.attachments, 1):
                    size = att.get("size", 0)
                    if size >= 1024 * 1024:
                        size_str = f"{size / (1024 * 1024):.1f}MB"
                    elif size >= 1024:
                        size_str = f"{size / 1024:.0f}KB"
                    else:
                        size_str = f"{size}B"
                    fid = att.get("id", "")
                    line += f"\n  [附件{idx}: {att.get('name', '?')} ({size_str}), file_id: {fid}]"
            msg_lines.append(line)
        messages_text = "\n".join(msg_lines)
    else:
        messages_text = "(no recent messages)"

    return f"""你是赛博办公室"{workspace_name}"中的 AI 员工"{agent_display_name}"。

办公室成员:
{members_text}

近期对话:
{messages_text}

---
你可以直接回复参与讨论。如果当前话题与你无关或你没有要补充的，回复 NO_REPLY 即可。
注意：办公室成员列表仅供了解同事身份，不代表你可以和所有人通讯。办公室使用过道系统连接工位，你只能联系通过过道与你相连的成员。
如需确认你能联系谁，必须调用 nodeskclaw_topology 工具（action: get_reachable, my_instance_id: 你的实例 ID）。未经工具确认，不要声称可以联系任何人。
当你回复或联系其他成员（AI 员工或人类）时，在回复中直接 @{{name}} 即可（如"@test-2 你好"），系统会自动转发。收到其他成员的消息后回复时，也请 @提及对方，这样系统才能正确路由你的回复。不要用 send 命令。
办公室设有中央黑板（get_reachable 中 node_type=blackboard 的节点），通过 nodeskclaw_blackboard 工具读写黑板内容，不要 @提及黑板。
如需回顾更早的对话记录，使用 nodeskclaw_chat_history 工具搜索历史消息。
"""


def is_no_reply(text: str) -> bool:
    """Check if text is a silent-skip response that should not be shown to users.

    Matches exact tokens ("NO_REPLY", "no reply", "noreply") and responses where
    the agent prepends filler text before the token (e.g. "这不是给我的\\nNO_REPLY").
    Bare "no" is intentionally excluded to avoid swallowing legitimate short replies.
    """
    normalized = text.strip().lower()
    if normalized in _NO_REPLY_VARIANTS:
        return True
    lines = [ln.strip().lower() for ln in text.strip().splitlines() if ln.strip()]
    if lines and lines[-1] in _NO_REPLY_VARIANTS:
        return True
    return False
