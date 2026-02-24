"""Gene Evolution Ecosystem service: CRUD, install/learn engine, rating, evolution."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import Integer, Select, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.base import not_deleted
from app.models.gene import (
    EffectMetricType,
    Gene,
    GeneEffectLog,
    GeneRating,
    GeneReviewStatus,
    GeneSource,
    Genome,
    GenomeRating,
    InstanceGene,
    InstanceGeneStatus,
)
from app.models.instance import Instance
from app.schemas.gene import (
    CoInstallPair,
    GeneCreateRequest,
    GeneStatsResponse,
    GenomeCreateRequest,
    LearningCallbackPayload,
    TagStats,
)
from app.services.nfs_mount import nfs_mount

logger = logging.getLogger(__name__)

OPENCLAW_CONFIG_REL = Path(".openclaw") / "openclaw.json"
SKILLS_DIR_REL = Path(".openclaw") / "skills"


def _json_loads(raw: str | None) -> list | dict | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _json_dumps(obj) -> str | None:
    if obj is None:
        return None
    return json.dumps(obj, ensure_ascii=False)


def _gene_to_dict(gene: Gene) -> dict:
    return {
        "id": gene.id,
        "name": gene.name,
        "slug": gene.slug,
        "description": gene.description,
        "short_description": gene.short_description,
        "category": gene.category,
        "tags": _json_loads(gene.tags) or [],
        "source": gene.source,
        "source_ref": gene.source_ref,
        "icon": gene.icon,
        "version": gene.version,
        "manifest": _json_loads(gene.manifest),
        "dependencies": _json_loads(gene.dependencies) or [],
        "synergies": _json_loads(gene.synergies) or [],
        "parent_gene_id": gene.parent_gene_id,
        "created_by_instance_id": gene.created_by_instance_id,
        "install_count": gene.install_count,
        "avg_rating": gene.avg_rating,
        "effectiveness_score": gene.effectiveness_score,
        "is_featured": gene.is_featured,
        "review_status": gene.review_status,
        "is_published": gene.is_published,
        "created_by": gene.created_by,
        "org_id": gene.org_id,
        "created_at": gene.created_at,
        "updated_at": gene.updated_at,
    }


def _genome_to_dict(genome: Genome) -> dict:
    return {
        "id": genome.id,
        "name": genome.name,
        "slug": genome.slug,
        "description": genome.description,
        "short_description": genome.short_description,
        "icon": genome.icon,
        "gene_slugs": _json_loads(genome.gene_slugs) or [],
        "config_override": _json_loads(genome.config_override),
        "install_count": genome.install_count,
        "avg_rating": genome.avg_rating,
        "is_featured": genome.is_featured,
        "is_published": genome.is_published,
        "created_by": genome.created_by,
        "org_id": genome.org_id,
        "created_at": genome.created_at,
    }


# ═══════════════════════════════════════════════════
#  CRUD + Market Query
# ═══════════════════════════════════════════════════


async def list_genes(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    tag: str | None = None,
    category: str | None = None,
    source: str | None = None,
    sort: str = "popularity",
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    base = select(Gene).where(not_deleted(Gene), Gene.is_published.is_(True))

    if keyword:
        base = base.where(Gene.name.ilike(f"%{keyword}%") | Gene.slug.ilike(f"%{keyword}%"))
    if tag:
        base = base.where(Gene.tags.ilike(f'%"{tag}"%'))
    if category:
        base = base.where(Gene.category == category)
    if source:
        base = base.where(Gene.source == source)

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    sort_map = {
        "popularity": Gene.install_count.desc(),
        "rating": Gene.avg_rating.desc(),
        "effectiveness": Gene.effectiveness_score.desc(),
        "newest": Gene.created_at.desc(),
    }
    base = base.order_by(sort_map.get(sort, Gene.install_count.desc()))
    base = base.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(base)
    genes = result.scalars().all()
    return [_gene_to_dict(g) for g in genes], total


async def get_gene(db: AsyncSession, gene_id: str) -> dict:
    result = await db.execute(
        select(Gene).where(Gene.id == gene_id, not_deleted(Gene))
    )
    gene = result.scalar_one_or_none()
    if not gene:
        raise AppException(404, "基因不存在")
    return _gene_to_dict(gene)


async def get_gene_by_slug(db: AsyncSession, slug: str) -> Gene | None:
    result = await db.execute(
        select(Gene).where(Gene.slug == slug, not_deleted(Gene))
    )
    return result.scalar_one_or_none()


async def create_gene(
    db: AsyncSession, req: GeneCreateRequest, user_id: str | None = None, org_id: str | None = None
) -> dict:
    existing = await get_gene_by_slug(db, req.slug)
    if existing:
        raise AppException(409, f"基因 slug '{req.slug}' 已存在")

    gene = Gene(
        name=req.name,
        slug=req.slug,
        description=req.description,
        short_description=req.short_description,
        category=req.category,
        tags=_json_dumps(req.tags),
        source=req.source,
        source_ref=req.source_ref,
        icon=req.icon,
        version=req.version,
        manifest=_json_dumps(req.manifest),
        dependencies=_json_dumps(req.dependencies),
        synergies=_json_dumps(req.synergies),
        is_featured=req.is_featured,
        is_published=req.is_published,
        created_by=user_id,
        org_id=org_id,
    )
    db.add(gene)
    await db.commit()
    await db.refresh(gene)
    return _gene_to_dict(gene)


async def get_gene_tags(db: AsyncSession) -> list[TagStats]:
    result = await db.execute(
        select(Gene.tags).where(not_deleted(Gene), Gene.is_published.is_(True))
    )
    tag_count: dict[str, int] = {}
    for (raw,) in result:
        tags = _json_loads(raw) or []
        for t in tags:
            tag_count[t] = tag_count.get(t, 0) + 1
    return [TagStats(tag=t, count=c) for t, c in sorted(tag_count.items(), key=lambda x: -x[1])]


async def get_featured_genes(db: AsyncSession, limit: int = 10) -> list[dict]:
    result = await db.execute(
        select(Gene)
        .where(not_deleted(Gene), Gene.is_published.is_(True), Gene.is_featured.is_(True))
        .order_by(Gene.effectiveness_score.desc())
        .limit(limit)
    )
    return [_gene_to_dict(g) for g in result.scalars().all()]


async def get_gene_variants(db: AsyncSession, gene_id: str) -> list[dict]:
    result = await db.execute(
        select(Gene)
        .where(Gene.parent_gene_id == gene_id, not_deleted(Gene), Gene.is_published.is_(True))
        .order_by(Gene.effectiveness_score.desc())
    )
    return [_gene_to_dict(g) for g in result.scalars().all()]


async def get_gene_synergies(db: AsyncSession, gene_id: str) -> list[dict]:
    gene = await db.execute(
        select(Gene).where(Gene.id == gene_id, not_deleted(Gene))
    )
    gene_obj = gene.scalar_one_or_none()
    if not gene_obj:
        return []

    slugs = _json_loads(gene_obj.synergies) or []
    if not slugs:
        return []

    result = await db.execute(
        select(Gene).where(Gene.slug.in_(slugs), not_deleted(Gene), Gene.is_published.is_(True))
    )
    return [_gene_to_dict(g) for g in result.scalars().all()]


# ── Genome CRUD ──────────────────────────────────


async def list_genomes(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    base = select(Genome).where(not_deleted(Genome), Genome.is_published.is_(True))
    if keyword:
        base = base.where(Genome.name.ilike(f"%{keyword}%") | Genome.slug.ilike(f"%{keyword}%"))

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    base = base.order_by(Genome.install_count.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(base)
    return [_genome_to_dict(g) for g in result.scalars().all()], total


async def get_genome(db: AsyncSession, genome_id: str) -> dict:
    result = await db.execute(
        select(Genome).where(Genome.id == genome_id, not_deleted(Genome))
    )
    genome = result.scalar_one_or_none()
    if not genome:
        raise AppException(404, "基因组不存在")
    return _genome_to_dict(genome)


async def create_genome(
    db: AsyncSession, req: GenomeCreateRequest, user_id: str | None = None, org_id: str | None = None
) -> dict:
    genome = Genome(
        name=req.name,
        slug=req.slug,
        description=req.description,
        short_description=req.short_description,
        icon=req.icon,
        gene_slugs=_json_dumps(req.gene_slugs),
        config_override=_json_dumps(req.config_override),
        is_featured=req.is_featured,
        is_published=req.is_published,
        created_by=user_id,
        org_id=org_id,
    )
    db.add(genome)
    await db.commit()
    await db.refresh(genome)
    return _genome_to_dict(genome)


async def get_featured_genomes(db: AsyncSession, limit: int = 10) -> list[dict]:
    result = await db.execute(
        select(Genome)
        .where(not_deleted(Genome), Genome.is_published.is_(True), Genome.is_featured.is_(True))
        .order_by(Genome.install_count.desc())
        .limit(limit)
    )
    return [_genome_to_dict(g) for g in result.scalars().all()]


# ═══════════════════════════════════════════════════
#  Install / Learn Engine
# ═══════════════════════════════════════════════════


async def get_instance_genes(db: AsyncSession, instance_id: str) -> list[dict]:
    q = (
        select(InstanceGene, Gene)
        .join(Gene, InstanceGene.gene_id == Gene.id)
        .where(InstanceGene.instance_id == instance_id, not_deleted(InstanceGene))
        .order_by(InstanceGene.created_at.desc())
    )
    result = await db.execute(q)
    rows = result.all()
    items = []
    for ig, gene in rows:
        d = {
            "id": ig.id,
            "instance_id": ig.instance_id,
            "gene_id": ig.gene_id,
            "genome_id": ig.genome_id,
            "status": ig.status,
            "installed_version": ig.installed_version,
            "learning_output": ig.learning_output,
            "config_snapshot": _json_loads(ig.config_snapshot),
            "agent_self_eval": ig.agent_self_eval,
            "usage_count": ig.usage_count,
            "variant_published": ig.variant_published,
            "installed_at": ig.installed_at,
            "created_at": ig.created_at,
            "gene": _gene_to_dict(gene),
        }
        items.append(d)
    return items


async def _has_meta_learning(db: AsyncSession, instance_id: str) -> bool:
    """Check if instance has meta-learning gene installed."""
    result = await db.execute(
        select(InstanceGene)
        .join(Gene, InstanceGene.gene_id == Gene.id)
        .where(
            InstanceGene.instance_id == instance_id,
            Gene.slug == "meta-learning",
            InstanceGene.status == InstanceGeneStatus.installed,
            not_deleted(InstanceGene),
        )
    )
    return result.scalar_one_or_none() is not None


async def install_gene(
    db: AsyncSession,
    instance_id: str,
    gene_slug: str,
    genome_id: str | None = None,
) -> dict:
    from app.api.workspaces import broadcast_event
    from app.services.instance_service import get_instance, restart_instance

    instance = await get_instance(instance_id, db)
    gene = await get_gene_by_slug(db, gene_slug)
    if not gene:
        raise AppException(404, f"基因 '{gene_slug}' 不存在")

    existing = await db.execute(
        select(InstanceGene).where(
            InstanceGene.instance_id == instance_id,
            InstanceGene.gene_id == gene.id,
            not_deleted(InstanceGene),
        )
    )
    if existing.scalar_one_or_none():
        raise AppException(409, f"基因 '{gene_slug}' 已安装")

    has_learning = await _has_meta_learning(db, instance_id)

    ig = InstanceGene(
        instance_id=instance_id,
        gene_id=gene.id,
        genome_id=genome_id,
        status=InstanceGeneStatus.learning if has_learning else InstanceGeneStatus.installing,
        installed_version=gene.version,
    )
    db.add(ig)
    gene.install_count += 1
    await db.commit()
    await db.refresh(ig)

    workspace_id = _get_workspace_id_for_instance(instance)

    if has_learning:
        if workspace_id:
            broadcast_event(workspace_id, "gene:learn_start", {
                "instance_id": instance_id,
                "gene_slug": gene_slug,
            })
        asyncio.create_task(
            _send_learning_task(db, instance, gene, ig)
        )
    else:
        if workspace_id:
            broadcast_event(workspace_id, "gene:install_start", {
                "instance_id": instance_id,
                "gene_slug": gene_slug,
            })
        asyncio.create_task(
            _direct_install(db, instance, gene, ig, workspace_id)
        )

    return {
        "id": ig.id,
        "gene_slug": gene_slug,
        "status": ig.status,
        "method": "learning" if has_learning else "direct",
    }


def _get_workspace_id_for_instance(instance: Instance) -> str | None:
    """Workspace ID from instance's advanced_config or None."""
    if instance.advanced_config:
        try:
            cfg = json.loads(instance.advanced_config)
            return cfg.get("workspace_id")
        except (json.JSONDecodeError, TypeError):
            pass
    return None


async def _direct_install(
    db: AsyncSession,
    instance: Instance,
    gene: Gene,
    ig: InstanceGene,
    workspace_id: str | None,
) -> None:
    from app.api.workspaces import broadcast_event
    from app.services.instance_service import restart_instance

    try:
        manifest = _json_loads(gene.manifest) or {}
        skill = manifest.get("skill", {})

        async with nfs_mount(instance, db) as mount_path:
            skill_name = skill.get("name", gene.slug)
            skill_content = skill.get("content", "")
            _write_skill_file(mount_path, skill_name, skill_content)

            openclaw_config = manifest.get("openclaw_config")
            if openclaw_config:
                _merge_openclaw_config(mount_path, openclaw_config)

        ig.status = InstanceGeneStatus.installed
        ig.installed_at = datetime.now(timezone.utc)
        ig.config_snapshot = _json_dumps(manifest.get("openclaw_config"))
        await db.commit()

        await restart_instance(instance.id, db)

        if workspace_id:
            broadcast_event(workspace_id, "gene:installed", {
                "instance_id": instance.id,
                "gene_slug": gene.slug,
                "method": "direct",
            })
    except Exception as e:
        logger.error("Direct install failed for gene %s on %s: %s", gene.slug, instance.id, e)
        ig.status = InstanceGeneStatus.failed
        await db.commit()


async def _send_learning_task(
    db: AsyncSession,
    instance: Instance,
    gene: Gene,
    ig: InstanceGene,
) -> None:
    """Send learning task to Learning Channel Plugin via webhook."""
    manifest = _json_loads(gene.manifest) or {}
    skill = manifest.get("skill", {})
    learning = manifest.get("learning")

    from app.core.config import settings

    callback_base = getattr(settings, "CLAWBUDDY_WEBHOOK_BASE_URL", "") or ""
    callback_url = f"{callback_base}/api/v1/genes/learning-callback"

    payload = {
        "mode": "learn",
        "task_id": ig.id,
        "gene_slug": gene.slug,
        "gene_content": skill.get("content", ""),
        "learning": learning,
        "callback_url": callback_url,
    }

    plugin_url = _get_learning_plugin_url(instance)
    if not plugin_url:
        logger.warning("No learning plugin URL for instance %s, falling back to direct install", instance.id)
        workspace_id = _get_workspace_id_for_instance(instance)
        await _direct_install(db, instance, gene, ig, workspace_id)
        return

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{plugin_url}/webhook", json=payload)
            resp.raise_for_status()
        logger.info("Learning task sent for gene %s on %s", gene.slug, instance.id)
    except Exception as e:
        logger.error("Failed to send learning task: %s, falling back to direct install", e)
        workspace_id = _get_workspace_id_for_instance(instance)
        await _direct_install(db, instance, gene, ig, workspace_id)


def _get_learning_plugin_url(instance: Instance) -> str | None:
    domain = instance.ingress_domain
    if not domain:
        return None
    base = domain.rstrip("/")
    if not base.startswith("http"):
        base = f"https://{base}"
    return f"{base}/extensions/learning"


def _write_skill_file(mount_path: Path, skill_name: str, content: str) -> None:
    skill_dir = mount_path / SKILLS_DIR_REL / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(content, encoding="utf-8")


def _merge_openclaw_config(mount_path: Path, patch: dict) -> None:
    import re

    config_path = mount_path / OPENCLAW_CONFIG_REL
    existing: dict = {}
    if config_path.exists():
        raw = config_path.read_text(encoding="utf-8")
        raw = re.sub(r'//[^\n]*', '', raw)
        raw = re.sub(r'/\*.*?\*/', '', raw, flags=re.DOTALL)
        raw = re.sub(r',\s*([}\]])', r'\1', raw)
        try:
            existing = json.loads(raw)
        except json.JSONDecodeError:
            existing = {}

    for key, val in patch.items():
        if isinstance(val, dict) and isinstance(existing.get(key), dict):
            existing[key].update(val)
        else:
            existing[key] = val

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _remove_skill_file(mount_path: Path, skill_name: str) -> None:
    import shutil

    skill_dir = mount_path / SKILLS_DIR_REL / skill_name
    if skill_dir.exists():
        shutil.rmtree(skill_dir)


# ── Learning callback handler ────────────────────


async def handle_learning_callback(
    db: AsyncSession, payload: LearningCallbackPayload
) -> dict:
    from app.api.workspaces import broadcast_event
    from app.services.instance_service import get_instance, restart_instance

    ig = await db.execute(
        select(InstanceGene).where(InstanceGene.id == payload.task_id, not_deleted(InstanceGene))
    )
    ig_obj = ig.scalar_one_or_none()
    if not ig_obj:
        raise AppException(404, f"学习任务 '{payload.task_id}' 不存在")

    instance = await get_instance(ig_obj.instance_id, db)
    gene = await db.execute(select(Gene).where(Gene.id == ig_obj.gene_id))
    gene_obj = gene.scalar_one_or_none()
    if not gene_obj:
        raise AppException(404, "基因不存在")

    workspace_id = _get_workspace_id_for_instance(instance)

    if workspace_id:
        broadcast_event(workspace_id, "gene:learn_decided", {
            "instance_id": instance.id,
            "gene_slug": gene_obj.slug,
            "decision": payload.decision,
            "reason": payload.reason,
        })

    if payload.decision == "direct_install":
        manifest = _json_loads(gene_obj.manifest) or {}
        skill = manifest.get("skill", {})
        async with nfs_mount(instance, db) as mount_path:
            _write_skill_file(mount_path, skill.get("name", gene_obj.slug), skill.get("content", ""))
            openclaw_config = manifest.get("openclaw_config")
            if openclaw_config:
                _merge_openclaw_config(mount_path, openclaw_config)

        ig_obj.status = InstanceGeneStatus.installed
        ig_obj.installed_at = datetime.now(timezone.utc)

    elif payload.decision == "learned":
        content = payload.content or ""
        async with nfs_mount(instance, db) as mount_path:
            _write_skill_file(mount_path, gene_obj.slug, content)
            manifest = _json_loads(gene_obj.manifest) or {}
            openclaw_config = manifest.get("openclaw_config")
            if openclaw_config:
                _merge_openclaw_config(mount_path, openclaw_config)

        ig_obj.status = InstanceGeneStatus.installed
        ig_obj.installed_at = datetime.now(timezone.utc)
        ig_obj.learning_output = content
        ig_obj.agent_self_eval = payload.self_eval

    elif payload.decision == "failed":
        ig_obj.status = InstanceGeneStatus.learn_failed
        if workspace_id:
            broadcast_event(workspace_id, "gene:learn_failed", {
                "instance_id": instance.id,
                "gene_slug": gene_obj.slug,
                "reason": payload.reason,
            })
        await db.commit()
        return {"status": "learn_failed"}

    else:
        raise AppException(400, f"未知决策: {payload.decision}")

    await db.commit()
    await restart_instance(instance.id, db)

    if workspace_id:
        broadcast_event(workspace_id, "gene:installed", {
            "instance_id": instance.id,
            "gene_slug": gene_obj.slug,
            "method": payload.decision,
        })

    return {"status": "installed", "method": payload.decision}


# ── Apply Genome ─────────────────────────────────


async def apply_genome(db: AsyncSession, instance_id: str, genome_id: str) -> dict:
    genome_result = await db.execute(
        select(Genome).where(Genome.id == genome_id, not_deleted(Genome))
    )
    genome = genome_result.scalar_one_or_none()
    if not genome:
        raise AppException(404, "基因组不存在")

    gene_slugs = _json_loads(genome.gene_slugs) or []
    if not gene_slugs:
        return {"installed": [], "skipped": []}

    installed_q = await db.execute(
        select(Gene.slug)
        .join(InstanceGene, InstanceGene.gene_id == Gene.id)
        .where(InstanceGene.instance_id == instance_id, not_deleted(InstanceGene))
    )
    already_installed = {row[0] for row in installed_q}

    results = {"installed": [], "skipped": []}
    for slug in gene_slugs:
        if slug in already_installed:
            results["skipped"].append(slug)
            continue
        try:
            await install_gene(db, instance_id, slug, genome_id=genome.id)
            results["installed"].append(slug)
        except AppException:
            results["skipped"].append(slug)

    genome.install_count += 1
    await db.commit()
    return results


# ═══════════════════════════════════════════════════
#  Rating + Effectiveness
# ═══════════════════════════════════════════════════


async def rate_gene(db: AsyncSession, gene_id: str, user_id: str, rating: int, comment: str | None = None) -> dict:
    existing = await db.execute(
        select(GeneRating).where(
            GeneRating.gene_id == gene_id,
            GeneRating.user_id == user_id,
            not_deleted(GeneRating),
        )
    )
    obj = existing.scalar_one_or_none()
    if obj:
        obj.rating = rating
        obj.comment = comment
    else:
        obj = GeneRating(gene_id=gene_id, user_id=user_id, rating=rating, comment=comment)
        db.add(obj)

    await db.commit()
    await _recalc_gene_rating(db, gene_id)
    return {"rating": rating}


async def rate_genome(db: AsyncSession, genome_id: str, user_id: str, rating: int, comment: str | None = None) -> dict:
    existing = await db.execute(
        select(GenomeRating).where(
            GenomeRating.genome_id == genome_id,
            GenomeRating.user_id == user_id,
            not_deleted(GenomeRating),
        )
    )
    obj = existing.scalar_one_or_none()
    if obj:
        obj.rating = rating
        obj.comment = comment
    else:
        obj = GenomeRating(genome_id=genome_id, user_id=user_id, rating=rating, comment=comment)
        db.add(obj)

    await db.commit()
    await _recalc_genome_rating(db, genome_id)
    return {"rating": rating}


async def _recalc_gene_rating(db: AsyncSession, gene_id: str) -> None:
    result = await db.execute(
        select(func.avg(GeneRating.rating)).where(
            GeneRating.gene_id == gene_id, not_deleted(GeneRating)
        )
    )
    avg = result.scalar() or 0.0
    gene_result = await db.execute(select(Gene).where(Gene.id == gene_id))
    gene = gene_result.scalar_one_or_none()
    if gene:
        gene.avg_rating = round(float(avg), 2)
        await db.commit()
        await _recalc_effectiveness_score(db, gene_id)


async def _recalc_genome_rating(db: AsyncSession, genome_id: str) -> None:
    result = await db.execute(
        select(func.avg(GenomeRating.rating)).where(
            GenomeRating.genome_id == genome_id, not_deleted(GenomeRating)
        )
    )
    avg = result.scalar() or 0.0
    genome_result = await db.execute(select(Genome).where(Genome.id == genome_id))
    genome = genome_result.scalar_one_or_none()
    if genome:
        genome.avg_rating = round(float(avg), 2)
        await db.commit()


async def log_effectiveness(
    db: AsyncSession,
    instance_id: str,
    gene_id: str,
    metric_type: str,
    value: float = 1.0,
    context: str | None = None,
) -> dict:
    from app.api.workspaces import broadcast_event

    log = GeneEffectLog(
        instance_id=instance_id,
        gene_id=gene_id,
        metric_type=metric_type,
        value=value,
        context=context,
    )
    db.add(log)

    ig_result = await db.execute(
        select(InstanceGene).where(
            InstanceGene.instance_id == instance_id,
            InstanceGene.gene_id == gene_id,
            not_deleted(InstanceGene),
        )
    )
    ig = ig_result.scalar_one_or_none()
    if ig:
        ig.usage_count += 1

    await db.commit()
    await _recalc_effectiveness_score(db, gene_id)

    gene_result = await db.execute(select(Gene).where(Gene.id == gene_id))
    gene = gene_result.scalar_one_or_none()

    instance_result = await db.execute(select(Instance).where(Instance.id == instance_id))
    instance = instance_result.scalar_one_or_none()
    if instance and gene:
        workspace_id = _get_workspace_id_for_instance(instance)
        if workspace_id:
            broadcast_event(workspace_id, "gene:effect_logged", {
                "instance_id": instance_id,
                "gene_slug": gene.slug,
                "metric_type": metric_type,
            })

    return {"logged": True}


async def _recalc_effectiveness_score(db: AsyncSession, gene_id: str) -> None:
    """Recalculate effectiveness_score = user_rating 25% + agent_self_eval 25% + usage_effect 50%."""
    gene_result = await db.execute(select(Gene).where(Gene.id == gene_id))
    gene = gene_result.scalar_one_or_none()
    if not gene:
        return

    user_rating_norm = gene.avg_rating / 5.0 if gene.avg_rating else 0.0

    agent_eval_result = await db.execute(
        select(func.avg(InstanceGene.agent_self_eval)).where(
            InstanceGene.gene_id == gene_id,
            InstanceGene.agent_self_eval.isnot(None),
            not_deleted(InstanceGene),
        )
    )
    agent_eval = agent_eval_result.scalar() or 0.0

    pos_result = await db.execute(
        select(func.count()).where(
            GeneEffectLog.gene_id == gene_id,
            GeneEffectLog.metric_type == EffectMetricType.user_positive,
        )
    )
    pos_count = pos_result.scalar() or 0

    neg_result = await db.execute(
        select(func.count()).where(
            GeneEffectLog.gene_id == gene_id,
            GeneEffectLog.metric_type == EffectMetricType.user_negative,
        )
    )
    neg_count = neg_result.scalar() or 0

    total = pos_count + neg_count
    usage_effect = (pos_count / total) if total > 0 else 0.5

    score = user_rating_norm * 0.25 + float(agent_eval) * 0.25 + usage_effect * 0.50
    gene.effectiveness_score = round(score, 4)
    await db.commit()


# ═══════════════════════════════════════════════════
#  Evolution: Variant publish, Agent creation, Uninstall
# ═══════════════════════════════════════════════════


async def publish_variant(
    db: AsyncSession,
    instance_id: str,
    gene_id: str,
    variant_name: str | None = None,
    variant_slug: str | None = None,
) -> dict:
    from app.api.workspaces import broadcast_event

    ig_result = await db.execute(
        select(InstanceGene).where(
            InstanceGene.instance_id == instance_id,
            InstanceGene.gene_id == gene_id,
            not_deleted(InstanceGene),
        )
    )
    ig = ig_result.scalar_one_or_none()
    if not ig:
        raise AppException(404, "未找到已安装的基因")
    if not ig.learning_output:
        raise AppException(400, "该基因未通过深度学习，无个性化内容可发布")
    if ig.variant_published:
        raise AppException(409, "该基因的变体已发布")

    parent_gene = await db.execute(select(Gene).where(Gene.id == gene_id))
    parent = parent_gene.scalar_one_or_none()
    if not parent:
        raise AppException(404, "原始基因不存在")

    instance_result = await db.execute(select(Instance).where(Instance.id == instance_id))
    instance = instance_result.scalar_one_or_none()
    agent_display = instance.name if instance else instance_id[:8]

    slug = variant_slug or f"{parent.slug}-by-{agent_display.lower().replace(' ', '-')}"
    name = variant_name or f"{parent.name} (by {agent_display})"

    manifest = _json_loads(parent.manifest) or {}
    manifest["skill"] = {"name": slug, "content": ig.learning_output}

    variant = Gene(
        name=name,
        slug=slug,
        description=f"Agent {agent_display} 基于 {parent.name} 的进化版本",
        short_description=parent.short_description,
        category=parent.category,
        tags=parent.tags,
        source=GeneSource.agent,
        icon=parent.icon,
        version="1.0.0",
        manifest=_json_dumps(manifest),
        dependencies=parent.dependencies,
        synergies=parent.synergies,
        parent_gene_id=gene_id,
        created_by_instance_id=instance_id,
        is_published=False,
        review_status=GeneReviewStatus.pending_admin,
    )
    db.add(variant)

    ig.variant_published = True
    await db.commit()
    await db.refresh(variant)

    workspace_id = _get_workspace_id_for_instance(instance) if instance else None
    if workspace_id:
        broadcast_event(workspace_id, "gene:variant_published", {
            "instance_id": instance_id,
            "gene_slug": parent.slug,
            "variant_slug": slug,
        })

    return _gene_to_dict(variant)


async def trigger_gene_creation(
    db: AsyncSession,
    instance_id: str,
    creation_prompt: str | None = None,
) -> dict:
    from app.services.instance_service import get_instance

    instance = await get_instance(instance_id, db)

    from app.core.config import settings

    callback_base = getattr(settings, "CLAWBUDDY_WEBHOOK_BASE_URL", "") or ""
    callback_url = f"{callback_base}/api/v1/genes/creation-callback"

    import uuid

    task_id = str(uuid.uuid4())

    payload = {
        "mode": "create",
        "task_id": task_id,
        "creation_prompt": creation_prompt or "基于你的工作经验，总结出一个可复用的方法论并生成一个新的基因",
        "callback_url": callback_url,
    }

    plugin_url = _get_learning_plugin_url(instance)
    if not plugin_url:
        raise AppException(400, "实例未配置 Learning Plugin")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{plugin_url}/webhook", json=payload)
            resp.raise_for_status()
    except Exception as e:
        raise AppException(500, f"发送创造任务失败: {e}")

    return {"task_id": task_id, "status": "sent"}


async def handle_creation_callback(
    db: AsyncSession, payload: LearningCallbackPayload
) -> dict:
    from app.api.workspaces import broadcast_event

    if payload.decision != "created":
        return {"status": "ignored", "decision": payload.decision}

    meta = payload.meta or {}

    instance_result = await db.execute(
        select(Instance).where(Instance.id == payload.instance_id)
    )
    instance = instance_result.scalar_one_or_none()

    gene = Gene(
        name=meta.get("gene_name", f"agent-gene-{payload.task_id[:8]}"),
        slug=meta.get("gene_slug", f"agent-gene-{payload.task_id[:8]}"),
        description=meta.get("gene_description", ""),
        short_description=meta.get("gene_description", "")[:256] if meta.get("gene_description") else None,
        category=meta.get("suggested_category", ""),
        tags=_json_dumps(meta.get("suggested_tags", [])),
        source=GeneSource.agent,
        icon=meta.get("icon"),
        version="1.0.0",
        manifest=_json_dumps({
            "skill": {"name": meta.get("gene_slug", f"agent-gene-{payload.task_id[:8]}"), "content": payload.content or ""}
        }),
        created_by_instance_id=payload.instance_id,
        is_published=False,
        review_status=GeneReviewStatus.pending_owner,
    )
    db.add(gene)
    await db.commit()
    await db.refresh(gene)

    workspace_id = _get_workspace_id_for_instance(instance) if instance else None
    if workspace_id:
        broadcast_event(workspace_id, "gene:created", {
            "instance_id": payload.instance_id,
            "gene_slug": gene.slug,
            "gene_name": gene.name,
        })

    return {"status": "created", "gene_id": gene.id, "slug": gene.slug}


async def review_gene(db: AsyncSession, gene_id: str, action: str, reason: str | None = None) -> dict:
    result = await db.execute(select(Gene).where(Gene.id == gene_id, not_deleted(Gene)))
    gene = result.scalar_one_or_none()
    if not gene:
        raise AppException(404, "基因不存在")

    if action == "approve":
        if gene.review_status == GeneReviewStatus.pending_owner:
            gene.review_status = GeneReviewStatus.pending_admin
        elif gene.review_status == GeneReviewStatus.pending_admin:
            gene.review_status = GeneReviewStatus.approved
            gene.is_published = True
        else:
            raise AppException(400, f"当前审核状态 '{gene.review_status}' 不可审核通过")
    elif action == "reject":
        gene.review_status = GeneReviewStatus.rejected
        gene.is_published = False
    else:
        raise AppException(400, f"未知审核动作: {action}")

    await db.commit()
    return {"review_status": gene.review_status, "is_published": gene.is_published}


async def uninstall_gene(db: AsyncSession, instance_id: str, gene_id: str) -> dict:
    from app.services.instance_service import get_instance, restart_instance

    instance = await get_instance(instance_id, db)

    ig_result = await db.execute(
        select(InstanceGene).where(
            InstanceGene.instance_id == instance_id,
            InstanceGene.gene_id == gene_id,
            not_deleted(InstanceGene),
        )
    )
    ig = ig_result.scalar_one_or_none()
    if not ig:
        raise AppException(404, "未找到已安装的基因")

    gene_result = await db.execute(select(Gene).where(Gene.id == gene_id))
    gene = gene_result.scalar_one_or_none()

    ig.status = InstanceGeneStatus.uninstalling
    await db.commit()

    try:
        if gene:
            manifest = _json_loads(gene.manifest) or {}
            skill_name = manifest.get("skill", {}).get("name", gene.slug)
            async with nfs_mount(instance, db) as mount_path:
                _remove_skill_file(mount_path, skill_name)

        ig.soft_delete()
        if gene:
            gene.install_count = max(0, gene.install_count - 1)
        await db.commit()

        await restart_instance(instance.id, db)
    except Exception as e:
        logger.error("Uninstall failed for gene %s on %s: %s", gene_id, instance_id, e)
        ig.status = InstanceGeneStatus.installed
        await db.commit()
        raise AppException(500, f"卸载失败: {e}")

    return {"status": "uninstalled"}


# ═══════════════════════════════════════════════════
#  Admin
# ═══════════════════════════════════════════════════


async def get_gene_stats(db: AsyncSession) -> GeneStatsResponse:
    total = (await db.execute(
        select(func.count()).select_from(Gene).where(not_deleted(Gene))
    )).scalar() or 0

    total_installs = (await db.execute(
        select(func.coalesce(func.sum(Gene.install_count), 0)).where(not_deleted(Gene))
    )).scalar() or 0

    learning = (await db.execute(
        select(func.count()).select_from(InstanceGene).where(
            InstanceGene.status == InstanceGeneStatus.learning,
            not_deleted(InstanceGene),
        )
    )).scalar() or 0

    failed = (await db.execute(
        select(func.count()).select_from(InstanceGene).where(
            InstanceGene.status == InstanceGeneStatus.learn_failed,
            not_deleted(InstanceGene),
        )
    )).scalar() or 0

    agent_created = (await db.execute(
        select(func.count()).select_from(Gene).where(
            Gene.source == GeneSource.agent, not_deleted(Gene)
        )
    )).scalar() or 0

    return GeneStatsResponse(
        total_genes=total,
        total_installs=int(total_installs),
        learning_count=learning,
        failed_count=failed,
        agent_created_count=agent_created,
    )


async def get_pending_review_genes(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(Gene)
        .where(
            Gene.review_status.in_([GeneReviewStatus.pending_owner, GeneReviewStatus.pending_admin]),
            not_deleted(Gene),
        )
        .order_by(Gene.created_at.desc())
    )
    genes = result.scalars().all()
    return [_gene_to_dict(g) for g in genes]


async def get_gene_activity(db: AsyncSession, limit: int = 50) -> list[dict]:
    result = await db.execute(
        select(GeneEffectLog, Gene.slug, Gene.name)
        .join(Gene, GeneEffectLog.gene_id == Gene.id)
        .order_by(GeneEffectLog.created_at.desc())
        .limit(limit)
    )
    items = []
    for log, slug, name in result:
        items.append({
            "id": log.id,
            "instance_id": log.instance_id,
            "gene_slug": slug,
            "gene_name": name,
            "metric_type": log.metric_type,
            "value": log.value,
            "context": log.context,
            "created_at": log.created_at,
        })
    return items


async def get_gene_matrix(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(
            InstanceGene.instance_id,
            Gene.slug,
            InstanceGene.status,
        )
        .join(Gene, InstanceGene.gene_id == Gene.id)
        .where(not_deleted(InstanceGene))
        .order_by(InstanceGene.instance_id, Gene.slug)
    )
    return [
        {"instance_id": r[0], "gene_slug": r[1], "status": r[2]}
        for r in result
    ]


async def get_co_install_analysis(db: AsyncSession, min_count: int = 2) -> list[CoInstallPair]:
    ig1 = InstanceGene.__table__.alias("ig1")
    ig2 = InstanceGene.__table__.alias("ig2")
    g1 = Gene.__table__.alias("g1")
    g2 = Gene.__table__.alias("g2")

    q = (
        select(
            g1.c.slug.label("gene_a_slug"),
            g2.c.slug.label("gene_b_slug"),
            func.count().label("co_count"),
        )
        .select_from(ig1)
        .join(ig2, (ig1.c.instance_id == ig2.c.instance_id) & (ig1.c.gene_id < ig2.c.gene_id))
        .join(g1, ig1.c.gene_id == g1.c.id)
        .join(g2, ig2.c.gene_id == g2.c.id)
        .where(ig1.c.deleted_at.is_(None), ig2.c.deleted_at.is_(None))
        .group_by(g1.c.slug, g2.c.slug)
        .having(func.count() >= min_count)
        .order_by(func.count().desc())
    )
    result = await db.execute(q)
    return [
        CoInstallPair(gene_a_slug=r[0], gene_b_slug=r[1], co_install_count=r[2])
        for r in result
    ]
