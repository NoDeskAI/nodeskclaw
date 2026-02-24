"""Gene Evolution Ecosystem API routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.common import ApiResponse, PaginatedResponse, Pagination
from app.schemas.gene import (
    ApplyGenomeRequest,
    CreateGeneRequest,
    EffectivenessRequest,
    GeneCreateRequest,
    GenomeCreateRequest,
    InstallGeneRequest,
    LearningCallbackPayload,
    PublishVariantRequest,
    RatingRequest,
    ReviewRequest,
    UninstallGeneRequest,
)
from app.services import gene_service

router = APIRouter()


# ═══════════════════════════════════════════════════
#  Gene Market
# ═══════════════════════════════════════════════════


@router.get("/genes")
async def list_genes(
    keyword: str | None = None,
    tag: str | None = None,
    category: str | None = None,
    source: str | None = None,
    sort: str = "popularity",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    genes, total = await gene_service.list_genes(
        db, keyword=keyword, tag=tag, category=category, source=source,
        sort=sort, page=page, page_size=page_size,
    )
    return PaginatedResponse(
        data=genes,
        pagination=Pagination(page=page, page_size=page_size, total=total),
    )


@router.get("/genes/tags")
async def gene_tags(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    tags = await gene_service.get_gene_tags(db)
    return ApiResponse(data=[t.model_dump() for t in tags])


@router.get("/genes/featured")
async def featured_genes(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    genes = await gene_service.get_featured_genes(db, limit=limit)
    return ApiResponse(data=genes)


@router.get("/genes/{gene_id}")
async def get_gene(
    gene_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    gene = await gene_service.get_gene(db, gene_id)
    return ApiResponse(data=gene)


@router.get("/genes/{gene_id}/variants")
async def gene_variants(
    gene_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    variants = await gene_service.get_gene_variants(db, gene_id)
    return ApiResponse(data=variants)


@router.get("/genes/{gene_id}/synergies")
async def gene_synergies(
    gene_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    synergies = await gene_service.get_gene_synergies(db, gene_id)
    return ApiResponse(data=synergies)


@router.post("/genes/{gene_id}/rate")
async def rate_gene(
    gene_id: str,
    req: RatingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await gene_service.rate_gene(db, gene_id, current_user.id, req.rating, req.comment)
    return ApiResponse(data=result)


# ═══════════════════════════════════════════════════
#  Genome Market
# ═══════════════════════════════════════════════════


@router.get("/genomes")
async def list_genomes(
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    genomes, total = await gene_service.list_genomes(db, keyword=keyword, page=page, page_size=page_size)
    return PaginatedResponse(
        data=genomes,
        pagination=Pagination(page=page, page_size=page_size, total=total),
    )


@router.get("/genomes/featured")
async def featured_genomes(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    genomes = await gene_service.get_featured_genomes(db, limit=limit)
    return ApiResponse(data=genomes)


@router.get("/genomes/{genome_id}")
async def get_genome(
    genome_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    genome = await gene_service.get_genome(db, genome_id)
    return ApiResponse(data=genome)


@router.post("/genomes/{genome_id}/rate")
async def rate_genome(
    genome_id: str,
    req: RatingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await gene_service.rate_genome(db, genome_id, current_user.id, req.rating, req.comment)
    return ApiResponse(data=result)


# ═══════════════════════════════════════════════════
#  Instance Gene Management
# ═══════════════════════════════════════════════════


@router.get("/instances/{instance_id}/genes")
async def instance_genes(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    genes = await gene_service.get_instance_genes(db, instance_id)
    return ApiResponse(data=genes)


@router.post("/instances/{instance_id}/genes/install")
async def install_gene(
    instance_id: str,
    req: InstallGeneRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    result = await gene_service.install_gene(db, instance_id, req.gene_slug)
    return ApiResponse(data=result)


@router.post("/instances/{instance_id}/genes/uninstall")
async def uninstall_gene(
    instance_id: str,
    req: UninstallGeneRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    result = await gene_service.uninstall_gene(db, instance_id, req.gene_id)
    return ApiResponse(data=result)


@router.post("/instances/{instance_id}/genomes/apply")
async def apply_genome(
    instance_id: str,
    req: ApplyGenomeRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    result = await gene_service.apply_genome(db, instance_id, req.genome_id)
    return ApiResponse(data=result)


# ═══════════════════════════════════════════════════
#  Evolution: Variant, Effectiveness, Creation
# ═══════════════════════════════════════════════════


@router.post("/instances/{instance_id}/genes/{gene_id}/publish-variant")
async def publish_variant(
    instance_id: str,
    gene_id: str,
    req: PublishVariantRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    result = await gene_service.publish_variant(
        db, instance_id, gene_id, req.variant_name, req.variant_slug
    )
    return ApiResponse(data=result)


@router.post("/instances/{instance_id}/genes/{gene_id}/effectiveness")
async def log_effectiveness(
    instance_id: str,
    gene_id: str,
    req: EffectivenessRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    result = await gene_service.log_effectiveness(
        db, instance_id, gene_id, req.metric_type, req.value, req.context
    )
    return ApiResponse(data=result)


@router.post("/instances/{instance_id}/genes/create")
async def create_gene_from_agent(
    instance_id: str,
    req: CreateGeneRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    result = await gene_service.trigger_gene_creation(db, instance_id, req.creation_prompt)
    return ApiResponse(data=result)


# ═══════════════════════════════════════════════════
#  Learning Plugin Callbacks (no auth - internal)
# ═══════════════════════════════════════════════════


@router.post("/genes/learning-callback")
async def learning_callback(
    payload: LearningCallbackPayload,
    db: AsyncSession = Depends(get_db),
):
    result = await gene_service.handle_learning_callback(db, payload)
    return ApiResponse(data=result)


@router.post("/genes/creation-callback")
async def creation_callback(
    payload: LearningCallbackPayload,
    db: AsyncSession = Depends(get_db),
):
    result = await gene_service.handle_creation_callback(db, payload)
    return ApiResponse(data=result)


# ═══════════════════════════════════════════════════
#  Admin
# ═══════════════════════════════════════════════════


@router.get("/admin/genes/stats")
async def admin_gene_stats(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    stats = await gene_service.get_gene_stats(db)
    return ApiResponse(data=stats.model_dump())


@router.get("/admin/genes/pending-review")
async def admin_pending_review_genes(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    genes = await gene_service.get_pending_review_genes(db)
    return ApiResponse(data=genes)


@router.get("/admin/genes/activity")
async def admin_gene_activity(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    activity = await gene_service.get_gene_activity(db, limit=limit)
    return ApiResponse(data=activity)


@router.get("/admin/genes/matrix")
async def admin_gene_matrix(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    matrix = await gene_service.get_gene_matrix(db)
    return ApiResponse(data=matrix)


@router.get("/admin/genes/co-install")
async def admin_co_install(
    min_count: int = Query(2, ge=1),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    pairs = await gene_service.get_co_install_analysis(db, min_count=min_count)
    return ApiResponse(data=[p.model_dump() for p in pairs])


@router.put("/admin/genes/{gene_id}/review")
async def admin_review_gene(
    gene_id: str,
    req: ReviewRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    result = await gene_service.review_gene(db, gene_id, req.action, req.reason)
    return ApiResponse(data=result)
