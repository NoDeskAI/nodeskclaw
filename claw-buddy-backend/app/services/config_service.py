"""Config service: read/write system_configs table with .env fallback."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.system_config import SystemConfig

# .env 中可作为兜底值的 key 映射
_ENV_FALLBACK: dict[str, str] = {
    "image_registry": "IMAGE_REGISTRY",
}


async def get_config(key: str, db: AsyncSession) -> str | None:
    """
    获取配置值。优先读数据库，数据库没有则回退到 .env 环境变量。

    Args:
        key: 配置键名，如 "image_registry"
        db: 数据库会话
    Returns:
        配置值，如果都没有则返回 None
    """
    row = (await db.execute(select(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
    if row is not None and row.value:
        return row.value

    # 回退到 .env
    env_attr = _ENV_FALLBACK.get(key)
    if env_attr:
        env_val = getattr(settings, env_attr, None)
        if env_val:
            return env_val

    return None


async def set_config(key: str, value: str | None, db: AsyncSession) -> SystemConfig:
    """
    写入或更新配置值。

    Args:
        key: 配置键名
        value: 配置值
        db: 数据库会话
    Returns:
        更新后的 SystemConfig 记录
    """
    row = (await db.execute(select(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
    if row:
        row.value = value
    else:
        row = SystemConfig(key=key, value=value)
        db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_all_configs(db: AsyncSession) -> dict[str, str | None]:
    """
    获取所有可管理的配置项，包含数据库中的值和 .env 兜底值。

    Returns:
        {key: value} 字典
    """
    result: dict[str, str | None] = {}

    # 先用 .env 兜底值填充
    for key, env_attr in _ENV_FALLBACK.items():
        env_val = getattr(settings, env_attr, None)
        result[key] = env_val if env_val else None

    # 数据库值覆盖
    rows = (await db.execute(select(SystemConfig))).scalars().all()
    for row in rows:
        result[row.key] = row.value

    return result
