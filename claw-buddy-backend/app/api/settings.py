"""Settings endpoints: manage system configuration via database."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services import config_service

router = APIRouter()

# 允许通过 API 管理的配置 key 白名单
_ALLOWED_KEYS = {
    "image_registry", "registry_username", "registry_password",
    "ingress_base_domain", "tls_secret_name",
    "allowed_storage_classes",
}

# 敏感字段：读取时脱敏，写入时加密
_SENSITIVE_KEYS = {"registry_password"}


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
    filtered = {k: v for k, v in all_configs.items() if k in _ALLOWED_KEYS}
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
    if key not in _ALLOWED_KEYS:
        raise HTTPException(status_code=400, detail=f"不支持的配置项: {key}")

    row = await config_service.set_config(key, body.value, db)
    display_value = "******" if key in _SENSITIVE_KEYS and row.value else row.value
    return ApiResponse(data={"key": row.key, "value": display_value})
