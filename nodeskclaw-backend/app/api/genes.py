"""Gene Evolution Ecosystem API routes."""

import logging
import re

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_org, get_db
from app.core.exceptions import BadRequestError, NotFoundError
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
    ManualGeneCreate,
    PublishVariantRequest,
    RatingRequest,
    ReviewRequest,
    UninstallGeneRequest,
    UpdateGeneRequest,
    UpdateGenomeRequest,
)
from app.services import gene_service

logger = logging.getLogger(__name__)
router = APIRouter()


def _validate_gene_callback_auth(
    payload: LearningCallbackPayload,
    mode: str,
    sig: str | None,
    instance_id: str | None,
) -> None:
    if sig or instance_id:
        if not sig or not instance_id:
            raise BadRequestError("回调签名参数不完整")
        if payload.instance_id != instance_id:
            raise BadRequestError("回调实例与签名参数不匹配")
        if not gene_service.verify_gene_callback_signature(payload, mode, sig):
            raise BadRequestError("回调签名无效")
        return

    if not settings.ALLOW_LEGACY_GENE_CALLBACKS:
        raise BadRequestError("缺少回调签名参数")

    logger.warning(
        "Allowing legacy unsigned gene callback mode=%s task_id=%s instance_id=%s",
        mode,
        payload.task_id,
        payload.instance_id,
    )


# ═══════════════════════════════════════════════════
#  Gene Market
# ═══════════════════════════════════════════════════


@router.get("/genes")
async def list_genes(
    keyword: str | None = None,
    tag: str | None = None,
    category: str | None = None,
    source: str | None = None,
    visibility: str | None = None,
    sort: str = "popularity",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    genes, total = await gene_service.list_genes(
        db, keyword=keyword, tag=tag, category=category, source=source,
        visibility=visibility, org_id=current_user.current_org_id,
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


@router.get("/genes/{gene_slug}")
async def get_gene(
    gene_slug: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    gene = await gene_service.get_gene(db, gene_slug)
    return ApiResponse(data=gene)


@router.get("/genes/{gene_slug}/variants")
async def gene_variants(
    gene_slug: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    variants = await gene_service.get_gene_variants(db, gene_slug)
    return ApiResponse(data=variants)


@router.get("/genes/{gene_slug}/synergies")
async def gene_synergies(
    gene_slug: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    synergies = await gene_service.get_gene_synergies(db, gene_slug)
    return ApiResponse(data=synergies)


@router.get("/genes/{gene_slug}/genomes")
async def gene_genomes(
    gene_slug: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    data = await gene_service.get_gene_genomes(db, gene_slug)
    return ApiResponse(data=data)


@router.get("/genes/{gene_slug}/installed-instances")
async def gene_installed_instances(
    gene_slug: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    ids = await gene_service.get_gene_installed_instance_ids(db, gene_slug)
    return ApiResponse(data=ids)


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
    org_ctx=Depends(get_current_org),
):
    _current_user, org = org_ctx
    genes = await gene_service.get_instance_genes(db, instance_id, org.id)
    return ApiResponse(data=genes)


@router.get("/instances/{instance_id}/skills")
async def instance_skills(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    _current_user, org = org_ctx
    skills = await gene_service.get_instance_skills(db, instance_id, org.id)
    return ApiResponse(data=skills)


_SAFE_SKILL_NAME = re.compile(r"^[a-zA-Z0-9_-]+$")


class _SkillContentUpdate(BaseModel):
    content: str


@router.get("/instances/{instance_id}/skills/{skill_name}/content")
async def get_skill_content(
    instance_id: str,
    skill_name: str,
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    if not _SAFE_SKILL_NAME.match(skill_name):
        raise BadRequestError(message="skill_name 包含非法字符")

    _current_user, org = org_ctx
    from app.services.instance_service import get_instance
    instance = await get_instance(instance_id, db, org.id)

    from app.services.runtime.registries.runtime_registry import RUNTIME_REGISTRY
    spec = RUNTIME_REGISTRY.get(instance.runtime)
    skills_dir = spec.skills_dir_rel if spec else ".openclaw/skills"

    from app.services.nfs_mount import remote_fs
    async with remote_fs(instance, db) as fs:
        content = await fs.read_text(f"{skills_dir}/{skill_name}/SKILL.md")

    if content is None:
        raise NotFoundError(message=f"Skill '{skill_name}' 不存在")

    return ApiResponse(data={"skill_name": skill_name, "content": content})


@router.put("/instances/{instance_id}/skills/{skill_name}/content")
async def update_skill_content(
    instance_id: str,
    skill_name: str,
    body: _SkillContentUpdate,
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    if not _SAFE_SKILL_NAME.match(skill_name):
        raise BadRequestError(message="skill_name 包含非法字符")

    _current_user, org = org_ctx
    from app.services.instance_service import get_instance
    instance = await get_instance(instance_id, db, org.id)

    from app.services.runtime.registries.runtime_registry import RUNTIME_REGISTRY
    spec = RUNTIME_REGISTRY.get(instance.runtime)
    skills_dir = spec.skills_dir_rel if spec else ".openclaw/skills"

    from app.services.nfs_mount import remote_fs
    async with remote_fs(instance, db) as fs:
        existing = await fs.read_text(f"{skills_dir}/{skill_name}/SKILL.md")
        if existing is None:
            raise NotFoundError(message=f"Skill '{skill_name}' 不存在")
        await fs.write_text(f"{skills_dir}/{skill_name}/SKILL.md", body.content)

    return ApiResponse(data={"skill_name": skill_name, "updated": True})


@router.post("/instances/{instance_id}/genes/install")
async def install_gene(
    instance_id: str,
    req: InstallGeneRequest,
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    _current_user, org = org_ctx
    result = await gene_service.install_gene(db, instance_id, req.gene_slug, org_id=org.id)
    return ApiResponse(data=result)


@router.post("/instances/{instance_id}/genes/uninstall")
async def uninstall_gene(
    instance_id: str,
    req: UninstallGeneRequest,
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    _current_user, org = org_ctx
    result = await gene_service.uninstall_gene(db, instance_id, req.gene_id, org_id=org.id)
    return ApiResponse(data=result)


@router.post("/instances/{instance_id}/genomes/apply")
async def apply_genome(
    instance_id: str,
    req: ApplyGenomeRequest,
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    _current_user, org = org_ctx
    result = await gene_service.apply_genome(db, instance_id, req.genome_id, org.id)
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
    org_ctx=Depends(get_current_org),
):
    _current_user, org = org_ctx
    await gene_service.get_instance_genes(db, instance_id, org.id)
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
    org_ctx=Depends(get_current_org),
):
    _current_user, org = org_ctx
    await gene_service.get_instance_genes(db, instance_id, org.id)
    result = await gene_service.log_effectiveness(
        db, instance_id, gene_id, req.metric_type, req.value, req.context
    )
    return ApiResponse(data=result)


@router.post("/instances/{instance_id}/genes/create")
async def create_gene_from_agent(
    instance_id: str,
    req: CreateGeneRequest,
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    _current_user, org = org_ctx
    result = await gene_service.trigger_gene_creation(db, instance_id, req.creation_prompt, org.id)
    return ApiResponse(data=result)


# ═══════════════════════════════════════════════════
#  Learning Plugin Callbacks (no auth - internal)
# ═══════════════════════════════════════════════════


@router.post("/genes/learning-callback")
async def learning_callback(
    payload: LearningCallbackPayload,
    sig: str | None = Query(None),
    instance_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    _validate_gene_callback_auth(payload, "learn", sig, instance_id)
    result = await gene_service.handle_learning_callback(db, payload)
    return ApiResponse(data=result)


@router.post("/genes/creation-callback")
async def creation_callback(
    payload: LearningCallbackPayload,
    sig: str | None = Query(None),
    instance_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    _validate_gene_callback_auth(payload, "create", sig, instance_id)
    result = await gene_service.handle_creation_callback(db, payload)
    return ApiResponse(data=result)


@router.post("/genes/forgetting-callback")
async def forgetting_callback(
    payload: LearningCallbackPayload,
    sig: str | None = Query(None),
    instance_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    _validate_gene_callback_auth(payload, "forget", sig, instance_id)
    result = await gene_service.handle_forgetting_callback(db, payload)
    return ApiResponse(data=result)


# ═══════════════════════════════════════════════════
#  Evolution Log
# ═══════════════════════════════════════════════════


@router.get("/instances/{instance_id}/evolution-log")
async def get_evolution_log(
    instance_id: str,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    org_ctx=Depends(get_current_org),
):
    _current_user, org = org_ctx
    events = await gene_service.get_evolution_log(db, instance_id, page, page_size, org.id)
    return ApiResponse(data=events)


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


@router.get("/admin/genes")
async def admin_list_genes(
    keyword: str | None = None,
    category: str | None = None,
    is_published: bool | None = None,
    sort: str = "newest",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    genes, total = await gene_service.admin_list_genes(
        db, keyword=keyword, category=category, is_published=is_published,
        sort=sort, page=page, page_size=page_size,
    )
    return PaginatedResponse(
        data=genes,
        pagination=Pagination(page=page, page_size=page_size, total=total),
    )


@router.post("/admin/genes")
async def admin_create_gene(
    req: GeneCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    gene = await gene_service.create_gene(db, req, user_id=current_user.id, org_id=current_user.org_id)
    return ApiResponse(data=gene)


@router.put("/admin/genes/{gene_id}")
async def admin_update_gene(
    gene_id: str,
    req: UpdateGeneRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    result = await gene_service.update_gene(db, gene_id, req)
    return ApiResponse(data=result)


@router.delete("/admin/genes/{gene_id}")
async def admin_delete_gene(
    gene_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    result = await gene_service.soft_delete_gene(db, gene_id)
    return ApiResponse(data=result)


@router.put("/admin/genes/{gene_id}/review")
async def admin_review_gene(
    gene_id: str,
    req: ReviewRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    result = await gene_service.review_gene(db, gene_id, req.action, req.reason)
    return ApiResponse(data=result)


@router.get("/admin/genomes")
async def admin_list_genomes(
    keyword: str | None = None,
    is_published: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    genomes, total = await gene_service.admin_list_genomes(
        db, keyword=keyword, is_published=is_published,
        page=page, page_size=page_size,
    )
    return PaginatedResponse(
        data=genomes,
        pagination=Pagination(page=page, page_size=page_size, total=total),
    )


@router.post("/admin/genomes")
async def admin_create_genome(
    req: GenomeCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    genome = await gene_service.create_genome(db, req, user_id=current_user.id, org_id=current_user.org_id)
    return ApiResponse(data=genome)


@router.put("/admin/genomes/{genome_id}")
async def admin_update_genome(
    genome_id: str,
    req: UpdateGenomeRequest,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    result = await gene_service.update_genome(db, genome_id, req)
    return ApiResponse(data=result)


@router.delete("/admin/genomes/{genome_id}")
async def admin_delete_genome(
    genome_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    result = await gene_service.soft_delete_genome(db, genome_id)
    return ApiResponse(data=result)


# ═══════════════════════════════════════════════════
#  Manual Gene Creation & Publishing
# ═══════════════════════════════════════════════════


@router.post("/genes/manual")
async def create_manual_gene(
    req: ManualGeneCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    gene_req = GeneCreateRequest(
        name=req.name,
        slug=req.slug,
        description=req.description,
        short_description=req.short_description,
        category=req.category,
        source="manual",
        is_published=False,
        manifest={"skill": {"name": req.slug, "content": req.skill_content}},
    )
    gene_data = await gene_service.create_gene(
        db, gene_req, user_id=current_user.id, org_id=current_user.current_org_id,
    )
    await gene_service.install_gene_prerestart(req.instance_id, req.slug)
    return ApiResponse(data=gene_data)


@router.post("/genes/{gene_id}/publish-to-market")
async def publish_gene_to_market(
    gene_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await gene_service.publish_gene_to_market(
        db, gene_id, user_id=current_user.id,
    )
    return ApiResponse(data=result)
