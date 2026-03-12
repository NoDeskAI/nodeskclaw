"""LLM Key management endpoints: org keys, user keys, user configs."""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import hooks
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
    InstanceLlmConfigEntry,
    InstanceLlmConfigInfo,
    InstanceLlmConfigUpdate,
    LlmConfigUpdateResult,
    OpenClawConfigResponse,
    OrgLlmKeyCreate,
    OrgLlmKeyInfo,
    OrgLlmKeyUpdate,
    ProviderModelsResponse,
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
    await hooks.emit("operation_audit", action="llm_key.created", target_type="llm_key", target_id=key.id, actor_id=user.id, org_id=org_id)
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
    await hooks.emit("operation_audit", action="llm_key.updated", target_type="llm_key", target_id=key_id, actor_id=_auth[0].id, org_id=org_id)
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
    await hooks.emit("operation_audit", action="llm_key.deleted", target_type="llm_key", target_id=key_id, actor_id=_auth[0].id, org_id=org_id)
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
            api_key_masked=_mask_key(k.api_key), base_url=k.base_url,
            api_type=k.api_type, is_active=k.is_active,
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
        if not body.api_key:
            return ApiResponse(code=400, message="新建 Key 时 api_key 不能为空")
        key = UserLlmKey(
            user_id=current_user.id,
            provider=body.provider,
            api_key=body.api_key,
            base_url=body.base_url,
            api_type=body.api_type,
        )
        db.add(key)
    else:
        if body.api_key is not None:
            key.api_key = body.api_key
        key.base_url = body.base_url
        key.api_type = body.api_type
    await db.commit()
    await db.refresh(key)
    return ApiResponse(data=UserLlmKeyInfo(
        id=key.id, provider=key.provider,
        api_key_masked=_mask_key(key.api_key), base_url=key.base_url,
        api_type=key.api_type, is_active=key.is_active,
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
# Provider Model Catalog
# ══════════════════════════════════════════════════════════

@router.get("/llm/providers/{provider}/models", response_model=ApiResponse[ProviderModelsResponse])
async def list_provider_models(
    provider: str,
    api_key: str | None = Query(None),
    org_id: str | None = Query(None),
    base_url: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch available models from a provider's API.

    - If api_key is provided, use it directly (personal key scenario).
    - Otherwise, look up an active org key for the given (org_id, provider).
    - base_url: optional override for custom providers.
    """
    resolved_key = api_key
    resolved_base_url = base_url
    if not resolved_key:
        pk_result = await db.execute(
            select(UserLlmKey).where(
                UserLlmKey.user_id == current_user.id,
                UserLlmKey.provider == provider,
                not_deleted(UserLlmKey),
            ).limit(1)
        )
        personal_key = pk_result.scalar_one_or_none()
        if personal_key:
            resolved_key = personal_key.api_key
            if not resolved_base_url:
                resolved_base_url = personal_key.base_url

    if not resolved_key and org_id:
        result = await db.execute(
            select(OrgLlmKey).where(
                OrgLlmKey.org_id == org_id,
                OrgLlmKey.provider == provider,
                OrgLlmKey.is_active.is_(True),
                not_deleted(OrgLlmKey),
            ).limit(1)
        )
        org_key = result.scalar_one_or_none()
        if org_key:
            resolved_key = org_key.api_key

    if not resolved_key:
        return ApiResponse(data=ProviderModelsResponse(provider=provider, models=[]),
                           message=f"无可用的 {provider} Key，请先配置个人 Key 或 Working Plan")

    from app.services.model_catalog_service import fetch_provider_models
    try:
        models = await fetch_provider_models(provider, resolved_key, base_url=resolved_base_url)
    except ValueError as e:
        return ApiResponse(data=ProviderModelsResponse(provider=provider, models=[]),
                           message=str(e))
    return ApiResponse(data=ProviderModelsResponse(provider=provider, models=models))


# ══════════════════════════════════════════════════════════
# User LLM Configs (Portal - key source selection)
# ══════════════════════════════════════════════════════════

@router.get("/users/me/llm-configs", response_model=ApiResponse[list[UserLlmConfigInfo]])
async def get_user_llm_configs(
    org_id: str = Query(...),
    instance_id: str | None = Query(None),
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
    configs = list(result.scalars().all())

    if instance_id:
        inst_result = await db.execute(
            select(Instance).where(
                Instance.id == instance_id,
                Instance.created_by == current_user.id,
                Instance.deleted_at.is_(None),
            )
        )
        instance = inst_result.scalar_one_or_none()
        if instance and instance.llm_providers:
            allowed = set(instance.llm_providers)
            configs = [c for c in configs if c.provider in allowed]

    return ApiResponse(data=[
        UserLlmConfigInfo(
            provider=c.provider,
            key_source=c.key_source,
            selected_models=c.selected_models,
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
            existing.org_llm_key_id = None
            existing.selected_models = item.selected_models
        else:
            db.add(UserLlmConfig(
                user_id=current_user.id,
                org_id=body.org_id,
                provider=item.provider,
                key_source=item.key_source,
                selected_models=item.selected_models,
            ))

    if body.instance_id:
        inst_q = await db.execute(
            select(Instance).where(
                Instance.id == body.instance_id,
                Instance.created_by == current_user.id,
                Instance.deleted_at.is_(None),
            )
        )
        target_instance = inst_q.scalar_one_or_none()
        if target_instance:
            target_instance.llm_providers = [c.provider for c in body.configs]

        other_inst_q = await db.execute(
            select(Instance).where(
                Instance.created_by == current_user.id,
                Instance.org_id == body.org_id,
                Instance.deleted_at.is_(None),
                Instance.id != body.instance_id,
                Instance.llm_providers.isnot(None),
            )
        )
        other_instances = other_inst_q.scalars().all()
        referenced: set[str] = set()
        for inst in other_instances:
            if inst.llm_providers:
                referenced.update(inst.llm_providers)

        for provider in old_providers - new_providers:
            if provider not in referenced:
                old_map[provider].soft_delete()
    else:
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

@router.get("/instances/{instance_id}/llm-configs", response_model=ApiResponse[list[InstanceLlmConfigEntry]])
async def get_instance_llm_configs(
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

    from app.services.llm_config_service import read_instance_llm_configs
    entries = await read_instance_llm_configs(instance, db, current_user.id)
    return ApiResponse(data=[InstanceLlmConfigEntry(**e) for e in entries])


@router.put("/instances/{instance_id}/llm-configs", response_model=ApiResponse)
async def update_instance_llm_configs(
    instance_id: str,
    body: InstanceLlmConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Instance).where(Instance.id == instance_id, Instance.deleted_at.is_(None))
    )
    instance = result.scalar_one_or_none()
    if instance is None:
        raise NotFoundError("实例不存在")

    if instance.status != InstanceStatus.running:
        raise NotFoundError("实例未运行，无法写入配置")

    for cfg in body.configs:
        if cfg.key_source == "personal":
            pk_result = await db.execute(
                select(UserLlmKey).where(
                    UserLlmKey.user_id == current_user.id,
                    UserLlmKey.provider == cfg.provider,
                    not_deleted(UserLlmKey),
                )
            )
            if pk_result.scalar_one_or_none() is None:
                raise NotFoundError(f"{cfg.provider} 的个人 Key 不存在，请先配置")

    from app.services.llm_config_service import write_instance_llm_configs
    await write_instance_llm_configs(instance, db, body.configs, current_user.id)

    owner_id = instance.created_by
    existing_result = await db.execute(
        select(UserLlmConfig).where(
            UserLlmConfig.user_id == owner_id,
            UserLlmConfig.org_id == instance.org_id,
            not_deleted(UserLlmConfig),
        )
    )
    existing_map = {c.provider: c for c in existing_result.scalars().all()}

    for cfg in body.configs:
        existing = existing_map.get(cfg.provider)
        if existing:
            existing.key_source = cfg.key_source
            existing.selected_models = cfg.selected_models
        else:
            db.add(UserLlmConfig(
                user_id=owner_id,
                org_id=instance.org_id,
                provider=cfg.provider,
                key_source=cfg.key_source,
                selected_models=cfg.selected_models,
            ))

    instance.llm_providers = [c.provider for c in body.configs]
    await db.commit()

    logger.info(
        "已同步 LLM 配置到 DB: instance=%s providers=%s",
        instance.name, [c.provider for c in body.configs],
    )
    await hooks.emit("operation_audit", action="instance.llm_config_updated", target_type="instance", target_id=instance_id, actor_id=current_user.id, org_id=instance.org_id)
    return ApiResponse(message="配置已写入")


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
    await hooks.emit("operation_audit", action="instance.openclaw_restarted", target_type="instance", target_id=instance_id, actor_id=current_user.id, org_id=instance.org_id)
    return ApiResponse(data=result_data)


@router.get("/instances/{instance_id}/openclaw-providers", response_model=ApiResponse[OpenClawConfigResponse])
async def get_openclaw_providers(
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

    from app.services.llm_config_service import read_openclaw_providers
    config = await read_openclaw_providers(instance, db)
    return ApiResponse(data=config)


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

    user_keys_result = await db.execute(
        select(UserLlmKey).where(
            UserLlmKey.user_id == instance.created_by,
            not_deleted(UserLlmKey),
        )
    )
    user_keys = {k.provider: k for k in user_keys_result.scalars().all()}

    items: list[InstanceLlmConfigInfo] = []
    for c in configs:
        masked = None
        if c.key_source == "personal":
            uk = user_keys.get(c.provider)
            if uk:
                masked = _mask_key(uk.api_key)

        items.append(InstanceLlmConfigInfo(
            provider=c.provider, key_source=c.key_source,
            api_key_masked=masked,
        ))

    return ApiResponse(data=items)
