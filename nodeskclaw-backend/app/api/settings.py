"""Settings endpoints: manage system configuration via database."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import hooks
from app.core.deps import get_db
from app.core.exceptions import BadRequestError
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services import config_service
from app.services.upload_policy_service import UPLOAD_CONFIG_KEYS, validate_upload_config_value
from app.services.runtime.registries.runtime_registry import RUNTIME_REGISTRY

logger = logging.getLogger(__name__)

router = APIRouter()

_ALLOWED_KEYS = {
    "registry_mode", "image_registry", "registry_username", "registry_password",
    "hosted_registry_url", "hosted_registry_username", "hosted_registry_password",
    "ingress_base_domain", "ingress_subdomain_suffix", "tls_secret_name",
    "ingress_tls_enabled",
    "allowed_storage_classes",
    "smtp_host", "smtp_port", "smtp_username", "smtp_password",
    "smtp_from_email", "smtp_from_name", "smtp_use_tls",
    "verification_email_subject", "verification_email_template",
    "egress_deny_cidrs", "egress_allow_ports",
    "network_policy_ingress_enabled", "network_policy_egress_enabled",
    "ingress_allow_cidrs",
    "instance_spec_presets",
    *UPLOAD_CONFIG_KEYS,
}

_SENSITIVE_KEYS = {"registry_password", "hosted_registry_password", "smtp_password"}


def _is_allowed_key(key: str) -> bool:
    if key in _ALLOWED_KEYS:
        return True
    if key.startswith("image_registry_"):
        runtime_id = key[len("image_registry_"):]
        return RUNTIME_REGISTRY.get(runtime_id) is not None
    return False


class ConfigUpdateBody(PydanticBaseModel):
    value: str | None = None


@router.get("", response_model=ApiResponse[dict])
async def get_settings(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """获取所有可管理的系统配置。"""
    all_configs = await config_service.get_all_configs(db)
    # 只返回白名单内的 key
    filtered = {k: v for k, v in all_configs.items() if _is_allowed_key(k)}
    # 敏感字段脱敏：有值显示 "******"，无值显示 None
    for k in _SENSITIVE_KEYS:
        if k in filtered and filtered[k]:
            filtered[k] = "******"
    return ApiResponse(data=filtered)


@router.put("/{key}", response_model=ApiResponse[dict])
async def update_setting(
    key: str,
    body: ConfigUpdateBody,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """更新指定系统配置项。"""
    if not _is_allowed_key(key):
        raise BadRequestError(f"不支持的配置项: {key}", "errors.settings.unsupported_key")

    if key == "registry_mode":
        mode = (body.value or "").strip().lower()
        if mode not in {"custom", "hosted"}:
            raise BadRequestError(
                "镜像仓库模式仅支持 custom 或 hosted",
                "errors.settings.invalid_registry_mode",
            )
        body.value = mode
        if mode == "hosted":
            hosted_url = await config_service.get_config("hosted_registry_url", db)
            hosted_username = await config_service.get_config("hosted_registry_username", db)
            hosted_password = await config_service.get_config("hosted_registry_password", db)
            if not hosted_url or not hosted_username or not hosted_password:
                raise BadRequestError(
                    "Hosted Registry 配置不完整",
                    "errors.settings.hosted_registry_incomplete",
                )

    if key == "hosted_registry_url" or key == "image_registry" or key.startswith("image_registry_"):
        from app.services.registry_service import normalize_registry_repository

        normalized = normalize_registry_repository(body.value)
        if normalized and any(char in normalized for char in ("?", "#", "@", " ")):
            raise BadRequestError(
                "镜像仓库地址格式无效",
                "errors.settings.invalid_registry_url",
            )
        if normalized and "/" in normalized:
            final_segment = normalized.rsplit("/", 1)[-1]
            if ":" in final_segment:
                raise BadRequestError(
                    "镜像仓库地址不能包含 Tag",
                    "errors.settings.invalid_registry_url",
                )
        body.value = normalized

    if key == "instance_spec_presets" and body.value is not None:
        import json as _json
        from app.schemas.spec_preset import SpecPresetInput
        try:
            items = _json.loads(body.value)
            if not isinstance(items, list):
                raise ValueError("must be a JSON array")
            for item in items:
                SpecPresetInput.model_validate(item)
        except Exception as exc:
            raise BadRequestError(
                f"规格预设格式无效: {exc}",
                "errors.settings.invalid_spec_presets",
            )

    await validate_upload_config_value(key, body.value, db)

    row = await config_service.set_config(key, body.value, db)
    display_value = "******" if key in _SENSITIVE_KEYS and row.value else row.value
    await hooks.emit("operation_audit", action="system.setting_updated", target_type="system_config", target_id=key, actor_id=_current_user.id, org_id=_current_user.current_org_id, details={})
    return ApiResponse(data={"key": row.key, "value": display_value})


class SmtpTestBody(PydanticBaseModel):
    recipient_email: str


@router.post("/smtp/test", response_model=ApiResponse)
async def test_smtp(
    body: SmtpTestBody,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """使用当前全局 SMTP 配置发送测试邮件。"""
    from app.services.email.transport import SmtpConfig
    from app.services.email_service import send_test_email

    host = await config_service.get_config("smtp_host", db)
    if not host:
        raise HTTPException(status_code=400, detail={
            "error_code": 40053,
            "message_key": "errors.smtp.not_configured",
            "message": "全局 SMTP 未配置",
        })

    port_str = await config_service.get_config("smtp_port", db) or "587"
    username = await config_service.get_config("smtp_username", db) or ""
    password = await config_service.get_config("smtp_password", db) or ""
    from_email = await config_service.get_config("smtp_from_email", db) or username
    from_name = await config_service.get_config("smtp_from_name", db)
    use_tls_str = await config_service.get_config("smtp_use_tls", db)
    use_tls = use_tls_str != "false" if use_tls_str else True

    smtp_config = SmtpConfig(
        smtp_host=host,
        smtp_port=int(port_str),
        smtp_username=username,
        smtp_password=password,
        from_email=from_email,
        from_name=from_name,
        use_tls=use_tls,
    )

    try:
        await send_test_email(body.recipient_email, smtp_config)
    except Exception as exc:
        logger.warning("SMTP test failed: %s", exc)
        raise HTTPException(status_code=400, detail={
            "error_code": 40051,
            "message_key": "errors.smtp.test_failed",
            "message": f"SMTP 测试失败: {exc}",
        })

    return ApiResponse(message="测试邮件已发送")
