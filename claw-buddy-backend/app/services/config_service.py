"""Config service: read/write system_configs table. All config lives in DB."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_config import SystemConfig


async def get_config(key: str, db: AsyncSession) -> str | None:
    """
    从数据库读取配置值。

    Args:
        key: 配置键名，如 "image_registry"
        db: 数据库会话
    Returns:
        配置值，如果没有则返回 None
    """
    row = (await db.execute(select(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
    if row is not None and row.value:
        return row.value
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
    获取所有数据库中的配置项。

    Returns:
        {key: value} 字典
    """
    result: dict[str, str | None] = {}
    rows = (await db.execute(select(SystemConfig))).scalars().all()
    for row in rows:
        result[row.key] = row.value
    return result
