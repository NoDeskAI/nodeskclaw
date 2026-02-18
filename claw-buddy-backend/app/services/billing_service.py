"""Billing & quota management service."""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, NotFoundError
from app.models.base import not_deleted
from app.models.instance import Instance
from app.models.organization import Organization
from app.models.plan import Plan
from app.schemas.billing import OrgUsage, PlanInfo

logger = logging.getLogger(__name__)


async def list_plans(db: AsyncSession) -> list[PlanInfo]:
    """列出所有可用套餐。"""
    result = await db.execute(
        select(Plan).where(Plan.is_active.is_(True), not_deleted(Plan)).order_by(Plan.price_monthly)
    )
    return [PlanInfo.model_validate(p) for p in result.scalars().all()]


async def get_plan_by_name(name: str, db: AsyncSession) -> Plan:
    """按名称获取套餐。"""
    result = await db.execute(
        select(Plan).where(Plan.name == name, Plan.is_active.is_(True), not_deleted(Plan))
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise NotFoundError(f"套餐 '{name}' 不存在")
    return plan


async def get_org_usage(org: Organization, db: AsyncSession) -> OrgUsage:
    """获取组织当前资源使用量。"""
    count_result = await db.execute(
        select(func.count()).where(
            Instance.org_id == org.id,
            not_deleted(Instance),
        )
    )
    instance_count = count_result.scalar_one()

    instances_result = await db.execute(
        select(Instance.cpu_limit, Instance.mem_limit, Instance.storage_size).where(
            Instance.org_id == org.id,
            not_deleted(Instance),
        )
    )
    total_cpu_m = 0
    total_mem_mi = 0
    total_storage_gi = 0.0
    for cpu_limit, mem_limit, storage_size in instances_result.all():
        total_cpu_m += _parse_cpu_millis(cpu_limit)
        total_mem_mi += _parse_mem_mi(mem_limit)
        total_storage_gi += _parse_storage_gi(storage_size or "0")

    storage_limit = getattr(org, "max_storage_total", "500Gi")

    return OrgUsage(
        instance_count=instance_count,
        instance_limit=org.max_instances,
        cpu_used=f"{total_cpu_m}m",
        cpu_limit=org.max_cpu_total,
        mem_used=f"{total_mem_mi}Mi",
        mem_limit=org.max_mem_total,
        storage_used=f"{int(total_storage_gi)}Gi",
        storage_limit=storage_limit,
    )


async def check_deploy_quota(
    org: Organization,
    db: AsyncSession,
    cpu_request: str = "0",
    mem_request: str = "0",
    storage_size: str = "0",
) -> None:
    """部署前检查配额（实例数 + CPU + 内存 + 存储），不满足则抛异常。"""
    usage = await get_org_usage(org, db)

    if usage.instance_count >= usage.instance_limit:
        raise BadRequestError(
            f"实例数量已达上限 ({usage.instance_count}/{usage.instance_limit})，"
            "请升级套餐或联系管理员"
        )

    req_cpu = _parse_cpu_millis(cpu_request)
    used_cpu = _parse_cpu_millis(usage.cpu_used)
    limit_cpu = _parse_cpu_millis(usage.cpu_limit)
    if limit_cpu > 0 and used_cpu + req_cpu > limit_cpu:
        raise BadRequestError(
            f"CPU 配额不足：已用 {usage.cpu_used}，本次需要 {cpu_request}，"
            f"上限 {usage.cpu_limit}"
        )

    req_mem = _parse_mem_mi(mem_request)
    used_mem = _parse_mem_mi(usage.mem_used)
    limit_mem = _parse_mem_mi(usage.mem_limit)
    if limit_mem > 0 and used_mem + req_mem > limit_mem:
        raise BadRequestError(
            f"内存配额不足：已用 {usage.mem_used}，本次需要 {mem_request}，"
            f"上限 {usage.mem_limit}"
        )

    req_storage = _parse_storage_gi(storage_size)
    used_storage = _parse_storage_gi(usage.storage_used)
    limit_storage = _parse_storage_gi(usage.storage_limit)
    if limit_storage > 0 and used_storage + req_storage > limit_storage:
        raise BadRequestError(
            f"存储配额不足：已用 {usage.storage_used}，本次需要 {storage_size}，"
            f"上限 {usage.storage_limit}"
        )


async def upgrade_org_plan(org: Organization, plan_name: str, db: AsyncSession) -> Organization:
    """升级组织套餐，同步更新配额。"""
    plan = await get_plan_by_name(plan_name, db)

    org.plan = plan.name
    org.max_instances = plan.max_instances

    if plan.name == "enterprise":
        org.max_cpu_total = "200"
        org.max_mem_total = "400Gi"
        org.max_storage_total = "2000Gi"
    elif plan.name == "pro":
        org.max_cpu_total = "80"
        org.max_mem_total = "160Gi"
        org.max_storage_total = "500Gi"
    else:
        org.max_cpu_total = "4"
        org.max_mem_total = "8Gi"
        org.max_storage_total = "100Gi"

    await db.commit()
    await db.refresh(org)
    logger.info("组织 %s 升级到套餐 %s", org.slug, plan.name)
    return org


def _parse_cpu_millis(val: str) -> int:
    """将 CPU 值解析为毫核。"""
    val = val.strip()
    if val.endswith("m"):
        return int(val[:-1])
    return int(float(val) * 1000)


def _parse_mem_mi(val: str) -> int:
    """将内存值解析为 MiB。"""
    val = val.strip()
    if val.endswith("Gi"):
        return int(float(val[:-2]) * 1024)
    if val.endswith("Mi"):
        return int(val[:-2])
    if val.endswith("Ki"):
        return int(float(val[:-2]) / 1024)
    return int(val)


def _parse_storage_gi(val: str) -> float:
    """将存储值解析为 GiB。"""
    if not val:
        return 0.0
    val = val.strip()
    if val.endswith("Ti"):
        return float(val[:-2]) * 1024
    if val.endswith("Gi"):
        return float(val[:-2])
    if val.endswith("Mi"):
        return float(val[:-2]) / 1024
    if val.endswith("Ki"):
        return float(val[:-2]) / (1024 * 1024)
    try:
        return float(val)
    except ValueError:
        return 0.0
