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
    # 统计实例数
    count_result = await db.execute(
        select(func.count()).where(
            Instance.org_id == org.id,
            not_deleted(Instance),
        )
    )
    instance_count = count_result.scalar_one()

    # 统计 CPU/MEM 使用量（按 limit 计算）
    instances_result = await db.execute(
        select(Instance.cpu_limit, Instance.mem_limit).where(
            Instance.org_id == org.id,
            not_deleted(Instance),
        )
    )
    total_cpu_m = 0
    total_mem_mi = 0
    for cpu_limit, mem_limit in instances_result.all():
        total_cpu_m += _parse_cpu_millis(cpu_limit)
        total_mem_mi += _parse_mem_mi(mem_limit)

    return OrgUsage(
        instance_count=instance_count,
        instance_limit=org.max_instances,
        cpu_used=f"{total_cpu_m}m",
        cpu_limit=org.max_cpu_total,
        mem_used=f"{total_mem_mi}Mi",
        mem_limit=org.max_mem_total,
    )


async def check_deploy_quota(org: Organization, db: AsyncSession) -> None:
    """部署前检查配额，不满足则抛异常。"""
    usage = await get_org_usage(org, db)

    if usage.instance_count >= usage.instance_limit:
        raise BadRequestError(
            f"实例数量已达上限 ({usage.instance_count}/{usage.instance_limit})，"
            "请升级套餐或联系管理员"
        )


async def upgrade_org_plan(org: Organization, plan_name: str, db: AsyncSession) -> Organization:
    """升级组织套餐，同步更新配额。"""
    plan = await get_plan_by_name(plan_name, db)

    org.plan = plan.name
    org.max_instances = plan.max_instances

    # 企业版配额更大
    if plan.name == "enterprise":
        org.max_cpu_total = "200"
        org.max_mem_total = "400Gi"
    elif plan.name == "pro":
        org.max_cpu_total = "80"
        org.max_mem_total = "160Gi"
    else:
        org.max_cpu_total = "4"
        org.max_mem_total = "8Gi"

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
