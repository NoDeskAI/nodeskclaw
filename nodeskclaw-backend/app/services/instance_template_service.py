"""Instance template CRUD service."""

import json
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.base import not_deleted
from app.models.gene import Gene, InstanceGene
from app.models.instance import Instance
from app.models.instance_template import InstanceTemplate
from app.schemas.instance_template import (
    GeneRef,
    InstanceTemplateCreate,
    InstanceTemplateFromInstance,
    InstanceTemplateInfo,
    InstanceTemplateUpdate,
)

logger = logging.getLogger(__name__)


def _parse_gene_slugs(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


def _template_to_info(tpl: InstanceTemplate, genes: list[GeneRef] | None = None) -> InstanceTemplateInfo:
    return InstanceTemplateInfo(
        id=tpl.id,
        name=tpl.name,
        slug=tpl.slug,
        description=tpl.description,
        short_description=tpl.short_description,
        icon=tpl.icon,
        gene_slugs=_parse_gene_slugs(tpl.gene_slugs),
        genes=genes or [],
        source_instance_id=tpl.source_instance_id,
        is_published=tpl.is_published,
        is_featured=tpl.is_featured,
        use_count=tpl.use_count,
        created_by=tpl.created_by,
        org_id=tpl.org_id,
        created_at=tpl.created_at,
    )


async def _resolve_gene_refs(db: AsyncSession, slugs: list[str]) -> list[GeneRef]:
    if not slugs:
        return []
    result = await db.execute(
        select(Gene).where(Gene.slug.in_(slugs), not_deleted(Gene))
    )
    gene_map = {g.slug: g for g in result.scalars().all()}
    return [
        GeneRef(
            slug=s,
            name=gene_map[s].name if s in gene_map else s,
            short_description=gene_map[s].short_description if s in gene_map else None,
            category=gene_map[s].category if s in gene_map else None,
            icon=gene_map[s].icon if s in gene_map else None,
        )
        for s in slugs
    ]


async def list_templates(
    db: AsyncSession,
    *,
    org_id: str | None = None,
    keyword: str | None = None,
    featured_only: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[InstanceTemplateInfo], int]:
    q = select(InstanceTemplate).where(not_deleted(InstanceTemplate), InstanceTemplate.is_published.is_(True))
    if org_id:
        q = q.where(InstanceTemplate.org_id == org_id)
    if keyword:
        like = f"%{keyword}%"
        q = q.where(InstanceTemplate.name.ilike(like) | InstanceTemplate.description.ilike(like))
    if featured_only:
        q = q.where(InstanceTemplate.is_featured.is_(True))

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = q.order_by(InstanceTemplate.use_count.desc(), InstanceTemplate.created_at.desc())
    q = q.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    templates = result.scalars().all()

    items = [_template_to_info(t) for t in templates]
    return items, total


async def get_template(db: AsyncSession, template_id: str) -> InstanceTemplateInfo:
    result = await db.execute(
        select(InstanceTemplate).where(InstanceTemplate.id == template_id, not_deleted(InstanceTemplate))
    )
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise NotFoundError("AI \u5458\u5de5\u6a21\u677f\u4e0d\u5b58\u5728")

    slugs = _parse_gene_slugs(tpl.gene_slugs)
    genes = await _resolve_gene_refs(db, slugs)
    return _template_to_info(tpl, genes)


async def get_template_gene_slugs(db: AsyncSession, template_id: str) -> list[str]:
    result = await db.execute(
        select(InstanceTemplate).where(InstanceTemplate.id == template_id, not_deleted(InstanceTemplate))
    )
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise NotFoundError("AI \u5458\u5de5\u6a21\u677f\u4e0d\u5b58\u5728")
    return _parse_gene_slugs(tpl.gene_slugs)


async def create_template(
    db: AsyncSession,
    req: InstanceTemplateCreate,
    user_id: str,
    org_id: str | None = None,
) -> InstanceTemplateInfo:
    existing = await db.execute(
        select(InstanceTemplate).where(
            InstanceTemplate.slug == req.slug,
            InstanceTemplate.org_id == org_id,
            not_deleted(InstanceTemplate),
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictError(f"\u6a21\u677f slug '{req.slug}' \u5df2\u5b58\u5728")

    tpl = InstanceTemplate(
        name=req.name,
        slug=req.slug,
        description=req.description,
        short_description=req.short_description,
        icon=req.icon,
        gene_slugs=json.dumps(req.gene_slugs),
        created_by=user_id,
        org_id=org_id,
    )
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)

    genes = await _resolve_gene_refs(db, req.gene_slugs)
    return _template_to_info(tpl, genes)


async def create_from_instance(
    db: AsyncSession,
    instance_id: str,
    req: InstanceTemplateFromInstance,
    user_id: str,
    org_id: str | None = None,
) -> InstanceTemplateInfo:
    inst = await db.execute(
        select(Instance).where(Instance.id == instance_id, not_deleted(Instance))
    )
    if not inst.scalar_one_or_none():
        raise NotFoundError("\u5b9e\u4f8b\u4e0d\u5b58\u5728")

    existing = await db.execute(
        select(InstanceTemplate).where(
            InstanceTemplate.slug == req.slug,
            InstanceTemplate.org_id == org_id,
            not_deleted(InstanceTemplate),
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictError(f"\u6a21\u677f slug '{req.slug}' \u5df2\u5b58\u5728")

    ig_result = await db.execute(
        select(Gene.slug).join(InstanceGene, InstanceGene.gene_id == Gene.id).where(
            InstanceGene.instance_id == instance_id,
            InstanceGene.status == "installed",
            not_deleted(InstanceGene),
            not_deleted(Gene),
        )
    )
    gene_slugs = [row[0] for row in ig_result.all()]

    tpl = InstanceTemplate(
        name=req.name,
        slug=req.slug,
        description=req.description,
        short_description=req.short_description,
        icon=req.icon,
        gene_slugs=json.dumps(gene_slugs),
        source_instance_id=instance_id,
        created_by=user_id,
        org_id=org_id,
    )
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)

    genes = await _resolve_gene_refs(db, gene_slugs)
    return _template_to_info(tpl, genes)


async def update_template(
    db: AsyncSession,
    template_id: str,
    req: InstanceTemplateUpdate,
) -> InstanceTemplateInfo:
    result = await db.execute(
        select(InstanceTemplate).where(InstanceTemplate.id == template_id, not_deleted(InstanceTemplate))
    )
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise NotFoundError("AI \u5458\u5de5\u6a21\u677f\u4e0d\u5b58\u5728")

    if req.name is not None:
        tpl.name = req.name
    if req.description is not None:
        tpl.description = req.description
    if req.short_description is not None:
        tpl.short_description = req.short_description
    if req.icon is not None:
        tpl.icon = req.icon
    if req.gene_slugs is not None:
        tpl.gene_slugs = json.dumps(req.gene_slugs)

    await db.commit()
    await db.refresh(tpl)

    slugs = _parse_gene_slugs(tpl.gene_slugs)
    genes = await _resolve_gene_refs(db, slugs)
    return _template_to_info(tpl, genes)


async def delete_template(db: AsyncSession, template_id: str) -> dict:
    result = await db.execute(
        select(InstanceTemplate).where(InstanceTemplate.id == template_id, not_deleted(InstanceTemplate))
    )
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise NotFoundError("AI \u5458\u5de5\u6a21\u677f\u4e0d\u5b58\u5728")
    tpl.soft_delete()
    await db.commit()
    return {"deleted": True}


async def increment_use_count(db: AsyncSession, template_id: str) -> None:
    result = await db.execute(
        select(InstanceTemplate).where(InstanceTemplate.id == template_id, not_deleted(InstanceTemplate))
    )
    tpl = result.scalar_one_or_none()
    if tpl:
        tpl.use_count = (tpl.use_count or 0) + 1
        await db.commit()
