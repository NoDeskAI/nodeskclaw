"""Agent Device service — placement, discovery, grants, leases, invocation and gene sync."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import hooks
from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.models.agent_device import (
    AgentDeviceGeneBinding,
    AgentDeviceGrant,
    AgentDeviceInstance,
    AgentDeviceLease,
    AgentDevicePresetEnablement,
)
from app.models.base import not_deleted
from app.models.corridor import CorridorHex, HexConnection, HumanHex
from app.models.gene import Gene, InstanceGene, InstanceGeneStatus
from app.models.instance import Instance
from app.models.node_card import NodeCard
from app.models.workspace import Workspace
from app.models.workspace_agent import WorkspaceAgent
from app.services import corridor_router
from app.services.agent_device_provider import (
    get_agent_device_preset,
    get_agent_device_provider,
    list_agent_device_presets,
)
from app.services.runtime import node_card as node_card_service

logger = logging.getLogger(__name__)

DEVICE_GRANT_SCOPES = {"discover", "lease", "invoke", "delegate"}
DEVICE_SUBJECT_TYPES = {"agent", "human"}
DEFAULT_DELEGATE_TTL_MINUTES = 30
DEFAULT_LEASE_TTL_SECONDS = 900


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _scope_list(scopes: list[str]) -> list[str]:
    normalized = sorted(set(scopes))
    invalid = [scope for scope in normalized if scope not in DEVICE_GRANT_SCOPES]
    if invalid:
        raise BadRequestError(
            f"不支持的设备授权 scope: {', '.join(invalid)}",
            "errors.agent_device.invalid_scope",
        )
    if not normalized:
        raise BadRequestError("授权 scope 不能为空", "errors.agent_device.scope_required")
    return normalized


def _status_for_device(device: AgentDeviceInstance) -> tuple[str, str | None]:
    provider = get_agent_device_provider(device.provider_id)
    if provider is None:
        return "provider_unconfigured", "provider_missing"
    status = provider.status()
    return status.status, status.reason


async def check_workspace(workspace_id: str, org_id: str | None, db: AsyncSession) -> Workspace:
    stmt = select(Workspace).where(Workspace.id == workspace_id, not_deleted(Workspace))
    if org_id:
        stmt = stmt.where(Workspace.org_id == org_id)
    workspace = (await db.execute(stmt)).scalar_one_or_none()
    if not workspace:
        raise NotFoundError("办公室不存在", "errors.workspace.not_found")
    return workspace


async def is_hex_occupied(
    db: AsyncSession,
    *,
    workspace_id: str,
    hex_q: int,
    hex_r: int,
    exclude_node_id: str | None = None,
) -> bool:
    if (hex_q, hex_r) == (0, 0):
        return True

    card = await db.execute(
        select(NodeCard.node_id).where(
            NodeCard.workspace_id == workspace_id,
            NodeCard.hex_q == hex_q,
            NodeCard.hex_r == hex_r,
            not_deleted(NodeCard),
        ).limit(1)
    )
    card_node_id = card.scalar_one_or_none()
    if card_node_id and card_node_id != exclude_node_id:
        return True

    legacy_checks = (
        select(WorkspaceAgent.instance_id).where(
            WorkspaceAgent.workspace_id == workspace_id,
            WorkspaceAgent.hex_q == hex_q,
            WorkspaceAgent.hex_r == hex_r,
            not_deleted(WorkspaceAgent),
        ),
        select(CorridorHex.id).where(
            CorridorHex.workspace_id == workspace_id,
            CorridorHex.hex_q == hex_q,
            CorridorHex.hex_r == hex_r,
            not_deleted(CorridorHex),
        ),
        select(HumanHex.id).where(
            HumanHex.workspace_id == workspace_id,
            HumanHex.hex_q == hex_q,
            HumanHex.hex_r == hex_r,
            not_deleted(HumanHex),
        ),
        select(AgentDeviceInstance.id).where(
            AgentDeviceInstance.workspace_id == workspace_id,
            AgentDeviceInstance.hex_q == hex_q,
            AgentDeviceInstance.hex_r == hex_r,
            not_deleted(AgentDeviceInstance),
        ),
    )
    for stmt in legacy_checks:
        found = (await db.execute(stmt.limit(1))).scalar_one_or_none()
        if found and found != exclude_node_id:
            return True
    return False


async def get_preset_enablement(
    db: AsyncSession,
    *,
    workspace_id: str,
    preset_id: str,
) -> AgentDevicePresetEnablement | None:
    return (await db.execute(
        select(AgentDevicePresetEnablement).where(
            AgentDevicePresetEnablement.workspace_id == workspace_id,
            AgentDevicePresetEnablement.preset_id == preset_id,
            not_deleted(AgentDevicePresetEnablement),
        )
    )).scalar_one_or_none()


async def get_preset_info(db: AsyncSession, *, workspace_id: str, preset_id: str) -> dict:
    preset = get_agent_device_preset(preset_id)
    if preset is None:
        raise NotFoundError("办公设施预设不存在", "errors.agent_device.preset_not_found")

    enablement = await get_preset_enablement(db, workspace_id=workspace_id, preset_id=preset_id)
    enabled = True if enablement is None else enablement.enabled
    provider = get_agent_device_provider(preset.provider_id)
    provider_status = provider.status() if provider else None
    return {
        "preset_id": preset.preset_id,
        "provider_id": preset.provider_id,
        "display_name": preset.display_name,
        "description": preset.description,
        "gene_slug": preset.gene_slug,
        "capability_schema": preset.capability_schema,
        "enabled": enabled,
        "config": enablement.config if enablement else preset.default_config,
        "provider_status": provider_status.status if provider_status else "provider_unconfigured",
        "provider_status_reason": provider_status.reason if provider_status else "provider_missing",
    }


async def list_preset_infos(db: AsyncSession, *, workspace_id: str) -> list[dict]:
    return [await get_preset_info(db, workspace_id=workspace_id, preset_id=p.preset_id) for p in list_agent_device_presets()]


async def set_preset_enablement(
    db: AsyncSession,
    *,
    workspace_id: str,
    preset_id: str,
    enabled: bool,
    config: dict | None,
    actor_id: str | None,
    org_id: str | None,
) -> dict:
    preset = get_agent_device_preset(preset_id)
    if preset is None:
        raise NotFoundError("办公设施预设不存在", "errors.agent_device.preset_not_found")
    row = await get_preset_enablement(db, workspace_id=workspace_id, preset_id=preset_id)
    if row is None:
        row = AgentDevicePresetEnablement(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            preset_id=preset_id,
            enabled=enabled,
            config=config,
            created_by=actor_id,
            updated_by=actor_id,
        )
        db.add(row)
    else:
        row.enabled = enabled
        row.config = config
        row.updated_by = actor_id
    await db.flush()
    await hooks.emit(
        "operation_audit",
        action="agent_device.preset_enabled" if enabled else "agent_device.preset_disabled",
        target_type="agent_device_preset",
        target_id=preset_id,
        actor_id=actor_id or "",
        actor_type="user",
        org_id=org_id,
        workspace_id=workspace_id,
        details={"preset_id": preset_id, "enabled": enabled},
    )
    return await get_preset_info(db, workspace_id=workspace_id, preset_id=preset_id)


async def ensure_preset_available(db: AsyncSession, *, workspace_id: str, preset_id: str) -> str:
    info = await get_preset_info(db, workspace_id=workspace_id, preset_id=preset_id)
    if not info["enabled"]:
        raise ForbiddenError("该办公设施预设已停用", "errors.agent_device.preset_disabled")
    return info["provider_id"]


async def get_device(db: AsyncSession, *, workspace_id: str, device_id: str) -> AgentDeviceInstance:
    device = (await db.execute(
        select(AgentDeviceInstance).where(
            AgentDeviceInstance.id == device_id,
            AgentDeviceInstance.workspace_id == workspace_id,
            not_deleted(AgentDeviceInstance),
        )
    )).scalar_one_or_none()
    if device is None:
        raise NotFoundError("办公设施不存在", "errors.agent_device.not_found")
    return device


async def list_devices(db: AsyncSession, *, workspace_id: str) -> list[AgentDeviceInstance]:
    result = await db.execute(
        select(AgentDeviceInstance).where(
            AgentDeviceInstance.workspace_id == workspace_id,
            not_deleted(AgentDeviceInstance),
        ).order_by(AgentDeviceInstance.created_at.desc())
    )
    devices = list(result.scalars().all())
    for device in devices:
        device.status, device.status_reason = _status_for_device(device)
    return devices


async def create_device(
    db: AsyncSession,
    *,
    workspace_id: str,
    preset_id: str,
    display_name: str,
    hex_q: int,
    hex_r: int,
    config: dict | None,
    metadata: dict | None,
    actor_id: str | None,
    org_id: str | None,
) -> AgentDeviceInstance:
    provider_id = await ensure_preset_available(db, workspace_id=workspace_id, preset_id=preset_id)
    if await is_hex_occupied(db, workspace_id=workspace_id, hex_q=hex_q, hex_r=hex_r):
        raise ConflictError("当前位置已被占用", "errors.corridor.hex_position_occupied")

    device = AgentDeviceInstance(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        preset_id=preset_id,
        provider_id=provider_id,
        display_name=display_name,
        hex_q=hex_q,
        hex_r=hex_r,
        config=config,
        metadata_=metadata,
        created_by=actor_id,
    )
    device.status, device.status_reason = _status_for_device(device)
    db.add(device)
    await node_card_service.create_node_card(
        db,
        node_type="device",
        node_id=device.id,
        workspace_id=workspace_id,
        hex_q=hex_q,
        hex_r=hex_r,
        name=display_name,
        status=device.status,
        metadata={
            "preset_id": preset_id,
            "provider_id": provider_id,
            "status_reason": device.status_reason,
            "protocol_name": "Agent Device",
        },
    )
    await corridor_router.auto_connect_hex(workspace_id, hex_q, hex_r, actor_id, db)
    await hooks.emit(
        "operation_audit",
        action="agent_device.created",
        target_type="agent_device",
        target_id=device.id,
        actor_id=actor_id or "",
        actor_type="user",
        org_id=org_id,
        workspace_id=workspace_id,
        details={"preset_id": preset_id, "provider_id": provider_id, "hex_q": hex_q, "hex_r": hex_r},
    )
    return device


async def update_device(
    db: AsyncSession,
    *,
    workspace_id: str,
    device_id: str,
    display_name: str | None = None,
    hex_q: int | None = None,
    hex_r: int | None = None,
    config: dict | None = None,
    metadata: dict | None = None,
    actor_id: str | None = None,
    org_id: str | None = None,
) -> tuple[AgentDeviceInstance, bool]:
    device = await get_device(db, workspace_id=workspace_id, device_id=device_id)
    old_q, old_r = device.hex_q, device.hex_r
    new_q = device.hex_q if hex_q is None else hex_q
    new_r = device.hex_r if hex_r is None else hex_r
    position_changed = (new_q, new_r) != (old_q, old_r)
    if position_changed and await is_hex_occupied(
        db, workspace_id=workspace_id, hex_q=new_q, hex_r=new_r, exclude_node_id=device.id
    ):
        raise ConflictError("当前位置已被占用", "errors.corridor.hex_position_occupied")

    if display_name is not None:
        device.display_name = display_name
    if position_changed:
        device.hex_q = new_q
        device.hex_r = new_r
    if config is not None:
        device.config = config
    if metadata is not None:
        device.metadata_ = metadata
    device.status, device.status_reason = _status_for_device(device)

    card = await node_card_service.get_node_card(db, node_id=device.id, workspace_id=workspace_id)
    if card:
        card_meta = card.metadata_ or {}
        card_meta.update({
            "preset_id": device.preset_id,
            "provider_id": device.provider_id,
            "status_reason": device.status_reason,
            "protocol_name": "Agent Device",
        })
        updates: dict[str, Any] = {"status": device.status, "metadata": card_meta}
        if display_name is not None:
            updates["name"] = device.display_name
        if position_changed:
            updates["hex_q"] = device.hex_q
            updates["hex_r"] = device.hex_r
        await node_card_service.update_node_card(db, card, **updates)

    if position_changed:
        await corridor_router.cascade_delete_connections(workspace_id, old_q, old_r, db)
        await corridor_router.auto_connect_hex(workspace_id, device.hex_q, device.hex_r, actor_id, db)

    await hooks.emit(
        "operation_audit",
        action="agent_device.updated",
        target_type="agent_device",
        target_id=device.id,
        actor_id=actor_id or "",
        actor_type="user",
        org_id=org_id,
        workspace_id=workspace_id,
        details={"position_changed": position_changed, "hex_q": device.hex_q, "hex_r": device.hex_r},
    )
    return device, position_changed


async def delete_device(
    db: AsyncSession,
    *,
    workspace_id: str,
    device_id: str,
    actor_id: str | None,
    org_id: str | None,
) -> AgentDeviceInstance:
    device = await get_device(db, workspace_id=workspace_id, device_id=device_id)
    active_leases = await db.execute(
        select(AgentDeviceLease).where(
            AgentDeviceLease.device_id == device_id,
            AgentDeviceLease.status == "active",
            not_deleted(AgentDeviceLease),
        )
    )
    for lease in active_leases.scalars().all():
        lease.status = "reclaimed"
        lease.released_at = utc_now()

    grants = await db.execute(
        select(AgentDeviceGrant).where(
            AgentDeviceGrant.device_id == device_id,
            not_deleted(AgentDeviceGrant),
        )
    )
    for grant in grants.scalars().all():
        grant.revoked_at = utc_now()
        grant.soft_delete()

    bindings = await db.execute(
        select(AgentDeviceGeneBinding).where(
            AgentDeviceGeneBinding.device_id == device_id,
            not_deleted(AgentDeviceGeneBinding),
        )
    )
    for binding in bindings.scalars().all():
        instance = await db.get(Instance, binding.instance_id)
        if instance is None:
            binding.sync_reason = "device_deleted"
            binding.soft_delete()
            continue
        await withdraw_gene_binding(
            db,
            workspace_id=workspace_id,
            device=device,
            instance=instance,
            gene_slug=binding.gene_slug,
            reason="device_deleted",
        )

    conns = await db.execute(
        select(HexConnection).where(
            HexConnection.workspace_id == workspace_id,
            not_deleted(HexConnection),
            or_(
                and_(HexConnection.hex_a_q == device.hex_q, HexConnection.hex_a_r == device.hex_r),
                and_(HexConnection.hex_b_q == device.hex_q, HexConnection.hex_b_r == device.hex_r),
            ),
        )
    )
    for conn in conns.scalars().all():
        conn.soft_delete()

    await node_card_service.soft_delete_node_card(db, node_id=device_id, workspace_id=workspace_id)
    device.soft_delete()
    await hooks.emit(
        "operation_audit",
        action="agent_device.deleted",
        target_type="agent_device",
        target_id=device.id,
        actor_id=actor_id or "",
        actor_type="user",
        org_id=org_id,
        workspace_id=workspace_id,
        details={"preset_id": device.preset_id},
    )
    return device


async def _valid_grant_query(
    *,
    workspace_id: str,
    device_id: str,
    subject_type: str,
    subject_id: str,
):
    now = utc_now()
    return select(AgentDeviceGrant).where(
        AgentDeviceGrant.workspace_id == workspace_id,
        AgentDeviceGrant.device_id == device_id,
        AgentDeviceGrant.subject_type == subject_type,
        AgentDeviceGrant.subject_id == subject_id,
        AgentDeviceGrant.revoked_at.is_(None),
        or_(AgentDeviceGrant.expires_at.is_(None), AgentDeviceGrant.expires_at > now),
        not_deleted(AgentDeviceGrant),
    )


async def find_valid_grant(
    db: AsyncSession,
    *,
    workspace_id: str,
    device_id: str,
    subject_type: str,
    subject_id: str,
    required_scope: str,
) -> AgentDeviceGrant | None:
    stmt = await _valid_grant_query(
        workspace_id=workspace_id,
        device_id=device_id,
        subject_type=subject_type,
        subject_id=subject_id,
    )
    result = await db.execute(stmt)
    now = utc_now()
    for grant in result.scalars().all():
        if required_scope in (grant.scopes or []) and await _grant_parent_chain_is_valid(
            db,
            workspace_id=workspace_id,
            device_id=device_id,
            grant=grant,
            now=now,
        ):
            return grant
    return None


async def _grant_parent_chain_is_valid(
    db: AsyncSession,
    *,
    workspace_id: str,
    device_id: str,
    grant: AgentDeviceGrant,
    now: datetime,
) -> bool:
    current_id = grant.parent_grant_id
    visited = {grant.id}
    while current_id:
        if current_id in visited:
            return False
        visited.add(current_id)
        parent = await db.get(AgentDeviceGrant, current_id)
        if (
            parent is None
            or parent.workspace_id != workspace_id
            or parent.device_id != device_id
            or parent.revoked_at is not None
            or parent.deleted_at is not None
            or (parent.expires_at is not None and parent.expires_at <= now)
        ):
            return False
        current_id = parent.parent_grant_id
    return True


async def create_grant(
    db: AsyncSession,
    *,
    workspace_id: str,
    device_id: str,
    subject_type: str,
    subject_id: str,
    scopes: list[str],
    can_delegate: bool,
    parent_grant_id: str | None,
    expires_at: datetime | None,
    granted_by_type: str,
    granted_by_id: str,
    org_id: str | None,
) -> AgentDeviceGrant:
    await get_device(db, workspace_id=workspace_id, device_id=device_id)
    if subject_type not in DEVICE_SUBJECT_TYPES:
        raise BadRequestError("授权对象类型必须是 agent 或 human", "errors.agent_device.invalid_subject_type")
    normalized_scopes = _scope_list(scopes)
    if granted_by_type == "agent" and subject_type != "agent":
        raise BadRequestError("Agent 只能委托办公设施权限给其他 Agent", "errors.agent_device.delegate_subject_required")

    parent: AgentDeviceGrant | None = None
    if granted_by_type == "agent":
        parent_stmt = await _valid_grant_query(
            workspace_id=workspace_id,
            device_id=device_id,
            subject_type="agent",
            subject_id=granted_by_id,
        )
        if parent_grant_id:
            parent_stmt = parent_stmt.where(AgentDeviceGrant.id == parent_grant_id)
        parent_result = await db.execute(parent_stmt)
        for candidate in parent_result.scalars().all():
            parent_scopes = set(candidate.scopes or [])
            if (
                candidate.can_delegate
                and "delegate" in parent_scopes
                and set(normalized_scopes).issubset(parent_scopes)
            ):
                parent = candidate
                break
        if parent is None:
            raise ForbiddenError("当前 Agent 没有委托该办公设施权限", "errors.agent_device.delegate_forbidden")
        parent_grant_id = parent.id
        parent_expiry = parent.expires_at
        if expires_at is None:
            expires_at = utc_now() + timedelta(minutes=DEFAULT_DELEGATE_TTL_MINUTES)
        if parent_expiry is not None and expires_at > parent_expiry:
            expires_at = parent_expiry
        can_delegate = can_delegate and "delegate" in normalized_scopes
    elif parent_grant_id:
        parent = await db.get(AgentDeviceGrant, parent_grant_id)
        if parent is None or parent.device_id != device_id:
            raise BadRequestError("父授权不存在", "errors.agent_device.parent_grant_not_found")

    grant = AgentDeviceGrant(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        device_id=device_id,
        subject_type=subject_type,
        subject_id=subject_id,
        scopes=normalized_scopes,
        can_delegate=can_delegate,
        parent_grant_id=parent_grant_id,
        granted_by_type=granted_by_type,
        granted_by_id=granted_by_id,
        expires_at=expires_at,
    )
    db.add(grant)
    await hooks.emit(
        "operation_audit",
        action="agent_device.grant_created",
        target_type="agent_device",
        target_id=device_id,
        actor_id=granted_by_id,
        actor_type=granted_by_type,
        org_id=org_id,
        workspace_id=workspace_id,
        details={
            "grant_id": grant.id,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "scopes": normalized_scopes,
            "can_delegate": can_delegate,
            "parent_grant_id": parent_grant_id,
        },
    )
    return grant


async def revoke_grant(
    db: AsyncSession,
    *,
    workspace_id: str,
    device_id: str,
    grant_id: str,
    actor_type: str,
    actor_id: str,
    org_id: str | None,
) -> AgentDeviceGrant:
    grant = (await db.execute(
        select(AgentDeviceGrant).where(
            AgentDeviceGrant.id == grant_id,
            AgentDeviceGrant.device_id == device_id,
            AgentDeviceGrant.workspace_id == workspace_id,
            not_deleted(AgentDeviceGrant),
        )
    )).scalar_one_or_none()
    if grant is None:
        raise NotFoundError("设备授权不存在", "errors.agent_device.grant_not_found")
    if actor_type == "agent" and grant.granted_by_id != actor_id:
        raise ForbiddenError("Agent 只能撤销自己委托的设备授权", "errors.agent_device.revoke_forbidden")
    descendants = await _descendant_grants(
        db,
        workspace_id=workspace_id,
        device_id=device_id,
        grant_id=grant.id,
    )
    revoked_at = utc_now()
    revoked_grants = [grant, *descendants]
    for revoked_grant in revoked_grants:
        revoked_grant.revoked_at = revoked_at
        revoked_grant.soft_delete()
    reclaimed_lease_count = await _reclaim_active_leases_for_grants(
        db,
        workspace_id=workspace_id,
        device_id=device_id,
        grant_ids=[revoked_grant.id for revoked_grant in revoked_grants],
    )
    await hooks.emit(
        "operation_audit",
        action="agent_device.grant_revoked",
        target_type="agent_device",
        target_id=device_id,
        actor_id=actor_id,
        actor_type=actor_type,
        org_id=org_id,
        workspace_id=workspace_id,
        details={
            "grant_id": grant_id,
            "subject_type": grant.subject_type,
            "subject_id": grant.subject_id,
            "descendant_grant_ids": [descendant.id for descendant in descendants],
            "reclaimed_lease_count": reclaimed_lease_count,
        },
    )
    return grant


async def _descendant_grants(
    db: AsyncSession,
    *,
    workspace_id: str,
    device_id: str,
    grant_id: str,
) -> list[AgentDeviceGrant]:
    descendants: list[AgentDeviceGrant] = []
    pending = [grant_id]
    visited = {grant_id}
    while pending:
        current_id = pending.pop()
        result = await db.execute(
            select(AgentDeviceGrant).where(
                AgentDeviceGrant.workspace_id == workspace_id,
                AgentDeviceGrant.device_id == device_id,
                AgentDeviceGrant.parent_grant_id == current_id,
                not_deleted(AgentDeviceGrant),
            )
        )
        for child in result.scalars().all():
            if child.id in visited:
                continue
            visited.add(child.id)
            descendants.append(child)
            pending.append(child.id)
    return descendants


async def _reclaim_active_leases_for_grants(
    db: AsyncSession,
    *,
    workspace_id: str,
    device_id: str,
    grant_ids: list[str],
) -> int:
    if not grant_ids:
        return 0
    result = await db.execute(
        select(AgentDeviceLease).where(
            AgentDeviceLease.workspace_id == workspace_id,
            AgentDeviceLease.device_id == device_id,
            AgentDeviceLease.grant_id.in_(grant_ids),
            AgentDeviceLease.status == "active",
            not_deleted(AgentDeviceLease),
        )
    )
    reclaimed_at = utc_now()
    reclaimed_count = 0
    for lease in result.scalars().all():
        lease.status = "reclaimed"
        lease.released_at = reclaimed_at
        reclaimed_count += 1
    return reclaimed_count


async def _is_grant_ancestor(
    db: AsyncSession,
    *,
    workspace_id: str,
    device_id: str,
    ancestor_grant_id: str,
    descendant_grant_id: str,
) -> bool:
    current_id: str | None = descendant_grant_id
    visited: set[str] = set()
    while current_id and current_id not in visited:
        visited.add(current_id)
        grant = (await db.execute(
            select(AgentDeviceGrant).where(
                AgentDeviceGrant.id == current_id,
                AgentDeviceGrant.workspace_id == workspace_id,
                AgentDeviceGrant.device_id == device_id,
                not_deleted(AgentDeviceGrant),
            )
        )).scalar_one_or_none()
        if grant is None:
            return False
        if grant.id == ancestor_grant_id:
            return True
        current_id = grant.parent_grant_id
    return False


async def _agent_can_reclaim_lease(
    db: AsyncSession,
    *,
    workspace_id: str,
    device_id: str,
    actor_agent_id: str,
    lease: AgentDeviceLease,
) -> bool:
    if lease.holder_agent_id == actor_agent_id:
        return True

    grant_stmt = await _valid_grant_query(
        workspace_id=workspace_id,
        device_id=device_id,
        subject_type="agent",
        subject_id=actor_agent_id,
    )
    result = await db.execute(grant_stmt)
    for grant in result.scalars().all():
        if not grant.can_delegate or "delegate" not in (grant.scopes or []):
            continue
        if await _is_grant_ancestor(
            db,
            workspace_id=workspace_id,
            device_id=device_id,
            ancestor_grant_id=grant.id,
            descendant_grant_id=lease.grant_id,
        ):
            return True
    return False


async def list_grants(db: AsyncSession, *, workspace_id: str, device_id: str) -> list[AgentDeviceGrant]:
    result = await db.execute(
        select(AgentDeviceGrant).where(
            AgentDeviceGrant.workspace_id == workspace_id,
            AgentDeviceGrant.device_id == device_id,
            not_deleted(AgentDeviceGrant),
        ).order_by(AgentDeviceGrant.created_at.desc())
    )
    return list(result.scalars().all())


async def expire_active_leases(db: AsyncSession, *, device_id: str) -> None:
    result = await db.execute(
        select(AgentDeviceLease).where(
            AgentDeviceLease.device_id == device_id,
            AgentDeviceLease.status == "active",
            AgentDeviceLease.expires_at <= utc_now(),
            not_deleted(AgentDeviceLease),
        )
    )
    for lease in result.scalars().all():
        lease.status = "expired"
        lease.released_at = utc_now()
    await db.flush()


async def active_lease(db: AsyncSession, *, device_id: str) -> AgentDeviceLease | None:
    await expire_active_leases(db, device_id=device_id)
    return (await db.execute(
        select(AgentDeviceLease).where(
            AgentDeviceLease.device_id == device_id,
            AgentDeviceLease.status == "active",
            not_deleted(AgentDeviceLease),
        ).limit(1)
    )).scalar_one_or_none()


async def agent_topology_reachable(
    db: AsyncSession,
    *,
    workspace_id: str,
    agent_id: str,
    device: AgentDeviceInstance,
) -> tuple[bool, str]:
    agent_hex = await corridor_router.get_agent_hex_in_workspace(agent_id, workspace_id, db)
    if agent_hex is None:
        return False, "agent_not_on_topology"
    if not await corridor_router.has_any_connections(workspace_id, db):
        return False, "topology_required"
    if not await corridor_router.can_reach(workspace_id, agent_hex[0], agent_hex[1], device.hex_q, device.hex_r, db):
        return False, "topology_unreachable"
    return True, "ok"


async def device_visibility(
    db: AsyncSession,
    *,
    workspace_id: str,
    device_id: str,
    agent_id: str | None,
) -> dict:
    device = await get_device(db, workspace_id=workspace_id, device_id=device_id)
    reasons: list[str] = []
    preset = await get_preset_info(db, workspace_id=workspace_id, preset_id=device.preset_id)
    device.status, device.status_reason = _status_for_device(device)
    if not preset["enabled"]:
        reasons.append("preset_disabled")
    if device.status != "available":
        reasons.append(device.status)

    grant: AgentDeviceGrant | None = None
    topology_reachable = False
    topology_reason = "agent_required"
    if agent_id:
        topology_reachable, topology_reason = await agent_topology_reachable(
            db, workspace_id=workspace_id, agent_id=agent_id, device=device,
        )
        if not topology_reachable:
            reasons.append(topology_reason)
        grant = await find_valid_grant(
            db,
            workspace_id=workspace_id,
            device_id=device_id,
            subject_type="agent",
            subject_id=agent_id,
            required_scope="discover",
        )
        if grant is None:
            reasons.append("grant_missing")
    else:
        reasons.append("agent_required")

    lease = await active_lease(db, device_id=device_id)
    visible = len(reasons) == 0
    return {
        "device_id": device.id,
        "visible": visible,
        "reasons": reasons,
        "status": device.status,
        "status_reason": device.status_reason,
        "preset_id": device.preset_id,
        "provider_id": device.provider_id,
        "display_name": device.display_name,
        "hex_q": device.hex_q,
        "hex_r": device.hex_r,
        "grant_id": grant.id if grant else None,
        "topology_reachable": topology_reachable,
        "reachability_source": "topology" if topology_reachable else None,
        "topology_path_ref": None,
        "topology_reason": topology_reason,
        "active_lease": lease_summary(lease) if lease else None,
    }


async def reachable_devices(db: AsyncSession, *, workspace_id: str, agent_id: str) -> list[dict]:
    devices = await list_devices(db, workspace_id=workspace_id)
    visible_devices = []
    for device in devices:
        visibility = await device_visibility(db, workspace_id=workspace_id, device_id=device.id, agent_id=agent_id)
        if visibility["visible"]:
            visible_devices.append({
                "id": device.id,
                "workspace_id": device.workspace_id,
                "preset_id": device.preset_id,
                "provider_id": device.provider_id,
                "display_name": device.display_name,
                "hex_q": device.hex_q,
                "hex_r": device.hex_r,
                "status": device.status,
                "visibility": visibility,
            })
    return visible_devices


async def require_agent_device_access(
    db: AsyncSession,
    *,
    workspace_id: str,
    device: AgentDeviceInstance,
    agent_id: str,
    required_scope: str,
) -> AgentDeviceGrant:
    preset = get_agent_device_preset(device.preset_id)
    if preset is None:
        raise NotFoundError("办公设施预设不存在", "errors.agent_device.preset_not_found")
    enablement = await get_preset_enablement(db, workspace_id=workspace_id, preset_id=device.preset_id)
    if enablement is not None and not enablement.enabled:
        raise ForbiddenError("该办公设施预设已停用", "errors.agent_device.preset_disabled")
    device.status, device.status_reason = _status_for_device(device)
    if device.status != "available":
        raise BadRequestError("办公设施当前不可用", "errors.agent_device.unavailable")
    reachable, reason = await agent_topology_reachable(db, workspace_id=workspace_id, agent_id=agent_id, device=device)
    if not reachable:
        raise ForbiddenError(f"办公设施拓扑不可达: {reason}", "errors.agent_device.topology_unreachable")
    grant = await find_valid_grant(
        db,
        workspace_id=workspace_id,
        device_id=device.id,
        subject_type="agent",
        subject_id=agent_id,
        required_scope=required_scope,
    )
    if grant is None:
        raise ForbiddenError("缺少办公设施授权", "errors.agent_device.grant_missing")
    return grant


async def acquire_lease(
    db: AsyncSession,
    *,
    workspace_id: str,
    device_id: str,
    agent_id: str,
    ttl_seconds: int | None,
    org_id: str | None,
) -> AgentDeviceLease:
    device = await get_device(db, workspace_id=workspace_id, device_id=device_id)
    grant = await require_agent_device_access(
        db, workspace_id=workspace_id, device=device, agent_id=agent_id, required_scope="lease"
    )
    await expire_active_leases(db, device_id=device_id)
    current = await active_lease(db, device_id=device_id)
    if current is not None:
        raise ConflictError("办公设施已有活跃租约", "errors.agent_device.lease_conflict")
    ttl = ttl_seconds or DEFAULT_LEASE_TTL_SECONDS
    if ttl <= 0 or ttl > 24 * 3600:
        raise BadRequestError("租约时长必须在 1 秒到 24 小时之间", "errors.agent_device.invalid_lease_ttl")
    lease = AgentDeviceLease(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        device_id=device_id,
        holder_agent_id=agent_id,
        grant_id=grant.id,
        status="active",
        expires_at=utc_now() + timedelta(seconds=ttl),
    )
    db.add(lease)
    await hooks.emit(
        "operation_audit",
        action="agent_device.lease_acquired",
        target_type="agent_device",
        target_id=device_id,
        actor_id=agent_id,
        actor_type="agent",
        org_id=org_id,
        workspace_id=workspace_id,
        details={"lease_id": lease.id, "grant_id": grant.id, "ttl_seconds": ttl},
    )
    return lease


async def renew_lease(
    db: AsyncSession,
    *,
    workspace_id: str,
    device_id: str,
    lease_id: str,
    agent_id: str,
    ttl_seconds: int | None,
    org_id: str | None,
) -> AgentDeviceLease:
    lease = await get_active_holder_lease(
        db, workspace_id=workspace_id, device_id=device_id, lease_id=lease_id, agent_id=agent_id
    )
    device = await get_device(db, workspace_id=workspace_id, device_id=device_id)
    await require_agent_device_access(
        db, workspace_id=workspace_id, device=device, agent_id=agent_id, required_scope="lease"
    )
    ttl = ttl_seconds or DEFAULT_LEASE_TTL_SECONDS
    if ttl <= 0 or ttl > 24 * 3600:
        raise BadRequestError("租约时长必须在 1 秒到 24 小时之间", "errors.agent_device.invalid_lease_ttl")
    lease.expires_at = utc_now() + timedelta(seconds=ttl)
    lease.renewed_at = utc_now()
    await hooks.emit(
        "operation_audit",
        action="agent_device.lease_renewed",
        target_type="agent_device",
        target_id=device_id,
        actor_id=agent_id,
        actor_type="agent",
        org_id=org_id,
        workspace_id=workspace_id,
        details={"lease_id": lease.id, "ttl_seconds": ttl},
    )
    return lease


async def get_active_holder_lease(
    db: AsyncSession,
    *,
    workspace_id: str,
    device_id: str,
    lease_id: str,
    agent_id: str,
) -> AgentDeviceLease:
    await expire_active_leases(db, device_id=device_id)
    lease = (await db.execute(
        select(AgentDeviceLease).where(
            AgentDeviceLease.id == lease_id,
            AgentDeviceLease.workspace_id == workspace_id,
            AgentDeviceLease.device_id == device_id,
            AgentDeviceLease.holder_agent_id == agent_id,
            AgentDeviceLease.status == "active",
            not_deleted(AgentDeviceLease),
        )
    )).scalar_one_or_none()
    if lease is None:
        raise NotFoundError("活跃租约不存在", "errors.agent_device.lease_not_found")
    return lease


async def release_lease(
    db: AsyncSession,
    *,
    workspace_id: str,
    device_id: str,
    lease_id: str,
    agent_id: str,
    org_id: str | None,
) -> AgentDeviceLease:
    lease = await get_active_holder_lease(
        db, workspace_id=workspace_id, device_id=device_id, lease_id=lease_id, agent_id=agent_id
    )
    lease.status = "released"
    lease.released_at = utc_now()
    await hooks.emit(
        "operation_audit",
        action="agent_device.lease_released",
        target_type="agent_device",
        target_id=device_id,
        actor_id=agent_id,
        actor_type="agent",
        org_id=org_id,
        workspace_id=workspace_id,
        details={"lease_id": lease.id},
    )
    return lease


async def reclaim_lease(
    db: AsyncSession,
    *,
    workspace_id: str,
    device_id: str,
    lease_id: str,
    actor_id: str,
    actor_type: str,
    org_id: str | None,
) -> AgentDeviceLease:
    lease = (await db.execute(
        select(AgentDeviceLease).where(
            AgentDeviceLease.id == lease_id,
            AgentDeviceLease.workspace_id == workspace_id,
            AgentDeviceLease.device_id == device_id,
            AgentDeviceLease.status == "active",
            not_deleted(AgentDeviceLease),
        )
    )).scalar_one_or_none()
    if lease is None:
        raise NotFoundError("活跃租约不存在", "errors.agent_device.lease_not_found")
    if actor_type == "agent" and not await _agent_can_reclaim_lease(
        db,
        workspace_id=workspace_id,
        device_id=device_id,
        actor_agent_id=actor_id,
        lease=lease,
    ):
        raise ForbiddenError("当前 Agent 无权回收该办公设施租约", "errors.agent_device.reclaim_forbidden")
    lease.status = "reclaimed"
    lease.released_at = utc_now()
    await hooks.emit(
        "operation_audit",
        action="agent_device.lease_reclaimed",
        target_type="agent_device",
        target_id=device_id,
        actor_id=actor_id,
        actor_type=actor_type,
        org_id=org_id,
        workspace_id=workspace_id,
        details={"lease_id": lease.id, "holder_agent_id": lease.holder_agent_id},
    )
    return lease


async def invoke_device(
    db: AsyncSession,
    *,
    workspace_id: str,
    device_id: str,
    agent_id: str,
    lease_id: str,
    action: str,
    payload: dict[str, Any],
    org_id: str | None,
) -> dict[str, Any]:
    device = await get_device(db, workspace_id=workspace_id, device_id=device_id)
    await require_agent_device_access(
        db, workspace_id=workspace_id, device=device, agent_id=agent_id, required_scope="invoke"
    )
    lease = await get_active_holder_lease(
        db, workspace_id=workspace_id, device_id=device_id, lease_id=lease_id, agent_id=agent_id
    )
    provider = get_agent_device_provider(device.provider_id)
    if provider is None:
        raise BadRequestError("办公设施 provider 未注册", "errors.agent_device.provider_unconfigured")

    try:
        result = await provider.invoke(
            device=device,
            actor_agent_id=agent_id,
            lease=lease,
            action=action,
            payload=payload,
        )
        await hooks.emit(
            "operation_audit",
            action="agent_device.invoke_succeeded",
            target_type="agent_device",
            target_id=device_id,
            actor_id=agent_id,
            actor_type="agent",
            org_id=org_id,
            workspace_id=workspace_id,
            details={"lease_id": lease.id, "grant_id": lease.grant_id, "provider_id": device.provider_id, "action": action},
        )
        return {"status": "ok", "result": result}
    except Exception as exc:
        await hooks.emit(
            "operation_audit",
            action="agent_device.invoke_failed",
            target_type="agent_device",
            target_id=device_id,
            actor_id=agent_id,
            actor_type="agent",
            org_id=org_id,
            workspace_id=workspace_id,
            details={"lease_id": lease.id, "grant_id": lease.grant_id, "provider_id": device.provider_id, "action": action, "error": str(exc)},
        )
        raise


def device_summary(device: AgentDeviceInstance) -> dict:
    return {
        "id": device.id,
        "workspace_id": device.workspace_id,
        "preset_id": device.preset_id,
        "provider_id": device.provider_id,
        "display_name": device.display_name,
        "hex_q": device.hex_q,
        "hex_r": device.hex_r,
        "status": device.status,
        "status_reason": device.status_reason,
        "config": device.config or {},
        "metadata": device.metadata_ or {},
        "created_by": device.created_by,
        "created_at": device.created_at,
        "updated_at": device.updated_at,
    }


def grant_summary(grant: AgentDeviceGrant) -> dict:
    return {
        "id": grant.id,
        "workspace_id": grant.workspace_id,
        "device_id": grant.device_id,
        "subject_type": grant.subject_type,
        "subject_id": grant.subject_id,
        "scopes": grant.scopes or [],
        "can_delegate": grant.can_delegate,
        "parent_grant_id": grant.parent_grant_id,
        "granted_by_type": grant.granted_by_type,
        "granted_by_id": grant.granted_by_id,
        "expires_at": grant.expires_at,
        "revoked_at": grant.revoked_at,
        "created_at": grant.created_at,
    }


def lease_summary(lease: AgentDeviceLease) -> dict:
    return {
        "id": lease.id,
        "workspace_id": lease.workspace_id,
        "device_id": lease.device_id,
        "holder_agent_id": lease.holder_agent_id,
        "grant_id": lease.grant_id,
        "status": lease.status,
        "expires_at": lease.expires_at,
        "renewed_at": lease.renewed_at,
        "released_at": lease.released_at,
        "created_at": lease.created_at,
    }


async def sync_workspace_device_genes(db: AsyncSession, *, workspace_id: str, reason: str) -> None:
    devices = await list_devices(db, workspace_id=workspace_id)
    agents = (await db.execute(
        select(WorkspaceAgent, Instance).join(
            Instance,
            and_(Instance.id == WorkspaceAgent.instance_id, not_deleted(Instance)),
        ).where(
            WorkspaceAgent.workspace_id == workspace_id,
            not_deleted(WorkspaceAgent),
        )
    )).all()

    for device in devices:
        preset = get_agent_device_preset(device.preset_id)
        if preset is None:
            continue
        for workspace_agent, instance in agents:
            visibility = await device_visibility(
                db,
                workspace_id=workspace_id,
                device_id=device.id,
                agent_id=workspace_agent.instance_id,
            )
            if visibility["visible"]:
                await ensure_gene_binding(
                    db,
                    workspace_id=workspace_id,
                    device=device,
                    instance=instance,
                    gene_slug=preset.gene_slug,
                    reason=reason,
                )
            else:
                await withdraw_gene_binding(
                    db,
                    workspace_id=workspace_id,
                    device=device,
                    instance=instance,
                    gene_slug=preset.gene_slug,
                    reason=reason,
                )


async def ensure_gene_binding(
    db: AsyncSession,
    *,
    workspace_id: str,
    device: AgentDeviceInstance,
    instance: Instance,
    gene_slug: str,
    reason: str,
) -> None:
    existing_binding = (await db.execute(
        select(AgentDeviceGeneBinding).where(
            AgentDeviceGeneBinding.workspace_id == workspace_id,
            AgentDeviceGeneBinding.device_id == device.id,
            AgentDeviceGeneBinding.instance_id == instance.id,
            AgentDeviceGeneBinding.gene_slug == gene_slug,
            not_deleted(AgentDeviceGeneBinding),
        )
    )).scalar_one_or_none()
    if existing_binding:
        return

    gene = (await db.execute(
        select(Gene).where(Gene.slug == gene_slug, not_deleted(Gene))
    )).scalar_one_or_none()
    if gene is None:
        logger.warning("Agent Device Gene 不存在，跳过同步: %s", gene_slug)
        return

    sibling_origins = (await db.execute(
        select(AgentDeviceGeneBinding.was_preexisting).where(
            AgentDeviceGeneBinding.workspace_id == workspace_id,
            AgentDeviceGeneBinding.instance_id == instance.id,
            AgentDeviceGeneBinding.gene_slug == gene_slug,
            not_deleted(AgentDeviceGeneBinding),
        )
    )).scalars().all()
    existing_instance_gene = (await db.execute(
        select(InstanceGene).where(
            InstanceGene.instance_id == instance.id,
            InstanceGene.gene_id == gene.id,
            InstanceGene.status == InstanceGeneStatus.installed,
            not_deleted(InstanceGene),
        )
    )).scalar_one_or_none()
    was_preexisting = all(sibling_origins) if sibling_origins else existing_instance_gene is not None
    if existing_instance_gene is None:
        try:
            from app.services.gene_service import install_gene_prerestart
            await install_gene_prerestart(instance.id, gene_slug)
        except Exception as exc:
            logger.warning(
                "Agent Device Gene 自动安装失败 instance=%s gene=%s err=%s",
                instance.id,
                gene_slug,
                exc,
            )
        existing_instance_gene = (await db.execute(
            select(InstanceGene).where(
                InstanceGene.instance_id == instance.id,
                InstanceGene.gene_id == gene.id,
                InstanceGene.status == InstanceGeneStatus.installed,
                not_deleted(InstanceGene),
            )
        )).scalar_one_or_none()

    db.add(AgentDeviceGeneBinding(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        device_id=device.id,
        instance_id=instance.id,
        gene_id=gene.id,
        gene_slug=gene_slug,
        instance_gene_id=existing_instance_gene.id if existing_instance_gene else None,
        was_preexisting=was_preexisting,
        sync_reason=reason,
    ))


async def withdraw_gene_binding(
    db: AsyncSession,
    *,
    workspace_id: str,
    device: AgentDeviceInstance,
    instance: Instance,
    gene_slug: str,
    reason: str,
) -> None:
    binding = (await db.execute(
        select(AgentDeviceGeneBinding).where(
            AgentDeviceGeneBinding.workspace_id == workspace_id,
            AgentDeviceGeneBinding.device_id == device.id,
            AgentDeviceGeneBinding.instance_id == instance.id,
            AgentDeviceGeneBinding.gene_slug == gene_slug,
            not_deleted(AgentDeviceGeneBinding),
        )
    )).scalar_one_or_none()
    if binding is None:
        return
    binding.sync_reason = reason
    binding.soft_delete()
    if binding.was_preexisting or not binding.gene_id:
        return
    sibling_binding = (await db.execute(
        select(AgentDeviceGeneBinding.id).where(
            AgentDeviceGeneBinding.workspace_id == workspace_id,
            AgentDeviceGeneBinding.instance_id == instance.id,
            AgentDeviceGeneBinding.gene_slug == gene_slug,
            AgentDeviceGeneBinding.id != binding.id,
            not_deleted(AgentDeviceGeneBinding),
        ).limit(1)
    )).scalar_one_or_none()
    if sibling_binding is not None:
        return
    try:
        from app.services.gene_service import uninstall_gene
        await uninstall_gene(db, instance.id, binding.gene_id)
    except Exception as exc:
        logger.warning(
            "Agent Device Gene 自动撤回失败 instance=%s gene=%s err=%s",
            instance.id,
            gene_slug,
            exc,
        )
