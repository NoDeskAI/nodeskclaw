"""Agent Device API — governed Agent Devices for workspace topology."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.workspaces import broadcast_event
from app.core import hooks
from app.core.deps import get_current_org, get_current_org_or_agent, get_db
from app.core.exceptions import BadRequestError, ForbiddenError
from app.core.security import get_auth_actor
from app.schemas.agent_device import (
    AgentDeviceCreate,
    AgentDeviceGrantCreate,
    AgentDeviceInvokeRequest,
    AgentDeviceLeaseAcquire,
    AgentDeviceLeaseRenew,
    AgentDevicePresetEnablementUpdate,
    AgentDeviceUpdate,
)
from app.services import agent_device_service as device_service
from app.services import workspace_member_service as wm_service
from app.services.workspace_actor_access import require_workspace_actor_member

logger = logging.getLogger(__name__)
router = APIRouter()


def _ok(data=None, message: str = "success"):
    return {"code": 0, "message": message, "data": data}


def _org_id(org) -> str | None:
    if org is None:
        return None
    return org.id if hasattr(org, "id") else org.get("org_id")


def _actor_from_context(user) -> tuple[str, str]:
    actor = get_auth_actor()
    if actor and actor.actor_type == "agent":
        return "agent", actor.actor_id
    return "user", str(user.id)


def _current_agent_id() -> str | None:
    actor = get_auth_actor()
    if actor and actor.actor_type == "agent":
        return actor.actor_id
    return None


async def _sync_device_genes(db: AsyncSession, workspace_id: str, reason: str) -> None:
    try:
        await device_service.sync_workspace_device_genes(db, workspace_id=workspace_id, reason=reason)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.warning("Agent Device Gene 同步失败 workspace=%s reason=%s err=%s", workspace_id, reason, exc)


async def _check_workspace_for_user(
    workspace_id: str,
    org,
    db: AsyncSession,
) -> None:
    await device_service.check_workspace(workspace_id, _org_id(org), db)


@router.get("/{workspace_id}/device-presets")
async def list_device_presets(
    workspace_id: str,
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    await _check_workspace_for_user(workspace_id, org, db)
    await wm_service.check_workspace_member(workspace_id, user, db)
    return _ok(await device_service.list_preset_infos(db, workspace_id=workspace_id))


@router.get("/{workspace_id}/device-presets/{preset_id}")
async def get_device_preset(
    workspace_id: str,
    preset_id: str,
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    await _check_workspace_for_user(workspace_id, org, db)
    await wm_service.check_workspace_member(workspace_id, user, db)
    return _ok(await device_service.get_preset_info(db, workspace_id=workspace_id, preset_id=preset_id))


@router.put("/{workspace_id}/device-presets/{preset_id}")
async def update_device_preset(
    workspace_id: str,
    preset_id: str,
    body: AgentDevicePresetEnablementUpdate,
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    await _check_workspace_for_user(workspace_id, org, db)
    await wm_service.check_workspace_access(workspace_id, user, "manage_devices", db)
    data = await device_service.set_preset_enablement(
        db,
        workspace_id=workspace_id,
        preset_id=preset_id,
        enabled=body.enabled,
        config=body.config,
        actor_id=user.id,
        org_id=_org_id(org),
    )
    await db.commit()
    broadcast_event(workspace_id, "device:preset_updated", {"preset_id": preset_id, "enabled": body.enabled})
    await _sync_device_genes(db, workspace_id, "preset_updated")
    return _ok(data)


@router.get("/{workspace_id}/devices")
async def list_devices(
    workspace_id: str,
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    await _check_workspace_for_user(workspace_id, org, db)
    await wm_service.check_workspace_member(workspace_id, user, db)
    devices = await device_service.list_devices(db, workspace_id=workspace_id)
    return _ok([device_service.device_summary(device) for device in devices])


@router.post("/{workspace_id}/devices")
async def create_device(
    workspace_id: str,
    body: AgentDeviceCreate,
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    await _check_workspace_for_user(workspace_id, org, db)
    await wm_service.check_workspace_access(workspace_id, user, "manage_devices", db)
    await wm_service.check_workspace_access(workspace_id, user, "edit_topology", db)
    device = await device_service.create_device(
        db,
        workspace_id=workspace_id,
        preset_id=body.preset_id,
        display_name=body.display_name,
        hex_q=body.hex_q,
        hex_r=body.hex_r,
        config=body.config,
        metadata=body.metadata,
        actor_id=user.id,
        org_id=_org_id(org),
    )
    await db.commit()
    await db.refresh(device)
    broadcast_event(workspace_id, "device:created", device_service.device_summary(device))
    await hooks.emit(
        "topology_change",
        db=db,
        workspace_id=workspace_id,
        action="device_created",
        target_type="agent_device",
        target_id=device.id,
        actor_type="user",
        actor_id=user.id,
    )
    await _sync_device_genes(db, workspace_id, "device_created")
    return _ok(device_service.device_summary(device))


@router.patch("/{workspace_id}/devices/{device_id}")
async def update_device(
    workspace_id: str,
    device_id: str,
    body: AgentDeviceUpdate,
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    await _check_workspace_for_user(workspace_id, org, db)
    await wm_service.check_workspace_access(workspace_id, user, "manage_devices", db)
    if body.hex_q is not None or body.hex_r is not None:
        await wm_service.check_workspace_access(workspace_id, user, "edit_topology", db)
    if (body.hex_q is None) != (body.hex_r is None):
        raise BadRequestError("移动办公设施时必须同时提供 hex_q 和 hex_r", "errors.agent_device.position_required")
    device, position_changed = await device_service.update_device(
        db,
        workspace_id=workspace_id,
        device_id=device_id,
        display_name=body.display_name,
        hex_q=body.hex_q,
        hex_r=body.hex_r,
        config=body.config,
        metadata=body.metadata,
        actor_id=user.id,
        org_id=_org_id(org),
    )
    await db.commit()
    await db.refresh(device)
    broadcast_event(workspace_id, "device:updated", device_service.device_summary(device))
    if position_changed:
        await hooks.emit(
            "topology_change",
            db=db,
            workspace_id=workspace_id,
            action="device_moved",
            target_type="agent_device",
            target_id=device.id,
            actor_type="user",
            actor_id=user.id,
        )
    await _sync_device_genes(db, workspace_id, "device_updated")
    return _ok(device_service.device_summary(device))


@router.delete("/{workspace_id}/devices/{device_id}")
async def delete_device(
    workspace_id: str,
    device_id: str,
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    await _check_workspace_for_user(workspace_id, org, db)
    await wm_service.check_workspace_access(workspace_id, user, "manage_devices", db)
    await wm_service.check_workspace_access(workspace_id, user, "edit_topology", db)
    device = await device_service.delete_device(
        db,
        workspace_id=workspace_id,
        device_id=device_id,
        actor_id=user.id,
        org_id=_org_id(org),
    )
    await db.commit()
    broadcast_event(workspace_id, "device:deleted", {"device_id": device.id})
    await hooks.emit(
        "topology_change",
        db=db,
        workspace_id=workspace_id,
        action="device_deleted",
        target_type="agent_device",
        target_id=device.id,
        actor_type="user",
        actor_id=user.id,
    )
    await _sync_device_genes(db, workspace_id, "device_deleted")
    return _ok(message="deleted")


@router.get("/{workspace_id}/devices/{device_id}/grants")
async def list_device_grants(
    workspace_id: str,
    device_id: str,
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    await _check_workspace_for_user(workspace_id, org, db)
    await wm_service.check_workspace_access(workspace_id, user, "manage_devices", db)
    grants = await device_service.list_grants(db, workspace_id=workspace_id, device_id=device_id)
    return _ok([device_service.grant_summary(grant) for grant in grants])


@router.post("/{workspace_id}/devices/{device_id}/grants")
async def create_device_grant(
    workspace_id: str,
    device_id: str,
    body: AgentDeviceGrantCreate,
    org_ctx=Depends(get_current_org_or_agent),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    await device_service.check_workspace(workspace_id, _org_id(org), db)
    await require_workspace_actor_member(workspace_id, user, db)
    actor_type, actor_id = _actor_from_context(user)
    if actor_type == "user":
        await wm_service.check_workspace_access(workspace_id, user, "manage_devices", db)
    grant = await device_service.create_grant(
        db,
        workspace_id=workspace_id,
        device_id=device_id,
        subject_type=body.subject_type,
        subject_id=body.subject_id,
        scopes=body.scopes,
        can_delegate=body.can_delegate,
        parent_grant_id=body.parent_grant_id,
        expires_at=body.expires_at,
        granted_by_type=actor_type,
        granted_by_id=actor_id,
        org_id=_org_id(org),
    )
    await db.commit()
    await db.refresh(grant)
    broadcast_event(workspace_id, "device:grant_created", device_service.grant_summary(grant))
    await _sync_device_genes(db, workspace_id, "grant_created")
    return _ok(device_service.grant_summary(grant))


@router.delete("/{workspace_id}/devices/{device_id}/grants/{grant_id}")
async def revoke_device_grant(
    workspace_id: str,
    device_id: str,
    grant_id: str,
    org_ctx=Depends(get_current_org_or_agent),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    await device_service.check_workspace(workspace_id, _org_id(org), db)
    await require_workspace_actor_member(workspace_id, user, db)
    actor_type, actor_id = _actor_from_context(user)
    if actor_type == "user":
        await wm_service.check_workspace_access(workspace_id, user, "manage_devices", db)
    grant = await device_service.revoke_grant(
        db,
        workspace_id=workspace_id,
        device_id=device_id,
        grant_id=grant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        org_id=_org_id(org),
    )
    await db.commit()
    broadcast_event(workspace_id, "device:grant_revoked", {"device_id": device_id, "grant_id": grant.id})
    await _sync_device_genes(db, workspace_id, "grant_revoked")
    return _ok(message="revoked")


@router.get("/{workspace_id}/reachable-devices")
async def get_reachable_devices(
    workspace_id: str,
    instance_id: str | None = Query(default=None),
    org_ctx=Depends(get_current_org_or_agent),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    await device_service.check_workspace(workspace_id, _org_id(org), db)
    await require_workspace_actor_member(workspace_id, user, db)
    agent_id = _current_agent_id() or instance_id
    if not agent_id:
        raise BadRequestError("查询可达办公设施时必须提供 instance_id", "errors.agent_device.agent_required")
    return _ok(await device_service.reachable_devices(db, workspace_id=workspace_id, agent_id=agent_id))


@router.get("/{workspace_id}/devices/{device_id}/visibility")
async def get_device_visibility(
    workspace_id: str,
    device_id: str,
    instance_id: str | None = Query(default=None),
    org_ctx=Depends(get_current_org_or_agent),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    await device_service.check_workspace(workspace_id, _org_id(org), db)
    await require_workspace_actor_member(workspace_id, user, db)
    agent_id = _current_agent_id() or instance_id
    return _ok(await device_service.device_visibility(
        db,
        workspace_id=workspace_id,
        device_id=device_id,
        agent_id=agent_id,
    ))


@router.post("/{workspace_id}/devices/{device_id}/leases")
async def acquire_device_lease(
    workspace_id: str,
    device_id: str,
    body: AgentDeviceLeaseAcquire,
    org_ctx=Depends(get_current_org_or_agent),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    await device_service.check_workspace(workspace_id, _org_id(org), db)
    await require_workspace_actor_member(workspace_id, user, db)
    agent_id = _current_agent_id()
    if not agent_id:
        raise ForbiddenError("只有 Agent 可以获取办公设施租约", "errors.agent_device.agent_required")
    lease = await device_service.acquire_lease(
        db,
        workspace_id=workspace_id,
        device_id=device_id,
        agent_id=agent_id,
        ttl_seconds=body.ttl_seconds,
        org_id=_org_id(org),
    )
    await db.commit()
    await db.refresh(lease)
    broadcast_event(workspace_id, "device:lease_acquired", device_service.lease_summary(lease))
    return _ok(device_service.lease_summary(lease))


@router.post("/{workspace_id}/devices/{device_id}/leases/{lease_id}/renew")
async def renew_device_lease(
    workspace_id: str,
    device_id: str,
    lease_id: str,
    body: AgentDeviceLeaseRenew,
    org_ctx=Depends(get_current_org_or_agent),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    await device_service.check_workspace(workspace_id, _org_id(org), db)
    await require_workspace_actor_member(workspace_id, user, db)
    agent_id = _current_agent_id()
    if not agent_id:
        raise ForbiddenError("只有 Agent 可以续租办公设施", "errors.agent_device.agent_required")
    lease = await device_service.renew_lease(
        db,
        workspace_id=workspace_id,
        device_id=device_id,
        lease_id=lease_id,
        agent_id=agent_id,
        ttl_seconds=body.ttl_seconds,
        org_id=_org_id(org),
    )
    await db.commit()
    await db.refresh(lease)
    broadcast_event(workspace_id, "device:lease_renewed", device_service.lease_summary(lease))
    return _ok(device_service.lease_summary(lease))


async def _release_device_lease_for_agent(
    workspace_id: str,
    device_id: str,
    lease_id: str,
    org_ctx,
    db: AsyncSession,
):
    user, org = org_ctx
    await device_service.check_workspace(workspace_id, _org_id(org), db)
    await require_workspace_actor_member(workspace_id, user, db)
    agent_id = _current_agent_id()
    if not agent_id:
        raise ForbiddenError("只有 Agent 可以释放办公设施租约", "errors.agent_device.agent_required")
    lease = await device_service.release_lease(
        db,
        workspace_id=workspace_id,
        device_id=device_id,
        lease_id=lease_id,
        agent_id=agent_id,
        org_id=_org_id(org),
    )
    await db.commit()
    broadcast_event(workspace_id, "device:lease_released", device_service.lease_summary(lease))
    return _ok(device_service.lease_summary(lease))


@router.post("/{workspace_id}/devices/{device_id}/leases/{lease_id}/release")
async def release_device_lease_post(
    workspace_id: str,
    device_id: str,
    lease_id: str,
    org_ctx=Depends(get_current_org_or_agent),
    db: AsyncSession = Depends(get_db),
):
    return await _release_device_lease_for_agent(workspace_id, device_id, lease_id, org_ctx, db)


@router.delete("/{workspace_id}/devices/{device_id}/leases/{lease_id}")
async def release_device_lease(
    workspace_id: str,
    device_id: str,
    lease_id: str,
    org_ctx=Depends(get_current_org_or_agent),
    db: AsyncSession = Depends(get_db),
):
    return await _release_device_lease_for_agent(workspace_id, device_id, lease_id, org_ctx, db)


@router.post("/{workspace_id}/devices/{device_id}/leases/{lease_id}/reclaim")
async def reclaim_device_lease(
    workspace_id: str,
    device_id: str,
    lease_id: str,
    org_ctx=Depends(get_current_org_or_agent),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    await device_service.check_workspace(workspace_id, _org_id(org), db)
    await require_workspace_actor_member(workspace_id, user, db)
    actor_type, actor_id = _actor_from_context(user)
    if actor_type == "user":
        await wm_service.check_workspace_access(workspace_id, user, "manage_devices", db)
    lease = await device_service.reclaim_lease(
        db,
        workspace_id=workspace_id,
        device_id=device_id,
        lease_id=lease_id,
        actor_type=actor_type,
        actor_id=actor_id,
        org_id=_org_id(org),
    )
    await db.commit()
    broadcast_event(workspace_id, "device:lease_reclaimed", device_service.lease_summary(lease))
    return _ok(device_service.lease_summary(lease))


@router.post("/{workspace_id}/devices/{device_id}/invoke")
async def invoke_device(
    workspace_id: str,
    device_id: str,
    body: AgentDeviceInvokeRequest,
    org_ctx=Depends(get_current_org_or_agent),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    await device_service.check_workspace(workspace_id, _org_id(org), db)
    await require_workspace_actor_member(workspace_id, user, db)
    agent_id = _current_agent_id()
    if not agent_id:
        raise ForbiddenError("只有 Agent 可以调用办公设施", "errors.agent_device.agent_required")
    result = await device_service.invoke_device(
        db,
        workspace_id=workspace_id,
        device_id=device_id,
        agent_id=agent_id,
        lease_id=body.lease_id,
        action=body.action,
        payload=body.payload,
        org_id=_org_id(org),
    )
    await db.commit()
    return _ok(result)
