"""LLM Key management endpoints: org keys, user keys, user configs."""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_org_admin, require_org_member
from app.core.exceptions import NotFoundError
from app.core.security import get_current_user
from app.models.base import not_deleted
from app.models.instance import Instance, InstanceStatus
from app.models.llm_usage_log import LlmUsageLog
from app.models.org_llm_key import OrgLlmKey
from app.models.user import User
from app.models.user_llm_config import UserLlmConfig
from app.models.user_llm_key import UserLlmKey
from app.schemas.common import ApiResponse
from app.schemas.llm import (
    AvailableLlmKey,
    InstanceLlmConfigInfo,
    LlmConfigUpdateResult,
    OrgLlmKeyCreate,
    OrgLlmKeyInfo,
    OrgLlmKeyUpdate,
    UserLlmConfigInfo,
    UserLlmConfigUpdate,
    UserLlmKeyCreate,
    UserLlmKeyInfo,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _mask_key(key: str) -> str:
    """Mask API key keeping prefix and last 3 chars."""
    if len(key) <= 8:
        return key[:2] + "***"
    return key[:6] + "***" + key[-3:]


# ══════════════════════════════════════════════════════════
# Org LLM Keys (Admin)
# ══════════════════════════════════════════════════════════

@router.get("/orgs/{org_id}/llm-keys", response_model=ApiResponse[list[OrgLlmKeyInfo]])
async def list_org_llm_keys(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: tuple = Depends(require_org_admin),
):
    result = await db.execute(
        select(OrgLlmKey).where(
            OrgLlmKey.org_id == org_id,
            not_deleted(OrgLlmKey),
        ).order_by(OrgLlmKey.created_at)
    )
    keys = result.scalars().all()

    key_ids = [k.id for k in keys]
    usage_map: dict[str, int] = {}
    if key_ids:
        usage_result = await db.execute(
            select(
                LlmUsageLog.org_llm_key_id,
                func.coalesce(func.sum(LlmUsageLog.total_tokens), 0),
            )
            .where(LlmUsageLog.org_llm_key_id.in_(key_ids))
            .group_by(LlmUsageLog.org_llm_key_id)
        )
        for row in usage_result:
            usage_map[row[0]] = int(row[1])

    items = [
        OrgLlmKeyInfo(
            id=k.id,
            org_id=k.org_id,
            provider=k.provider,
            label=k.label,
            api_key_masked=_mask_key(k.api_key),
            base_url=k.base_url,
            org_token_limit=k.org_token_limit,
            system_token_limit=k.system_token_limit,
            is_active=k.is_active,
            usage_total_tokens=usage_map.get(k.id, 0),
            created_by=k.created_by,
        )
        for k in keys
    ]
    return ApiResponse(data=items)


@router.post("/orgs/{org_id}/llm-keys", response_model=ApiResponse[OrgLlmKeyInfo])
async def create_org_llm_key(
    org_id: str,
    body: OrgLlmKeyCreate,
    db: AsyncSession = Depends(get_db),
    _auth: tuple = Depends(require_org_admin),
):
    user, _org = _auth
    key = OrgLlmKey(
        org_id=org_id,
        provider=body.provider,
        label=body.label,
        api_key=body.api_key,
        base_url=body.base_url,
        org_token_limit=body.org_token_limit,
        system_token_limit=body.system_token_limit,
        created_by=user.id,
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)
    logger.info("创建组织 LLM Key: org=%s provider=%s label=%s", org_id, body.provider, body.label)
    return ApiResponse(data=OrgLlmKeyInfo(
        id=key.id, org_id=key.org_id, provider=key.provider, label=key.label,
        api_key_masked=_mask_key(key.api_key), base_url=key.base_url,
        org_token_limit=key.org_token_limit, system_token_limit=key.system_token_limit,
        is_active=key.is_active, created_by=key.created_by,
    ))


@router.patch("/orgs/{org_id}/llm-keys/{key_id}", response_model=ApiResponse[OrgLlmKeyInfo])
async def update_org_llm_key(
    org_id: str,
    key_id: str,
    body: OrgLlmKeyUpdate,
    db: AsyncSession = Depends(get_db),
    _auth: tuple = Depends(require_org_admin),
):
    result = await db.execute(
        select(OrgLlmKey).where(
            OrgLlmKey.id == key_id, OrgLlmKey.org_id == org_id, not_deleted(OrgLlmKey)
        )
    )
    key = result.scalar_one_or_none()
    if key is None:
        raise NotFoundError("组织 LLM Key 不存在")

    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(key, field, val)
    await db.commit()
    await db.refresh(key)
    return ApiResponse(data=OrgLlmKeyInfo(
        id=key.id, org_id=key.org_id, provider=key.provider, label=key.label,
        api_key_masked=_mask_key(key.api_key), base_url=key.base_url,
        org_token_limit=key.org_token_limit, system_token_limit=key.system_token_limit,
        is_active=key.is_active, created_by=key.created_by,
    ))


@router.delete("/orgs/{org_id}/llm-keys/{key_id}", response_model=ApiResponse)
async def delete_org_llm_key(
    org_id: str,
    key_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: tuple = Depends(require_org_admin),
):
    result = await db.execute(
        select(OrgLlmKey).where(
            OrgLlmKey.id == key_id, OrgLlmKey.org_id == org_id, not_deleted(OrgLlmKey)
        )
    )
    key = result.scalar_one_or_none()
    if key is None:
        raise NotFoundError("组织 LLM Key 不存在")

    key.soft_delete()
    await db.commit()
    logger.info("软删除组织 LLM Key: %s", key_id)
    return ApiResponse(message="已删除")


@router.get("/orgs/{org_id}/available-llm-keys", response_model=ApiResponse[list[AvailableLlmKey]])
async def list_available_llm_keys(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: tuple = Depends(require_org_member),
):
    result = await db.execute(
        select(OrgLlmKey).where(
            OrgLlmKey.org_id == org_id,
            OrgLlmKey.is_active.is_(True),
            not_deleted(OrgLlmKey),
        ).order_by(OrgLlmKey.provider, OrgLlmKey.label)
    )
    keys = result.scalars().all()
    return ApiResponse(data=[
        AvailableLlmKey(
            id=k.id, provider=k.provider, label=k.label,
            api_key_masked=_mask_key(k.api_key), is_active=k.is_active,
        )
        for k in keys
    ])


# ══════════════════════════════════════════════════════════
# User LLM Keys (Portal - personal keys)
# ══════════════════════════════════════════════════════════

@router.get("/users/me/llm-keys", response_model=ApiResponse[list[UserLlmKeyInfo]])
async def list_user_llm_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(UserLlmKey).where(
            UserLlmKey.user_id == current_user.id,
            not_deleted(UserLlmKey),
        ).order_by(UserLlmKey.provider)
    )
    keys = result.scalars().all()
    return ApiResponse(data=[
        UserLlmKeyInfo(
            id=k.id, provider=k.provider,
            api_key_masked=_mask_key(k.api_key), base_url=k.base_url, is_active=k.is_active,
        )
        for k in keys
    ])


@router.post("/users/me/llm-keys", response_model=ApiResponse[UserLlmKeyInfo])
async def upsert_user_llm_key(
    body: UserLlmKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upsert: create or update personal key by provider."""
    result = await db.execute(
        select(UserLlmKey).where(
            UserLlmKey.user_id == current_user.id,
            UserLlmKey.provider == body.provider,
            not_deleted(UserLlmKey),
        )
    )
    key = result.scalar_one_or_none()
    if key is None:
        key = UserLlmKey(
            user_id=current_user.id,
            provider=body.provider,
            api_key=body.api_key,
            base_url=body.base_url,
        )
        db.add(key)
    else:
        key.api_key = body.api_key
        key.base_url = body.base_url
    await db.commit()
    await db.refresh(key)
    return ApiResponse(data=UserLlmKeyInfo(
        id=key.id, provider=key.provider,
        api_key_masked=_mask_key(key.api_key), base_url=key.base_url, is_active=key.is_active,
    ))


@router.delete("/users/me/llm-keys/{provider}", response_model=ApiResponse)
async def delete_user_llm_key(
    provider: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(UserLlmKey).where(
            UserLlmKey.user_id == current_user.id,
            UserLlmKey.provider == provider,
            not_deleted(UserLlmKey),
        )
    )
    key = result.scalar_one_or_none()
    if key is None:
        raise NotFoundError(f"未找到 {provider} 的个人 Key")

    key.soft_delete()
    await db.commit()
    return ApiResponse(message="已删除")


# ══════════════════════════════════════════════════════════
# User LLM Configs (Portal - key source selection)
# ══════════════════════════════════════════════════════════

@router.get("/users/me/llm-configs", response_model=ApiResponse[list[UserLlmConfigInfo]])
async def get_user_llm_configs(
    org_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(UserLlmConfig).where(
            UserLlmConfig.user_id == current_user.id,
            UserLlmConfig.org_id == org_id,
            not_deleted(UserLlmConfig),
        )
    )
    configs = result.scalars().all()

    org_key_ids = [c.org_llm_key_id for c in configs if c.org_llm_key_id]
    label_map: dict[str, str] = {}
    if org_key_ids:
        keys_result = await db.execute(
            select(OrgLlmKey.id, OrgLlmKey.label).where(OrgLlmKey.id.in_(org_key_ids))
        )
        for row in keys_result:
            label_map[row[0]] = row[1]

    return ApiResponse(data=[
        UserLlmConfigInfo(
            provider=c.provider,
            key_source=c.key_source,
            org_llm_key_id=c.org_llm_key_id,
            org_llm_key_label=label_map.get(c.org_llm_key_id) if c.org_llm_key_id else None,
        )
        for c in configs
    ])


@router.put("/users/me/llm-configs", response_model=ApiResponse[LlmConfigUpdateResult])
async def update_user_llm_configs(
    body: UserLlmConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    old_result = await db.execute(
        select(UserLlmConfig).where(
            UserLlmConfig.user_id == current_user.id,
            UserLlmConfig.org_id == body.org_id,
            not_deleted(UserLlmConfig),
        )
    )
    old_configs = old_result.scalars().all()
    old_providers = {c.provider for c in old_configs}
    old_map = {c.provider: c for c in old_configs}

    new_providers = {c.provider for c in body.configs}

    for item in body.configs:
        existing = old_map.get(item.provider)
        if existing:
            existing.key_source = item.key_source
            existing.org_llm_key_id = item.org_llm_key_id
        else:
            db.add(UserLlmConfig(
                user_id=current_user.id,
                org_id=body.org_id,
                provider=item.provider,
                key_source=item.key_source,
                org_llm_key_id=item.org_llm_key_id,
            ))

    for provider in old_providers - new_providers:
        old_map[provider].soft_delete()

    await db.commit()

    providers_changed = old_providers != new_providers
    affected: list[dict] = []
    if providers_changed:
        inst_result = await db.execute(
            select(Instance).where(
                Instance.created_by == current_user.id,
                Instance.org_id == body.org_id,
                Instance.status == InstanceStatus.running,
                Instance.deleted_at.is_(None),
            )
        )
        instances = inst_result.scalars().all()
        affected = [{"id": i.id, "name": i.name} for i in instances]

    return ApiResponse(data=LlmConfigUpdateResult(
        needs_restart=providers_changed and len(affected) > 0,
        affected_instances=affected,
    ))


# ══════════════════════════════════════════════════════════
# Instance LLM Config (read-only)
# ══════════════════════════════════════════════════════════

@router.post("/instances/{instance_id}/restart-openclaw", response_model=ApiResponse[dict])
async def restart_openclaw(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Instance).where(Instance.id == instance_id, Instance.deleted_at.is_(None))
    )
    instance = result.scalar_one_or_none()
    if instance is None:
        raise NotFoundError("实例不存在")

    from app.services.llm_config_service import restart_openclaw as _restart
    result_data = await _restart(instance, db)
    return ApiResponse(data=result_data)


@router.get("/instances/{instance_id}/llm-config", response_model=ApiResponse[list[InstanceLlmConfigInfo]])
async def get_instance_llm_config(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Instance).where(Instance.id == instance_id, Instance.deleted_at.is_(None))
    )
    instance = result.scalar_one_or_none()
    if instance is None:
        raise NotFoundError("实例不存在")

    configs_result = await db.execute(
        select(UserLlmConfig).where(
            UserLlmConfig.user_id == instance.created_by,
            UserLlmConfig.org_id == instance.org_id,
            not_deleted(UserLlmConfig),
        )
    )
    configs = configs_result.scalars().all()

    items: list[InstanceLlmConfigInfo] = []
    for c in configs:
        label = None
        masked = None
        if c.key_source == "org" and c.org_llm_key_id:
            key_r = await db.execute(
                select(OrgLlmKey).where(OrgLlmKey.id == c.org_llm_key_id)
            )
            org_key = key_r.scalar_one_or_none()
            if org_key:
                label = org_key.label
                masked = _mask_key(org_key.api_key)
        elif c.key_source == "personal":
            key_r = await db.execute(
                select(UserLlmKey).where(
                    UserLlmKey.user_id == instance.created_by,
                    UserLlmKey.provider == c.provider,
                    not_deleted(UserLlmKey),
                )
            )
            user_key = key_r.scalar_one_or_none()
            if user_key:
                masked = _mask_key(user_key.api_key)

        items.append(InstanceLlmConfigInfo(
            provider=c.provider, key_source=c.key_source,
            key_label=label, api_key_masked=masked,
        ))

    return ApiResponse(data=items)
