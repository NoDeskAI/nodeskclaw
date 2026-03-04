"""Organization settings endpoints -- required genes configuration."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_org_admin
from app.models.base import not_deleted
from app.models.gene import Gene
from app.models.org_required_gene import OrgRequiredGene
from app.schemas.common import ApiResponse
from app.schemas.organization import OrgRequiredGeneAdd, OrgRequiredGeneInfo

logger = logging.getLogger(__name__)

router = APIRouter()


def _to_info(rg: OrgRequiredGene, gene: Gene) -> OrgRequiredGeneInfo:
    return OrgRequiredGeneInfo(
        id=rg.id,
        gene_id=gene.id,
        gene_name=gene.name,
        gene_slug=gene.slug,
        gene_short_description=gene.short_description,
        gene_icon=gene.icon,
        gene_category=gene.category,
    )


@router.get(
    "/{org_id}/required-genes",
    response_model=ApiResponse[list[OrgRequiredGeneInfo]],
)
async def list_required_genes(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: tuple = Depends(require_org_admin),
):
    result = await db.execute(
        select(OrgRequiredGene, Gene)
        .join(Gene, OrgRequiredGene.gene_id == Gene.id)
        .where(
            OrgRequiredGene.org_id == org_id,
            not_deleted(OrgRequiredGene),
            not_deleted(Gene),
        )
        .order_by(OrgRequiredGene.created_at)
    )
    rows = result.all()
    items = [_to_info(rg, gene) for rg, gene in rows]
    return ApiResponse(data=items)


@router.post(
    "/{org_id}/required-genes",
    response_model=ApiResponse[OrgRequiredGeneInfo],
)
async def add_required_gene(
    org_id: str,
    body: OrgRequiredGeneAdd,
    db: AsyncSession = Depends(get_db),
    _auth: tuple = Depends(require_org_admin),
):
    gene = await db.get(Gene, body.gene_id)
    if not gene or gene.deleted_at is not None:
        raise HTTPException(404, detail={
            "error_code": 40440,
            "message_key": "errors.gene.not_found",
            "message": "基因不存在",
        })

    existing = await db.execute(
        select(OrgRequiredGene).where(
            OrgRequiredGene.org_id == org_id,
            OrgRequiredGene.gene_id == body.gene_id,
            not_deleted(OrgRequiredGene),
        ).limit(1)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, detail={
            "error_code": 40901,
            "message_key": "errors.org_settings.gene_already_required",
            "message": "该基因已在必装列表中",
        })

    rg = OrgRequiredGene(org_id=org_id, gene_id=body.gene_id)
    db.add(rg)
    await db.commit()
    await db.refresh(rg)

    return ApiResponse(data=_to_info(rg, gene))


@router.delete(
    "/{org_id}/required-genes/{required_gene_id}",
    response_model=ApiResponse,
)
async def remove_required_gene(
    org_id: str,
    required_gene_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: tuple = Depends(require_org_admin),
):
    result = await db.execute(
        select(OrgRequiredGene).where(
            OrgRequiredGene.id == required_gene_id,
            OrgRequiredGene.org_id == org_id,
            not_deleted(OrgRequiredGene),
        )
    )
    rg = result.scalar_one_or_none()
    if not rg:
        raise HTTPException(404, detail={
            "error_code": 40441,
            "message_key": "errors.org_settings.required_gene_not_found",
            "message": "必装基因记录不存在",
        })

    rg.soft_delete()
    await db.commit()
    return ApiResponse(message="已移除")
