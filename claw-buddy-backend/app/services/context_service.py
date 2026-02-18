"""Context Bus service — CRUD for ContextEntry, AgentShareConfig, AgentSubscription."""

import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_share_config import AgentShareConfig
from app.models.agent_subscription import AgentSubscription
from app.models.context_entry import DEFAULT_TTL, ContextEntry
from app.schemas.workspace import (
    AgentShareConfigInfo,
    AgentShareConfigUpdate,
    AgentSubscriptionInfo,
    AgentSubscriptionUpdate,
    ContextEntryCreate,
    ContextEntryInfo,
)

logger = logging.getLogger(__name__)

SHARE_PATTERN = re.compile(
    r'\[SHARE:(\w+)(?::([^\]]+))?\]\s*(.+?)(?=\[SHARE:|\Z)',
    re.DOTALL,
)


def strip_share_markers(text: str) -> str:
    return SHARE_PATTERN.sub('', text).strip()


def extract_tags(content: str) -> list[str]:
    """Simple keyword extraction from content for tagging."""
    words = re.findall(r'[\w\u4e00-\u9fff]+', content)
    seen: set[str] = set()
    tags: list[str] = []
    for w in words:
        if len(w) >= 2 and w.lower() not in seen:
            seen.add(w.lower())
            tags.append(w)
        if len(tags) >= 5:
            break
    return tags


# ── Context CRUD ─────────────────────────────────────

async def create_context_entry(
    db: AsyncSession, workspace_id: str, source_instance_id: str, data: ContextEntryCreate,
) -> ContextEntryInfo:
    now = datetime.now(timezone.utc)
    ttl = data.ttl_hours or DEFAULT_TTL.get(data.entry_type, 24)
    entry = ContextEntry(
        workspace_id=workspace_id,
        source_instance_id=source_instance_id,
        entry_type=data.entry_type,
        content=data.content,
        tags=data.tags or extract_tags(data.content),
        visibility=data.visibility,
        target_instance_ids=data.target_instance_ids,
        ttl_hours=ttl,
        expires_at=now + timedelta(hours=ttl),
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _entry_info(entry)


async def list_context_entries(
    db: AsyncSession, workspace_id: str, limit: int = 50, entry_type: str | None = None,
) -> list[ContextEntryInfo]:
    now = datetime.now(timezone.utc)
    q = select(ContextEntry).where(
        ContextEntry.workspace_id == workspace_id,
        ContextEntry.expires_at > now,
        ContextEntry.deleted_at.is_(None),
    )
    if entry_type:
        q = q.where(ContextEntry.entry_type == entry_type)
    q = q.order_by(ContextEntry.created_at.desc()).limit(limit)
    result = await db.execute(q)
    return [_entry_info(e) for e in result.scalars().all()]


async def delete_context_entry(db: AsyncSession, entry_id: str) -> bool:
    result = await db.execute(
        select(ContextEntry).where(ContextEntry.id == entry_id, ContextEntry.deleted_at.is_(None))
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        return False
    entry.soft_delete()
    await db.commit()
    return True


async def get_relevant_context(
    db: AsyncSession, agent_id: str, workspace_id: str,
) -> list[ContextEntry]:
    sub_result = await db.execute(
        select(AgentSubscription).where(
            AgentSubscription.instance_id == agent_id,
            AgentSubscription.workspace_id == workspace_id,
        )
    )
    sub = sub_result.scalar_one_or_none()
    max_entries = sub.max_entries if sub else 10

    now = datetime.now(timezone.utc)
    q = select(ContextEntry).where(
        ContextEntry.workspace_id == workspace_id,
        ContextEntry.source_instance_id != agent_id,
        ContextEntry.expires_at > now,
        ContextEntry.deleted_at.is_(None),
        or_(
            ContextEntry.visibility == 'workspace',
            ContextEntry.target_instance_ids.contains([agent_id]),
        ),
    )

    if sub and sub.subscribe_tags:
        q = q.where(ContextEntry.tags.overlap(sub.subscribe_tags))
    if sub and sub.subscribe_types:
        q = q.where(ContextEntry.entry_type.in_(sub.subscribe_types))
    if sub and sub.subscribe_agents:
        q = q.where(ContextEntry.source_instance_id.in_(sub.subscribe_agents))

    q = q.order_by(ContextEntry.created_at.desc()).limit(max_entries)
    result = await db.execute(q)
    return list(result.scalars().all())


async def parse_and_publish(
    db: AsyncSession, workspace_id: str, instance_id: str, response_text: str,
) -> list[ContextEntry]:
    """Parse [SHARE:...] markers from Agent response and store as context entries."""
    matches = SHARE_PATTERN.findall(response_text)
    entries: list[ContextEntry] = []
    now = datetime.now(timezone.utc)

    for entry_type, target_hint, content in matches:
        entry_type = entry_type.strip()
        content = content.strip()
        if not content:
            continue

        ttl = DEFAULT_TTL.get(entry_type, 24)
        entry = ContextEntry(
            workspace_id=workspace_id,
            source_instance_id=instance_id,
            entry_type=entry_type,
            content=content,
            tags=extract_tags(content),
            visibility='targeted' if target_hint else 'workspace',
            target_instance_ids=[],
            ttl_hours=ttl,
            expires_at=now + timedelta(hours=ttl),
        )
        db.add(entry)
        entries.append(entry)

    if entries:
        await db.commit()
        logger.info("Agent %s published %d context entries", instance_id, len(entries))
    return entries


async def cleanup_expired(db: AsyncSession) -> int:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        delete(ContextEntry).where(ContextEntry.expires_at < now)
    )
    await db.commit()
    count = result.rowcount or 0
    if count:
        logger.info("Cleaned up %d expired context entries", count)
    return count


# ── AgentShareConfig ─────────────────────────────────

async def get_share_config(
    db: AsyncSession, instance_id: str, workspace_id: str,
) -> AgentShareConfigInfo | None:
    result = await db.execute(
        select(AgentShareConfig).where(
            AgentShareConfig.instance_id == instance_id,
            AgentShareConfig.workspace_id == workspace_id,
        )
    )
    cfg = result.scalar_one_or_none()
    if cfg is None:
        return None
    return AgentShareConfigInfo(
        instance_id=cfg.instance_id, workspace_id=cfg.workspace_id,
        share_enabled=cfg.share_enabled, share_frequency=cfg.share_frequency,
        share_types=cfg.share_types, custom_instruction=cfg.custom_instruction,
        publish_tags=cfg.publish_tags,
    )


async def update_share_config(
    db: AsyncSession, instance_id: str, workspace_id: str, data: AgentShareConfigUpdate,
) -> AgentShareConfigInfo | None:
    result = await db.execute(
        select(AgentShareConfig).where(
            AgentShareConfig.instance_id == instance_id,
            AgentShareConfig.workspace_id == workspace_id,
        )
    )
    cfg = result.scalar_one_or_none()
    if cfg is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(cfg, field, value)
    await db.commit()
    await db.refresh(cfg)
    return AgentShareConfigInfo(
        instance_id=cfg.instance_id, workspace_id=cfg.workspace_id,
        share_enabled=cfg.share_enabled, share_frequency=cfg.share_frequency,
        share_types=cfg.share_types, custom_instruction=cfg.custom_instruction,
        publish_tags=cfg.publish_tags,
    )


# ── AgentSubscription ────────────────────────────────

async def get_subscription(
    db: AsyncSession, instance_id: str, workspace_id: str,
) -> AgentSubscriptionInfo | None:
    result = await db.execute(
        select(AgentSubscription).where(
            AgentSubscription.instance_id == instance_id,
            AgentSubscription.workspace_id == workspace_id,
        )
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        return None
    return AgentSubscriptionInfo(
        instance_id=sub.instance_id, workspace_id=sub.workspace_id,
        subscribe_tags=sub.subscribe_tags, subscribe_types=sub.subscribe_types,
        subscribe_agents=sub.subscribe_agents, max_entries=sub.max_entries,
    )


async def update_subscription(
    db: AsyncSession, instance_id: str, workspace_id: str, data: AgentSubscriptionUpdate,
) -> AgentSubscriptionInfo | None:
    result = await db.execute(
        select(AgentSubscription).where(
            AgentSubscription.instance_id == instance_id,
            AgentSubscription.workspace_id == workspace_id,
        )
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(sub, field, value)
    await db.commit()
    await db.refresh(sub)
    return AgentSubscriptionInfo(
        instance_id=sub.instance_id, workspace_id=sub.workspace_id,
        subscribe_tags=sub.subscribe_tags, subscribe_types=sub.subscribe_types,
        subscribe_agents=sub.subscribe_agents, max_entries=sub.max_entries,
    )


def _entry_info(e: ContextEntry) -> ContextEntryInfo:
    return ContextEntryInfo(
        id=e.id, workspace_id=e.workspace_id, source_instance_id=e.source_instance_id,
        entry_type=e.entry_type, content=e.content, tags=e.tags,
        visibility=e.visibility, target_instance_ids=e.target_instance_ids,
        ttl_hours=e.ttl_hours, expires_at=e.expires_at, created_at=e.created_at,
    )
