"""WorkspaceMessage service — record and retrieve group chat messages."""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace_message import WorkspaceMessage

logger = logging.getLogger(__name__)

NO_REPLY_TOKEN = "NO_REPLY"
MAX_COLLABORATION_DEPTH = 3


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


def build_context_prompt(
    workspace_name: str,
    agent_display_name: str,
    current_instance_id: str,
    members: list[dict],
    recent_messages: list[WorkspaceMessage],
) -> str:
    """Build the system prompt context injected into each Agent call.

    Filters out the current agent's own messages (session already has them).
    """
    members_text = "\n".join(
        f"- [{m['type']}] {m['name']}" for m in members
    )

    other_messages = [
        m for m in recent_messages if m.sender_id != current_instance_id
    ]

    if other_messages:
        msg_lines = []
        for m in other_messages[-30:]:
            ts = m.created_at.strftime("%H:%M") if isinstance(m.created_at, datetime) else ""
            msg_lines.append(f"[{ts} {m.sender_name}]: {m.content}")
        messages_text = "\n".join(msg_lines)
    else:
        messages_text = "(no recent messages from other members)"

    return f"""你是工作区"{workspace_name}"中的 Agent "{agent_display_name}"。

工作区成员:
{members_text}

近期对话（来自其他成员，你自己的历史已在对话记录中）:
{messages_text}

---
你可以直接回复参与讨论。如果当前话题与你无关或你没有要补充的，回复 NO_REPLY 即可。
如需主动联系其他 Agent，使用 send 工具: send -t nodeskclaw -to "agent:{{name}}" -m "消息"
"""


def is_no_reply(text: str) -> bool:
    """Check if text matches the NO_REPLY silent token."""
    return text.strip().upper() == NO_REPLY_TOKEN
