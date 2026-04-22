"""LLM Key management endpoints: model providers, user keys, instance configs."""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import hooks
from app.core.deps import get_current_org, get_db, require_feature, require_org_admin, require_org_member
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.security import get_current_user
from app.models.base import not_deleted
from app.models.instance import Instance
from app.models.instance_provider_config import InstanceProviderConfig
from app.models.llm_usage_log import LlmUsageLog
from app.models.org_llm_key import OrgModelProvider
from app.models.user import User
from app.models.user_llm_key import UserLlmKey
from app.schemas.common import ApiResponse
from app.schemas.llm import (
    AvailableModelProvider,
    InstanceLlmConfigInfo,
    InstanceProviderConfigEntry,
    InstanceProviderConfigUpdate,
    LlmTestConnectionRequest,
    LlmTestConnectionResult,
    OpenClawConfigResponse,
    OrgModelProviderCreate,
    OrgModelProviderInfo,
    OrgModelProviderUpdate,
    ProviderModelsResponse,
    UserLlmKeyCreate,
    UserLlmKeyInfo,
)
from app.services.codex_provider import (
    CODEX_CLI_SENTINEL,
    is_codex_provider,
    mask_personal_key,
    normalize_codex_api_key,
    normalize_selected_models,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _mask_key(key: str, provider: str = "") -> str:
    return mask_personal_key(provider, key)


async def _get_instance_in_org(instance_id: str, org_id: str, db: AsyncSession) -> Instance:
    result = await db.execute(
        select(Instance).where(
            Instance.id == instance_id,
            Instance.org_id == org_id,
            Instance.deleted_at.is_(None),
        )
    )
    instance = result.scalar_one_or_none()
    if instance is None:
        raise NotFoundError("实例不存在")
    return instance


# ══════════════════════════════════════════════════════════
# Org Model Providers (Admin)
# ══════════════════════════════════════════════════════════

@router.get("/orgs/{org_id}/model-providers", response_model=ApiResponse[list[OrgModelProviderInfo]])
async def list_model_providers(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: tuple = Depends(require_org_admin),
):
    result = await db.execute(
        select(OrgModelProvider).where(
            OrgModelProvider.org_id == org_id,
            not_deleted(OrgModelProvider),
        ).order_by(OrgModelProvider.created_at)
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
        OrgModelProviderInfo(
            id=k.id,
            org_id=k.org_id,
            provider=k.provider,
            label=k.label,
            api_key_masked=_mask_key(k.api_key, k.provider),
            base_url=k.base_url,
            api_type=k.api_type,
            org_token_limit=k.org_token_limit,
            system_token_limit=k.system_token_limit,
            is_active=k.is_active,
            allowed_models=k.allowed_models,
            usage_total_tokens=usage_map.get(k.id, 0),
            created_by=k.created_by,
        )
        for k in keys
    ]
    return ApiResponse(data=items)


@router.post("/orgs/{org_id}/model-providers", response_model=ApiResponse[OrgModelProviderInfo])
async def create_model_provider(
    org_id: str,
    body: OrgModelProviderCreate,
    db: AsyncSession = Depends(get_db),
    _auth: tuple = Depends(require_org_admin),
):
    if is_codex_provider(body.provider):
        raise BadRequestError("Codex 仅支持个人配置，不支持 Working Plan")

    dup_result = await db.execute(
        select(OrgModelProvider).where(
            OrgModelProvider.org_id == org_id,
            OrgModelProvider.provider == body.provider,
            not_deleted(OrgModelProvider),
        )
    )
    if dup_result.scalar_one_or_none():
        raise BadRequestError(
            f"{body.provider} 已配置，请编辑现有配置",
            "errors.model_provider.already_exists",
        )

    user, _org = _auth
    key = OrgModelProvider(
        org_id=org_id,
        provider=body.provider,
        label=body.label,
        api_key=body.api_key,
        base_url=body.base_url,
        api_type=body.api_type,
        org_token_limit=body.org_token_limit,
        system_token_limit=body.system_token_limit,
        created_by=user.id,
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)
    logger.info("创建模型供应商: org=%s provider=%s", org_id, body.provider)
    await hooks.emit("operation_audit", action="model_provider.created", target_type="model_provider", target_id=key.id, actor_id=user.id, org_id=org_id)
    return ApiResponse(data=OrgModelProviderInfo(
        id=key.id, org_id=key.org_id, provider=key.provider, label=key.label,
        api_key_masked=_mask_key(key.api_key, key.provider), base_url=key.base_url,
        api_type=key.api_type, org_token_limit=key.org_token_limit,
        system_token_limit=key.system_token_limit,
        is_active=key.is_active, created_by=key.created_by,
    ))


@router.patch("/orgs/{org_id}/model-providers/{key_id}", response_model=ApiResponse[OrgModelProviderInfo])
async def update_model_provider(
    org_id: str,
    key_id: str,
    body: OrgModelProviderUpdate,
    db: AsyncSession = Depends(get_db),
    _auth: tuple = Depends(require_org_admin),
):
    result = await db.execute(
        select(OrgModelProvider).where(
            OrgModelProvider.id == key_id, OrgModelProvider.org_id == org_id, not_deleted(OrgModelProvider)
        )
    )
    key = result.scalar_one_or_none()
    if key is None:
        raise NotFoundError("模型供应商不存在")
    if is_codex_provider(key.provider):
        raise BadRequestError("Codex 仅支持个人配置，不支持 Working Plan")

    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(key, field, val)
    await db.commit()
    await db.refresh(key)
    await hooks.emit("operation_audit", action="model_provider.updated", target_type="model_provider", target_id=key_id, actor_id=_auth[0].id, org_id=org_id)
    return ApiResponse(data=OrgModelProviderInfo(
        id=key.id, org_id=key.org_id, provider=key.provider, label=key.label,
        api_key_masked=_mask_key(key.api_key, key.provider), base_url=key.base_url,
        api_type=key.api_type, org_token_limit=key.org_token_limit,
        system_token_limit=key.system_token_limit,
        is_active=key.is_active, allowed_models=key.allowed_models, created_by=key.created_by,
    ))


@router.delete("/orgs/{org_id}/model-providers/{key_id}", response_model=ApiResponse)
async def delete_model_provider(
    org_id: str,
    key_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: tuple = Depends(require_org_admin),
):
    result = await db.execute(
        select(OrgModelProvider).where(
            OrgModelProvider.id == key_id, OrgModelProvider.org_id == org_id, not_deleted(OrgModelProvider)
        )
    )
    key = result.scalar_one_or_none()
    if key is None:
        raise NotFoundError("模型供应商不存在")

    key.soft_delete()
    await db.commit()
    logger.info("软删除模型供应商: %s", key_id)
    await hooks.emit("operation_audit", action="model_provider.deleted", target_type="model_provider", target_id=key_id, actor_id=_auth[0].id, org_id=org_id)
    return ApiResponse(message="已删除")


@router.get("/orgs/{org_id}/model-providers/available", response_model=ApiResponse[list[AvailableModelProvider]])
async def list_available_model_providers(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: tuple = Depends(require_org_member),
):
    result = await db.execute(
        select(OrgModelProvider).where(
            OrgModelProvider.org_id == org_id,
            OrgModelProvider.is_active.is_(True),
            not_deleted(OrgModelProvider),
        ).order_by(OrgModelProvider.provider)
    )
    keys = result.scalars().all()
    return ApiResponse(data=[
        AvailableModelProvider(
            id=k.id, provider=k.provider, label=k.label,
            api_key_masked=_mask_key(k.api_key, k.provider), is_active=k.is_active,
            allowed_models=k.allowed_models,
            api_type=k.api_type, base_url=k.base_url,
            skip_ssl_verify=k.skip_ssl_verify,
        )
        for k in keys
    ])


# backward-compat aliases for old routes
@router.get("/orgs/{org_id}/llm-keys", response_model=ApiResponse[list[OrgModelProviderInfo]], include_in_schema=False)
async def list_org_llm_keys(org_id: str, db: AsyncSession = Depends(get_db), _auth: tuple = Depends(require_org_admin)):
    return await list_model_providers(org_id, db, _auth)


@router.post("/orgs/{org_id}/llm-keys", response_model=ApiResponse[OrgModelProviderInfo], include_in_schema=False)
async def create_org_llm_key(org_id: str, body: OrgModelProviderCreate, db: AsyncSession = Depends(get_db), _auth: tuple = Depends(require_org_admin)):
    return await create_model_provider(org_id, body, db, _auth)


@router.patch("/orgs/{org_id}/llm-keys/{key_id}", response_model=ApiResponse[OrgModelProviderInfo], include_in_schema=False)
async def update_org_llm_key(org_id: str, key_id: str, body: OrgModelProviderUpdate, db: AsyncSession = Depends(get_db), _auth: tuple = Depends(require_org_admin)):
    return await update_model_provider(org_id, key_id, body, db, _auth)


@router.delete("/orgs/{org_id}/llm-keys/{key_id}", response_model=ApiResponse, include_in_schema=False)
async def delete_org_llm_key(org_id: str, key_id: str, db: AsyncSession = Depends(get_db), _auth: tuple = Depends(require_org_admin)):
    return await delete_model_provider(org_id, key_id, db, _auth)


@router.get("/orgs/{org_id}/available-llm-keys", response_model=ApiResponse[list[AvailableModelProvider]], include_in_schema=False)
async def list_available_llm_keys(org_id: str, db: AsyncSession = Depends(get_db), _auth: tuple = Depends(require_org_member)):
    return await list_available_model_providers(org_id, db, _auth)


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
            api_key_masked=_mask_key(k.api_key, k.provider), base_url=k.base_url,
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
    normalized_api_key = normalize_codex_api_key(body.api_key) if is_codex_provider(body.provider) else body.api_key
    if key is None:
        if not normalized_api_key:
            raise BadRequestError("新建 Key 时 api_key 不能为空", "errors.llm.api_key_required")
        key = UserLlmKey(
            user_id=current_user.id,
            provider=body.provider,
            api_key=normalized_api_key,
            base_url=body.base_url,
            api_type=body.api_type,
        )
        db.add(key)
    else:
        if is_codex_provider(body.provider):
            key.api_key = normalize_codex_api_key(body.api_key)
        elif body.api_key is not None:
            key.api_key = body.api_key
        key.base_url = body.base_url
        key.api_type = body.api_type
    await db.commit()
    await db.refresh(key)
    return ApiResponse(data=UserLlmKeyInfo(
        id=key.id, provider=key.provider,
        api_key_masked=_mask_key(key.api_key, key.provider), base_url=key.base_url,
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
    api_type: str | None = Query(None),
    skip_ssl_verify: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.model_catalog_service import fetch_provider_models

    if is_codex_provider(provider):
        models = await fetch_provider_models(provider, CODEX_CLI_SENTINEL)
        return ApiResponse(data=ProviderModelsResponse(provider=provider, models=models))

    resolved_key = api_key
    resolved_base_url = base_url
    resolved_api_type = api_type
    resolved_skip_ssl = skip_ssl_verify
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
            if not resolved_api_type:
                resolved_api_type = personal_key.api_type
            if resolved_skip_ssl is None:
                resolved_skip_ssl = personal_key.skip_ssl_verify

    if not resolved_key and org_id:
        result = await db.execute(
            select(OrgModelProvider).where(
                OrgModelProvider.org_id == org_id,
                OrgModelProvider.provider == provider,
                OrgModelProvider.is_active.is_(True),
                not_deleted(OrgModelProvider),
            ).limit(1)
        )
        org_key = result.scalar_one_or_none()
        if org_key:
            resolved_key = org_key.api_key
            if not resolved_base_url:
                resolved_base_url = org_key.base_url
            if not resolved_api_type:
                resolved_api_type = org_key.api_type
            if resolved_skip_ssl is None:
                resolved_skip_ssl = org_key.skip_ssl_verify

    if not resolved_key:
        raise BadRequestError(
            f"无可用的 {provider} Key，请先配置个人 Key 或 Working Plan",
            "errors.llm.provider_key_missing",
        )

    try:
        models = await fetch_provider_models(
            provider, resolved_key, base_url=resolved_base_url, api_type=resolved_api_type,
            skip_ssl_verify=bool(resolved_skip_ssl),
        )
    except ValueError as e:
        raise BadRequestError(str(e), "errors.llm.model_fetch_failed")
    return ApiResponse(data=ProviderModelsResponse(provider=provider, models=models))


async def _test_via_proxy(
    proxy_url: str,
    provider: str,
    api_key: str,
    model: str | None,
    *,
    base_url: str | None = None,
    api_type: str | None = None,
    skip_ssl_verify: bool = False,
):
    """Route test connection through the LLM Proxy's /internal/test-connection endpoint."""
    import httpx
    from app.services.model_catalog_service import ChatTestResult

    payload = {
        "provider": provider,
        "api_key": api_key,
        "model": model or "",
        "base_url": base_url,
        "api_type": api_type,
        "skip_ssl_verify": skip_ssl_verify,
    }
    try:
        async with httpx.AsyncClient(verify=False, timeout=httpx.Timeout(45, connect=10)) as client:
            resp = await client.post(f"{proxy_url}/internal/test-connection", json=payload)
            data = resp.json()
        return ChatTestResult(
            ok=data.get("ok", False),
            model=data.get("model", model or ""),
            message=data.get("message", ""),
            latency_ms=data.get("latency_ms", 0),
            error_detail=data.get("error_detail"),
        )
    except Exception as e:
        logger.warning("LLM Proxy test-connection 调用失败，fallback 到直连: %s", e)
        from app.services.model_catalog_service import test_provider_chat_completion
        return await test_provider_chat_completion(
            provider, api_key, model,
            base_url=base_url, api_type=api_type,
            skip_ssl_verify=skip_ssl_verify,
        )


@router.post("/llm/test-connection", response_model=ApiResponse[LlmTestConnectionResult])
async def test_llm_connection(
    body: LlmTestConnectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.core.config import settings
    from app.services.model_catalog_service import test_provider_chat_completion

    resolved_key = body.api_key
    resolved_base_url = body.base_url
    resolved_api_type = body.api_type

    if not resolved_key and body.org_id:
        result = await db.execute(
            select(OrgModelProvider).where(
                OrgModelProvider.org_id == body.org_id,
                OrgModelProvider.provider == body.provider,
                OrgModelProvider.is_active.is_(True),
                not_deleted(OrgModelProvider),
            ).limit(1)
        )
        org_key = result.scalar_one_or_none()
        if org_key:
            resolved_key = org_key.api_key
            if not resolved_base_url:
                resolved_base_url = org_key.base_url
            if not resolved_api_type:
                resolved_api_type = org_key.api_type

    if not resolved_key:
        pk_result = await db.execute(
            select(UserLlmKey).where(
                UserLlmKey.user_id == current_user.id,
                UserLlmKey.provider == body.provider,
                not_deleted(UserLlmKey),
            ).limit(1)
        )
        personal_key = pk_result.scalar_one_or_none()
        if personal_key:
            resolved_key = personal_key.api_key
            if not resolved_base_url:
                resolved_base_url = personal_key.base_url
            if not resolved_api_type:
                resolved_api_type = personal_key.api_type

    if not resolved_key:
        return ApiResponse(data=LlmTestConnectionResult(
            ok=False, message="无可用 Key，请先填写 API Key",
        ))

    proxy_url = (settings.LLM_PROXY_INTERNAL_URL or settings.LLM_PROXY_URL or "").rstrip("/")
    if proxy_url:
        r = await _test_via_proxy(
            proxy_url, body.provider, resolved_key, body.model,
            base_url=resolved_base_url, api_type=resolved_api_type,
            skip_ssl_verify=body.skip_ssl_verify,
        )
    else:
        r = await test_provider_chat_completion(
            body.provider, resolved_key, body.model,
            base_url=resolved_base_url, api_type=resolved_api_type,
            skip_ssl_verify=body.skip_ssl_verify,
        )
    return ApiResponse(data=LlmTestConnectionResult(
        ok=r.ok,
        message=r.message,
        tested_model=r.model if r.model else None,
        latency_ms=r.latency_ms or None,
        error_detail=r.error_detail,
    ))


# ══════════════════════════════════════════════════════════
# Instance Provider Configs (per-instance)
# ══════════════════════════════════════════════════════════

@router.get("/instances/{instance_id}/provider-configs", response_model=ApiResponse[list[InstanceProviderConfigEntry]])
async def get_instance_provider_configs(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_ctx=Depends(get_current_org),
):
    _current_user, org = org_ctx
    instance = await _get_instance_in_org(instance_id, org.id, db)

    from app.services.llm_config_service import read_instance_llm_configs
    entries = await read_instance_llm_configs(instance, db, current_user.id)
    return ApiResponse(data=[InstanceProviderConfigEntry(**e) for e in entries])


@router.put("/instances/{instance_id}/provider-configs", response_model=ApiResponse)
async def update_instance_provider_configs(
    instance_id: str,
    body: InstanceProviderConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_ctx=Depends(get_current_org),
):
    _current_user, org = org_ctx
    instance = await _get_instance_in_org(instance_id, org.id, db)

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
    applied = await write_instance_llm_configs(instance, db, body.configs, current_user.id)

    instance.llm_providers = [c.provider for c in body.configs]
    await db.commit()

    logger.info(
        "已更新实例 provider 配置: instance=%s providers=%s applied=%s",
        instance.name, [c.provider for c in body.configs], applied,
    )
    await hooks.emit("operation_audit", action="instance.llm_config_updated", target_type="instance", target_id=instance_id, actor_id=current_user.id, org_id=instance.org_id)

    if applied:
        return ApiResponse(message="配置已写入")
    return ApiResponse(data={"pending": True}, message="配置已保存，重启后自动应用")


# backward-compat aliases for old instance llm-configs routes
@router.get("/instances/{instance_id}/llm-configs", response_model=ApiResponse[list[InstanceProviderConfigEntry]], include_in_schema=False)
async def get_instance_llm_configs(instance_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user), org_ctx=Depends(get_current_org)):
    return await get_instance_provider_configs(instance_id, db, current_user, org_ctx)


@router.put("/instances/{instance_id}/llm-configs", response_model=ApiResponse, include_in_schema=False)
async def update_instance_llm_configs(instance_id: str, body: InstanceProviderConfigUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user), org_ctx=Depends(get_current_org)):
    return await update_instance_provider_configs(instance_id, body, db, current_user, org_ctx)


@router.post("/instances/{instance_id}/restart-runtime", response_model=ApiResponse[dict])
async def restart_runtime(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_ctx=Depends(get_current_org),
):
    _current_user, org = org_ctx
    instance = await _get_instance_in_org(instance_id, org.id, db)

    from app.services.llm_config_service import restart_runtime as _restart
    result_data = await _restart(instance, db)
    await hooks.emit("operation_audit", action="instance.runtime_restarted", target_type="instance", target_id=instance_id, actor_id=current_user.id, org_id=instance.org_id)
    return ApiResponse(data=result_data)


@router.get("/instances/{instance_id}/openclaw-providers", response_model=ApiResponse[OpenClawConfigResponse])
async def get_openclaw_providers(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    _current_user, org = org_ctx
    instance = await _get_instance_in_org(instance_id, org.id, db)

    if instance.runtime != "openclaw":
        return ApiResponse(data=OpenClawConfigResponse(data_source="not_applicable", providers=[]))

    from app.services.llm_config_service import read_openclaw_providers
    config = await read_openclaw_providers(instance, db)
    return ApiResponse(data=config)


@router.get("/instances/{instance_id}/llm-config", response_model=ApiResponse[list[InstanceLlmConfigInfo]])
async def get_instance_llm_config(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    _current_user, org = org_ctx
    instance = await _get_instance_in_org(instance_id, org.id, db)

    ipc_result = await db.execute(
        select(InstanceProviderConfig).where(
            InstanceProviderConfig.instance_id == instance.id,
            not_deleted(InstanceProviderConfig),
        )
    )
    ipc_list = ipc_result.scalars().all()

    user_keys_result = await db.execute(
        select(UserLlmKey).where(
            UserLlmKey.user_id == instance.created_by,
            not_deleted(UserLlmKey),
        )
    )
    user_keys = {k.provider: k for k in user_keys_result.scalars().all()}

    items: list[InstanceLlmConfigInfo] = []
    for c in ipc_list:
        masked = None
        if c.key_source == "personal":
            uk = user_keys.get(c.provider)
            if uk:
                masked = _mask_key(uk.api_key, uk.provider)

        items.append(InstanceLlmConfigInfo(
            provider=c.provider, key_source=c.key_source,
            api_key_masked=masked,
        ))

    return ApiResponse(data=items)


# ── EE-only Token Analytics ──────────────────────────

@router.get(
    "/orgs/{org_id}/token-analytics",
    dependencies=[Depends(require_feature("llm_analytics")), Depends(require_org_admin)],
)
async def get_org_token_analytics(
    org_id: str,
    db: AsyncSession = Depends(get_db),
):
    """EE-only: Organization-level LLM token usage analytics by provider, model, and instance."""
    from app.models.llm_usage_log import LlmUsageLog

    rows = await db.execute(
        select(
            LlmUsageLog.provider,
            LlmUsageLog.model,
            LlmUsageLog.instance_id,
            func.sum(LlmUsageLog.prompt_tokens),
            func.sum(LlmUsageLog.completion_tokens),
            func.sum(LlmUsageLog.total_tokens),
            func.count(),
        ).where(
            LlmUsageLog.org_id == org_id,
        ).group_by(
            LlmUsageLog.provider, LlmUsageLog.model, LlmUsageLog.instance_id,
        )
    )

    by_provider: list[dict] = []
    grand_prompt = 0
    grand_completion = 0
    grand_total = 0
    for row in rows.all():
        p_tok = int(row[3] or 0)
        c_tok = int(row[4] or 0)
        t_tok = int(row[5] or 0)
        grand_prompt += p_tok
        grand_completion += c_tok
        grand_total += t_tok
        by_provider.append({
            "provider": row[0],
            "model": row[1],
            "instance_id": row[2],
            "prompt_tokens": p_tok,
            "completion_tokens": c_tok,
            "total_tokens": t_tok,
            "request_count": int(row[6] or 0),
        })

    return ApiResponse(data={
        "total_prompt_tokens": grand_prompt,
        "total_completion_tokens": grand_completion,
        "total_tokens": grand_total,
        "by_provider": by_provider,
    })
