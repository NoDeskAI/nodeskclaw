"""Gene Evolution Ecosystem service: CRUD, install/learn engine, rating, evolution."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Coroutine

import httpx
from sqlalchemy import Integer, Select, case, cast, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, BadRequestError, ConflictError, NotFoundError
from app.models.base import not_deleted
from app.models.gene import (
    EffectMetricType,
    EvolutionEvent,
    EvolutionEventType,
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
from app.models.instance import Instance, InstanceStatus
from app.schemas.gene import (
    CoInstallPair,
    GeneCreateRequest,
    GeneStatsResponse,
    GenomeCreateRequest,
    LearningCallbackPayload,
    TagStats,
    UpdateGeneRequest,
    UpdateGenomeRequest,
)
from app.services.nfs_mount import PodFS, remote_fs
from app.services.openclaw_session import (
    ensure_skills_discovery,
    inject_evolution_notification,
    invalidate_skill_snapshots,
)

OPENCLAW_CONFIG_REL = ".openclaw/openclaw.json"
SKILLS_DIR_REL = ".openclaw/skills"

logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task] = set()


def _fire_task(coro: Coroutine) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


@asynccontextmanager
async def _instance_pg_advisory_lock(instance_id: str):
    """PostgreSQL advisory lock scoped to an instance, for serializing NFS operations.

    Uses session-level pg_advisory_lock/pg_advisory_unlock on a dedicated connection
    so the lock is held across the entire async block regardless of transaction boundaries.
    """
    from app.core.deps import async_session_factory

    lock_key = hash(instance_id) % (2**31)
    async with async_session_factory() as lock_db:
        await lock_db.execute(text("SELECT pg_advisory_lock(:key)"), {"key": lock_key})
        try:
            yield
        finally:
            await lock_db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})


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


async def _record_evolution(
    db: AsyncSession,
    instance_id: str,
    event_type: EvolutionEventType,
    gene_name: str,
    gene_slug: str | None = None,
    gene_id: str | None = None,
    genome_id: str | None = None,
    details: dict | None = None,
) -> None:
    ev = EvolutionEvent(
        instance_id=instance_id,
        gene_id=gene_id,
        genome_id=genome_id,
        event_type=event_type.value,
        gene_name=gene_name,
        gene_slug=gene_slug,
        details=_json_dumps(details),
    )
    db.add(ev)


def _has_frontmatter(content: str) -> bool:
    """Check whether SKILL.md content begins with YAML front matter (``---``)."""
    return content.lstrip().startswith("---")


def _validate_skill_metadata(
    manifest: dict | None,
    short_description: str | None,
    description: str | None,
) -> None:
    """Reject gene creation when skill metadata is insufficient for OpenClaw discovery.

    OpenClaw requires YAML front matter (name + description) in SKILL.md.
    Either the skill content must already include front matter, or the gene
    must provide a description that _write_skill_file can use to generate it.
    """
    if not manifest or "skill" not in manifest:
        return
    skill = manifest["skill"]
    content = skill.get("content", "")
    if _has_frontmatter(content):
        return
    if not (short_description or description):
        raise BadRequestError(
            "带 skill 的基因必须提供 short_description 或 description"
            "（OpenClaw 需要 YAML front matter 中的 description 字段来发现 skill）",
        )


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


async def _enrich_genomes_tool_counts(db: AsyncSession, genome_dicts: list[dict]) -> list[dict]:
    all_slugs: set[str] = set()
    for gd in genome_dicts:
        all_slugs.update(gd.get("gene_slugs") or [])
    if not all_slugs:
        for gd in genome_dicts:
            gd["native_tool_count"] = 0
            gd["mcp_server_count"] = 0
        return genome_dicts

    result = await db.execute(
        select(Gene.slug, Gene.manifest).where(Gene.slug.in_(list(all_slugs)), not_deleted(Gene))
    )
    slug_tools: dict[str, tuple[int, int]] = {}
    for slug, manifest_raw in result.all():
        m = _json_loads(manifest_raw) if isinstance(manifest_raw, str) else (manifest_raw or {})
        ta = m.get("tool_allow", [])
        ms = m.get("mcp_servers", [])
        slug_tools[slug] = (
            len(ta) if isinstance(ta, list) else 0,
            len(ms) if isinstance(ms, list) else 0,
        )

    for gd in genome_dicts:
        native = 0
        mcp = 0
        for s in gd.get("gene_slugs") or []:
            counts = slug_tools.get(s, (0, 0))
            native += counts[0]
            mcp += counts[1]
        gd["native_tool_count"] = native
        gd["mcp_server_count"] = mcp
    return genome_dicts


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
        raise NotFoundError("基因不存在")
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
        raise ConflictError(f"基因 slug '{req.slug}' 已存在")

    _validate_skill_metadata(req.manifest, req.short_description, req.description)

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


async def get_gene_genomes(db: AsyncSession, gene_id: str) -> list[dict]:
    """返回包含该基因的所有基因组（通过 gene_slugs JSON 数组匹配）。"""
    gene = await db.execute(
        select(Gene).where(Gene.id == gene_id, not_deleted(Gene))
    )
    gene_obj = gene.scalar_one_or_none()
    if not gene_obj:
        return []

    result = await db.execute(
        select(Genome).where(not_deleted(Genome), Genome.is_published.is_(True))
    )
    matched = []
    for g in result.scalars().all():
        slugs = _json_loads(g.gene_slugs) or []
        if gene_obj.slug in slugs:
            matched.append(_genome_to_dict(g))
    return await _enrich_genomes_tool_counts(db, matched)


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
    items = await _enrich_genomes_tool_counts(db, [_genome_to_dict(g) for g in result.scalars().all()])
    return items, total


async def get_genome(db: AsyncSession, genome_id: str) -> dict:
    result = await db.execute(
        select(Genome).where(Genome.id == genome_id, not_deleted(Genome))
    )
    genome = result.scalar_one_or_none()
    if not genome:
        raise NotFoundError("基因组不存在")
    items = await _enrich_genomes_tool_counts(db, [_genome_to_dict(genome)])
    return items[0]


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
    return await _enrich_genomes_tool_counts(db, [_genome_to_dict(g) for g in result.scalars().all()])


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


async def get_gene_installed_instance_ids(db: AsyncSession, gene_id: str) -> list[str]:
    """Return instance IDs where this gene is currently installed."""
    result = await db.execute(
        select(InstanceGene.instance_id).where(
            InstanceGene.gene_id == gene_id,
            InstanceGene.status == InstanceGeneStatus.installed,
            not_deleted(InstanceGene),
        )
    )
    return [row[0] for row in result.all()]


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


async def _has_pending_learning(db: AsyncSession, instance_id: str, exclude_ig_id: str) -> bool:
    """Check if the instance still has other InstanceGene records in learning status."""
    result = await db.execute(
        select(InstanceGene.id).where(
            InstanceGene.instance_id == instance_id,
            InstanceGene.status == InstanceGeneStatus.learning,
            InstanceGene.id != exclude_ig_id,
            not_deleted(InstanceGene),
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _finish_learning_if_done(
    db: AsyncSession, instance_id: str, exclude_ig_id: str
) -> bool:
    """If no more genes are learning, restore instance status and return True (should restart)."""
    from app.services.instance_service import _broadcast_agent_status

    still_learning = await _has_pending_learning(db, instance_id, exclude_ig_id)
    if still_learning:
        return False

    instance = await db.get(Instance, instance_id)
    if instance and instance.status == InstanceStatus.learning:
        _broadcast_agent_status(instance.workspace_id, instance_id, "restarting")
    return True


async def install_gene(
    db: AsyncSession,
    instance_id: str,
    gene_slug: str,
    genome_id: str | None = None,
) -> dict:
    from app.api.workspaces import broadcast_event
    from app.services.instance_service import get_instance

    instance = await get_instance(instance_id, db)
    gene = await get_gene_by_slug(db, gene_slug)
    if not gene:
        raise NotFoundError(f"基因 '{gene_slug}' 不存在")

    result = await db.execute(
        select(InstanceGene).where(
            InstanceGene.instance_id == instance_id,
            InstanceGene.gene_id == gene.id,
            not_deleted(InstanceGene),
        )
    )
    existing_ig = result.scalar_one_or_none()
    if existing_ig:
        if existing_ig.status in (
            InstanceGeneStatus.installing,
            InstanceGeneStatus.learning,
            InstanceGeneStatus.failed,
            InstanceGeneStatus.learn_failed,
        ):
            existing_ig.soft_delete()
            await db.commit()
        else:
            raise ConflictError(f"基因 '{gene_slug}' 已学习")

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

    workspace_id = instance.workspace_id

    if has_learning:
        from app.services.instance_service import _broadcast_agent_status
        instance.status = InstanceStatus.learning
        await db.commit()
        _broadcast_agent_status(workspace_id, instance_id, "learning")
        if workspace_id:
            broadcast_event(workspace_id, "gene:learn_start", {
                "instance_id": instance_id,
                "gene_slug": gene_slug,
            })
        _fire_task(
            _send_learning_task(instance.id, gene.id, ig.id)
        )
    else:
        if workspace_id:
            broadcast_event(workspace_id, "gene:install_start", {
                "instance_id": instance_id,
                "gene_slug": gene_slug,
            })
        _fire_task(
            _direct_install(instance.id, gene.id, ig.id, workspace_id)
        )

    return {
        "id": ig.id,
        "gene_slug": gene_slug,
        "status": ig.status,
        "method": "learning" if has_learning else "direct",
    }


async def _inject_mcp_servers(
    db: AsyncSession, instance_id: str, gene_id: str, mcp_servers: list[dict],
) -> None:
    """Auto-inject MCP servers from gene manifest into instance_mcp_servers."""
    import uuid
    from app.models.instance_mcp_server import InstanceMcpServer

    for mcp_def in mcp_servers:
        name = mcp_def.get("name", "")
        if not name:
            continue
        existing = await db.execute(
            select(InstanceMcpServer).where(
                InstanceMcpServer.instance_id == instance_id,
                InstanceMcpServer.name == name,
                not_deleted(InstanceMcpServer),
            ).limit(1)
        )
        if existing.scalar_one_or_none():
            continue
        mcp = InstanceMcpServer(
            id=str(uuid.uuid4()),
            instance_id=instance_id,
            name=name,
            transport=mcp_def.get("transport", "stdio"),
            command=mcp_def.get("command"),
            url=mcp_def.get("url"),
            args=mcp_def.get("args"),
            env=mcp_def.get("env"),
            source="gene",
            source_gene_id=gene_id,
        )
        db.add(mcp)
    await db.flush()


async def _direct_install(
    instance_id: str,
    gene_id: str,
    ig_id: str,
    workspace_id: str | None,
) -> None:
    from app.api.workspaces import broadcast_event
    from app.core.deps import async_session_factory
    from app.services.instance_service import restart_instance

    async with _instance_pg_advisory_lock(instance_id):
        async with async_session_factory() as db:
            ig = await db.get(InstanceGene, ig_id)
            gene = await db.get(Gene, gene_id)
            instance = await db.get(Instance, instance_id)
            if not ig or not gene or not instance:
                logger.error("_direct_install: record missing ig=%s gene=%s inst=%s", ig_id, gene_id, instance_id)
                return

            try:
                manifest = _json_loads(gene.manifest) or {}
                skill = manifest.get("skill", {})

                async with remote_fs(instance, db) as fs:
                    skill_name = skill.get("name", gene.slug)
                    skill_content = skill.get("content", "")
                    await _write_skill_file(fs, skill_name, skill_content, gene.short_description or gene.description or "")
                    await ensure_skills_discovery(fs)

                    await _apply_engineering_actions(fs, manifest)

                    await invalidate_skill_snapshots(fs)
                    await inject_evolution_notification(fs, skill_name, "installed")

                ig.status = InstanceGeneStatus.installed
                ig.installed_at = datetime.now(timezone.utc)
                ig.config_snapshot = _json_dumps(manifest.get("openclaw_config"))
                await _record_evolution(
                    db, instance_id, EvolutionEventType.learned, gene.name,
                    gene_slug=gene.slug, gene_id=gene_id,
                    details={"version": gene.version, "learning_type": "direct"},
                )
                await db.commit()

                should_restart = await _finish_learning_if_done(db, instance_id, ig_id)
                if should_restart:
                    await restart_instance(instance.id, db)

                if workspace_id:
                    broadcast_event(workspace_id, "gene:installed", {
                        "instance_id": instance.id,
                        "gene_slug": gene.slug,
                        "method": "direct",
                    })
            except Exception as e:
                logger.error("Direct install failed for gene %s on %s: %s", gene.slug, instance.id, e)
                try:
                    ig.status = InstanceGeneStatus.failed
                    await db.commit()
                except Exception:
                    logger.error("Failed to mark gene install as failed for ig=%s", ig_id)


async def _send_learning_task(
    instance_id: str,
    gene_id: str,
    ig_id: str,
) -> None:
    """Send learning task to Learning Channel Plugin via webhook."""
    from app.core.deps import async_session_factory

    async with async_session_factory() as db:
        ig = await db.get(InstanceGene, ig_id)
        gene = await db.get(Gene, gene_id)
        instance = await db.get(Instance, instance_id)
        if not ig or not gene or not instance:
            logger.error("_send_learning_task: record missing ig=%s gene=%s inst=%s", ig_id, gene_id, instance_id)
            return

        manifest = _json_loads(gene.manifest) or {}
        skill = manifest.get("skill", {})
        learning = manifest.get("learning")

        from app.core.config import settings

        callback_base = getattr(settings, "NODESKCLAW_WEBHOOK_BASE_URL", "") or ""
        callback_url = f"{callback_base}/api/v1/genes/learning-callback"

        gene_content = skill.get("content", "")
        force_deep = not _has_frontmatter(gene_content)

        payload: dict = {
            "mode": "learn",
            "task_id": ig.id,
            "gene_slug": gene.slug,
            "gene_content": gene_content,
            "learning": learning,
            "callback_url": callback_url,
            "force_deep_learn": force_deep,
            "gene_meta": {
                "name": gene.name,
                "description": gene.short_description or gene.description or "",
                "category": gene.category or "",
            },
        }

        if force_deep:
            ig.config_snapshot = _json_dumps({"force_deep_learn": True})
            await db.commit()

        plugin_url = _get_learning_plugin_url(instance)
        if not plugin_url:
            logger.warning("No learning plugin URL for instance %s, falling back to direct install", instance.id)
            await _direct_install(instance.id, gene.id, ig.id, instance.workspace_id)
            return

        try:
            async with httpx.AsyncClient(
                transport=httpx.AsyncHTTPTransport(verify=False, local_address="0.0.0.0"),
                timeout=30,
            ) as client:
                resp = await client.post(f"{plugin_url}/webhook", json=payload)
                resp.raise_for_status()
            logger.info("Learning task sent for gene %s on %s", gene.slug, instance.id)
        except Exception as e:
            logger.error("Failed to send learning task: %s, falling back to direct install", e)
            await _direct_install(instance.id, gene.id, ig.id, instance.workspace_id)


def _get_learning_plugin_url(instance: Instance) -> str | None:
    domain = instance.ingress_domain
    if not domain:
        return None
    base = domain.rstrip("/")
    if not base.startswith("http"):
        base = f"https://{base}"
    return f"{base}/extensions/learning"


async def _write_skill_file(
    fs: PodFS,
    skill_name: str,
    content: str,
    description: str = "",
) -> None:
    """Write SKILL.md with YAML front matter required by OpenClaw."""
    if not content.lstrip().startswith("---"):
        desc = description or f"Skill: {skill_name}"
        front_matter = f"---\nname: {skill_name}\ndescription: {desc}\n---\n\n"
        content = front_matter + content

    await fs.mkdir(f"{SKILLS_DIR_REL}/{skill_name}")
    await fs.write_text(f"{SKILLS_DIR_REL}/{skill_name}/SKILL.md", content)


async def _merge_openclaw_config(fs: PodFS, patch: dict) -> None:
    raw = await fs.read_text(OPENCLAW_CONFIG_REL)
    existing: dict = {}
    if raw is not None:
        try:
            existing = json.loads(raw)
        except json.JSONDecodeError:
            existing = {}

    for key, val in patch.items():
        if isinstance(val, dict) and isinstance(existing.get(key), dict):
            existing[key].update(val)
        else:
            existing[key] = val

    await fs.write_text(
        OPENCLAW_CONFIG_REL,
        json.dumps(existing, indent=2, ensure_ascii=False),
    )


async def _append_tool_allow(fs: PodFS, tool_names: list[str]) -> None:
    """Deduplicate-append tool names to openclaw.json tools.allow array."""
    raw = await fs.read_text(OPENCLAW_CONFIG_REL)
    existing: dict = {}
    if raw is not None:
        try:
            existing = json.loads(raw)
        except json.JSONDecodeError:
            existing = {}

    tools = existing.setdefault("tools", {})
    allow = tools.get("allow", [])
    if not isinstance(allow, list):
        allow = []
    existing_set = set(allow)
    for name in tool_names:
        if name not in existing_set:
            allow.append(name)
            existing_set.add(name)
    tools["allow"] = allow

    await fs.write_text(OPENCLAW_CONFIG_REL, json.dumps(existing, indent=2, ensure_ascii=False))


async def _apply_engineering_actions(fs: PodFS, manifest: dict) -> None:
    """Execute all engineering actions from a gene manifest."""
    openclaw_config = manifest.get("openclaw_config")
    if openclaw_config:
        await _merge_openclaw_config(fs, openclaw_config)

    tool_allow = manifest.get("tool_allow")
    if tool_allow and isinstance(tool_allow, list):
        await _append_tool_allow(fs, tool_allow)


async def _remove_skill_file(fs: PodFS, skill_name: str) -> None:
    await fs.remove(f"{SKILLS_DIR_REL}/{skill_name}")




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
        raise NotFoundError(f"学习任务 '{payload.task_id}' 不存在")

    instance = await get_instance(ig_obj.instance_id, db)
    gene = await db.execute(select(Gene).where(Gene.id == ig_obj.gene_id))
    gene_obj = gene.scalar_one_or_none()
    if not gene_obj:
        raise NotFoundError("基因不存在")

    workspace_id = instance.workspace_id

    if workspace_id:
        broadcast_event(workspace_id, "gene:learn_decided", {
            "instance_id": instance.id,
            "gene_slug": gene_obj.slug,
            "decision": payload.decision,
            "reason": payload.reason,
        })

    snapshot = _json_loads(ig_obj.config_snapshot) if ig_obj.config_snapshot else {}
    was_forced = snapshot.get("force_deep_learn", False) if isinstance(snapshot, dict) else False

    if payload.decision == "direct_install":
        if was_forced:
            logger.warning(
                "Agent chose direct_install despite force_deep_learn for gene %s on %s, "
                "falling back to auto-generated frontmatter install",
                gene_obj.slug, instance.id,
            )
        manifest = _json_loads(gene_obj.manifest) or {}
        skill = manifest.get("skill", {})
        gene_desc = gene_obj.short_description or gene_obj.description or ""
        skill_name = skill.get("name", gene_obj.slug)
        async with remote_fs(instance, db) as fs:
            await _write_skill_file(fs, skill_name, skill.get("content", ""), gene_desc)
            await _apply_engineering_actions(fs, manifest)
            await invalidate_skill_snapshots(fs)
            await inject_evolution_notification(fs, skill_name, "installed")

        ig_obj.status = InstanceGeneStatus.installed
        ig_obj.installed_at = datetime.now(timezone.utc)

    elif payload.decision == "learned":
        content = payload.content or ""
        gene_desc = gene_obj.short_description or gene_obj.description or ""
        async with remote_fs(instance, db) as fs:
            await _write_skill_file(fs, gene_obj.slug, content, gene_desc)
            manifest = _json_loads(gene_obj.manifest) or {}
            await _apply_engineering_actions(fs, manifest)
            await invalidate_skill_snapshots(fs)
            await inject_evolution_notification(fs, gene_obj.slug, "installed")

        ig_obj.status = InstanceGeneStatus.installed
        ig_obj.installed_at = datetime.now(timezone.utc)
        ig_obj.learning_output = content
        ig_obj.agent_self_eval = payload.self_eval

    elif payload.decision == "failed":
        ig_obj.status = InstanceGeneStatus.learn_failed
        await _record_evolution(
            db, instance.id, EvolutionEventType.learn_failed, gene_obj.name,
            gene_slug=gene_obj.slug, gene_id=gene_obj.id,
            details={"reason": payload.reason},
        )
        if workspace_id:
            broadcast_event(workspace_id, "gene:learn_failed", {
                "instance_id": instance.id,
                "gene_slug": gene_obj.slug,
                "reason": payload.reason,
            })
        await db.commit()

        should_restart = await _finish_learning_if_done(db, instance.id, ig_obj.id)
        if should_restart:
            await restart_instance(instance.id, db)

        return {"status": "learn_failed"}

    else:
        raise BadRequestError(f"未知决策: {payload.decision}")

    await _record_evolution(
        db, instance.id, EvolutionEventType.learned, gene_obj.name,
        gene_slug=gene_obj.slug, gene_id=gene_obj.id,
        details={"version": gene_obj.version, "learning_type": payload.decision},
    )
    await db.commit()

    should_restart = await _finish_learning_if_done(db, instance.id, ig_obj.id)
    if should_restart:
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
        raise NotFoundError("基因组不存在")

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
    await _record_evolution(
        db, instance_id, EvolutionEventType.genome_applied, genome.name,
        genome_id=genome.id,
        details={"genome_slug": genome.slug, "gene_slugs": gene_slugs, "installed": results["installed"], "skipped": results["skipped"]},
    )
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
        workspace_id = instance.workspace_id
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
        raise NotFoundError("未找到已学习的基因")
    if not ig.learning_output:
        raise BadRequestError("该基因未通过深度学习，无个性化内容可发布")
    if ig.variant_published:
        raise ConflictError("该基因的变体已发布")

    parent_gene = await db.execute(select(Gene).where(Gene.id == gene_id))
    parent = parent_gene.scalar_one_or_none()
    if not parent:
        raise NotFoundError("原始基因不存在")

    instance_result = await db.execute(select(Instance).where(Instance.id == instance_id))
    instance = instance_result.scalar_one_or_none()
    agent_display = instance.name if instance else instance_id[:8]

    slug = variant_slug or f"{parent.slug}-by-{agent_display.lower().replace(' ', '-')}"
    name = variant_name or f"{parent.name} (by {agent_display})"

    manifest = _json_loads(parent.manifest) or {}
    manifest["skill"] = {"name": slug, "content": ig.learning_output}

    variant_desc = f"Agent {agent_display} 基于 {parent.name} 的进化版本"
    _validate_skill_metadata(manifest, parent.short_description, variant_desc)

    variant = Gene(
        name=name,
        slug=slug,
        description=variant_desc,
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
    await _record_evolution(
        db, instance_id, EvolutionEventType.variant_published, parent.name,
        gene_slug=parent.slug, gene_id=gene_id,
        details={"variant_gene_id": variant.id, "variant_slug": slug},
    )
    await db.commit()
    await db.refresh(variant)

    workspace_id = instance.workspace_id if instance else None
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

    callback_base = getattr(settings, "NODESKCLAW_WEBHOOK_BASE_URL", "") or ""
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
        raise BadRequestError("实例未配置 Learning Plugin")

    try:
        async with httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(verify=False, local_address="0.0.0.0"),
            timeout=30,
        ) as client:
            resp = await client.post(f"{plugin_url}/webhook", json=payload)
            resp.raise_for_status()
    except Exception as e:
        raise AppException(code=50001, message=f"发送创造任务失败: {e}", status_code=500)

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

    gene_desc = meta.get("gene_description", "")
    gene_short_desc = gene_desc[:256] if gene_desc else None
    gene_manifest = {
        "skill": {"name": meta.get("gene_slug", f"agent-gene-{payload.task_id[:8]}"), "content": payload.content or ""}
    }

    _validate_skill_metadata(gene_manifest, gene_short_desc, gene_desc or None)

    gene = Gene(
        name=meta.get("gene_name", f"agent-gene-{payload.task_id[:8]}"),
        slug=meta.get("gene_slug", f"agent-gene-{payload.task_id[:8]}"),
        description=gene_desc,
        short_description=gene_short_desc,
        category=meta.get("suggested_category", ""),
        tags=_json_dumps(meta.get("suggested_tags", [])),
        source=GeneSource.agent,
        icon=meta.get("icon"),
        version="1.0.0",
        manifest=_json_dumps(gene_manifest),
        created_by_instance_id=payload.instance_id,
        is_published=False,
        review_status=GeneReviewStatus.pending_owner,
    )
    db.add(gene)
    await db.commit()
    await db.refresh(gene)

    workspace_id = instance.workspace_id if instance else None
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
        raise NotFoundError("基因不存在")

    if action == "approve":
        if gene.review_status == GeneReviewStatus.pending_owner:
            gene.review_status = GeneReviewStatus.pending_admin
        elif gene.review_status == GeneReviewStatus.pending_admin:
            gene.review_status = GeneReviewStatus.approved
            gene.is_published = True
        else:
            raise BadRequestError(f"当前审核状态 '{gene.review_status}' 不可审核通过")
    elif action == "reject":
        gene.review_status = GeneReviewStatus.rejected
        gene.is_published = False
    else:
        raise BadRequestError(f"未知审核动作: {action}")

    await db.commit()
    return {"review_status": gene.review_status, "is_published": gene.is_published}


async def uninstall_gene(db: AsyncSession, instance_id: str, gene_id: str) -> dict:
    from app.services.instance_service import get_instance

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
        raise NotFoundError("未找到已学习的基因")

    has_learning = await _has_meta_learning(db, instance_id)

    if has_learning:
        ig.status = InstanceGeneStatus.forgetting
        await db.commit()
        _fire_task(_send_forgetting_task(instance_id, gene_id, ig.id))
        return {"status": "forgetting", "method": "deep"}
    else:
        ig.status = InstanceGeneStatus.uninstalling
        await db.commit()
        _fire_task(_direct_uninstall(instance_id, gene_id, ig.id))
        return {"status": "uninstalling", "method": "direct"}


async def _direct_uninstall(
    instance_id: str,
    gene_id: str,
    ig_id: str,
) -> None:
    """Remove skill file and soft-delete InstanceGene without Agent involvement."""
    from app.core.deps import async_session_factory
    from app.services.instance_service import restart_instance

    async with _instance_pg_advisory_lock(instance_id):
        async with async_session_factory() as db:
            ig = await db.get(InstanceGene, ig_id)
            gene = await db.get(Gene, gene_id)
            instance = await db.get(Instance, instance_id)
            if not ig or not instance:
                logger.error("_direct_uninstall: record missing ig=%s inst=%s", ig_id, instance_id)
                return

            try:
                if gene:
                    manifest = _json_loads(gene.manifest) or {}
                    skill_name = manifest.get("skill", {}).get("name", gene.slug)
                    async with remote_fs(instance, db) as fs:
                        await _remove_skill_file(fs, skill_name)
                        await ensure_skills_discovery(fs)
                        await invalidate_skill_snapshots(fs)
                        await inject_evolution_notification(fs, skill_name, "uninstalled")

                ig.soft_delete()
                if gene:
                    gene.install_count = max(0, gene.install_count - 1)
                await _record_evolution(
                    db, instance_id, EvolutionEventType.forgotten,
                    gene.name if gene else "unknown",
                    gene_slug=gene.slug if gene else None,
                    gene_id=gene_id,
                    details={"version": ig.installed_version, "usage_count": ig.usage_count, "method": "direct"},
                )
                await db.commit()

                await restart_instance(instance.id, db)
                logger.info("Direct uninstall completed for gene %s on %s", gene_id, instance_id)
            except Exception as e:
                logger.error("Direct uninstall failed for gene %s on %s: %s", gene_id, instance_id, e)
                ig.status = InstanceGeneStatus.installed
                await db.commit()


async def _send_forgetting_task(
    instance_id: str,
    gene_id: str,
    ig_id: str,
) -> None:
    """Send forgetting task to Learning Channel Plugin via webhook."""
    from app.core.deps import async_session_factory

    async with async_session_factory() as db:
        ig = await db.get(InstanceGene, ig_id)
        gene = await db.get(Gene, gene_id)
        instance = await db.get(Instance, instance_id)
        if not ig or not gene or not instance:
            logger.error("_send_forgetting_task: record missing ig=%s gene=%s inst=%s", ig_id, gene_id, instance_id)
            return

        manifest = _json_loads(gene.manifest) or {}
        skill_content = manifest.get("skill", {}).get("content", "")

        from app.core.config import settings

        callback_base = getattr(settings, "NODESKCLAW_WEBHOOK_BASE_URL", "") or ""
        callback_url = f"{callback_base}/api/v1/genes/forgetting-callback"

        payload = {
            "mode": "forget",
            "task_id": ig.id,
            "gene_slug": gene.slug,
            "gene_content": skill_content,
            "learning_output": ig.learning_output or "",
            "usage_count": ig.usage_count,
            "callback_url": callback_url,
        }

        plugin_url = _get_learning_plugin_url(instance)
        if not plugin_url:
            logger.warning("No learning plugin URL for instance %s, falling back to direct uninstall", instance.id)
            await _direct_uninstall(instance.id, gene.id, ig.id)
            return

        try:
            async with httpx.AsyncClient(
                transport=httpx.AsyncHTTPTransport(verify=False, local_address="0.0.0.0"),
                timeout=30,
            ) as client:
                resp = await client.post(f"{plugin_url}/webhook", json=payload)
                resp.raise_for_status()
            logger.info("Forgetting task sent for gene %s on %s", gene.slug, instance.id)
        except Exception as e:
            logger.error("Failed to send forgetting task: %s, falling back to direct uninstall", e)
            await _direct_uninstall(instance.id, gene.id, ig.id)


# ── Forgetting callback handler ──────────────────


async def handle_forgetting_callback(
    db: AsyncSession, payload: LearningCallbackPayload
) -> dict:
    from app.api.workspaces import broadcast_event
    from app.services.instance_service import get_instance, restart_instance

    ig = await db.get(InstanceGene, payload.task_id)
    if not ig:
        raise NotFoundError(f"InstanceGene not found: {payload.task_id}")

    instance = await get_instance(ig.instance_id, db)
    gene_result = await db.execute(select(Gene).where(Gene.id == ig.gene_id))
    gene = gene_result.scalar_one_or_none()

    workspace_id = instance.workspace_id

    gene_name = gene.name if gene else "unknown"
    gene_slug = gene.slug if gene else None

    if payload.decision == "forget_failed":
        ig.status = InstanceGeneStatus.forget_failed
        await _record_evolution(
            db, ig.instance_id, EvolutionEventType.forget_failed, gene_name,
            gene_slug=gene_slug, gene_id=ig.gene_id,
            details={"reason": payload.reason},
        )
        await db.commit()
        if workspace_id:
            await broadcast_event(workspace_id, "gene:forget_failed", {
                "instance_id": ig.instance_id,
                "gene_id": ig.gene_id,
                "reason": payload.reason,
            })
        return {"status": "forget_failed"}

    if payload.decision == "simplified" and gene:
        manifest = _json_loads(gene.manifest) or {}
        skill_name = manifest.get("skill", {}).get("name", gene.slug)
        content = payload.content or ""
        async with remote_fs(instance, db) as fs:
            await _write_skill_file(fs, skill_name, content, gene.short_description or "")
            await invalidate_skill_snapshots(fs)
            await inject_evolution_notification(fs, skill_name, "uninstalled")

        ig.status = InstanceGeneStatus.simplified
        await _record_evolution(
            db, ig.instance_id, EvolutionEventType.simplified, gene_name,
            gene_slug=gene_slug, gene_id=ig.gene_id,
            details={
                "version": ig.installed_version,
                "usage_count": ig.usage_count,
                "simplified_reason": payload.reason,
                "method": "deep",
            },
        )
        await db.commit()

        should_restart = await _finish_learning_if_done(db, instance.id, ig.id)
        if should_restart:
            await restart_instance(instance.id, db)

        if workspace_id:
            await broadcast_event(workspace_id, "gene:simplified", {
                "instance_id": ig.instance_id,
                "gene_id": ig.gene_id,
                "gene_name": gene_name,
                "reason": payload.reason,
            })
        return {"status": "simplified"}

    # Default: "forgotten" -- complete removal
    if gene:
        manifest = _json_loads(gene.manifest) or {}
        skill_name = manifest.get("skill", {}).get("name", gene.slug)
        async with remote_fs(instance, db) as fs:
            await _remove_skill_file(fs, skill_name)
            await ensure_skills_discovery(fs)
            await invalidate_skill_snapshots(fs)
            await inject_evolution_notification(fs, skill_name, "uninstalled")

    ig.soft_delete()
    if gene:
        gene.install_count = max(0, gene.install_count - 1)
    await _record_evolution(
        db, ig.instance_id, EvolutionEventType.forgotten, gene_name,
        gene_slug=gene_slug, gene_id=ig.gene_id,
        details={
            "version": ig.installed_version,
            "usage_count": ig.usage_count,
            "forgetting_summary": payload.content,
            "self_eval": payload.self_eval,
            "method": "deep",
        },
    )
    await db.commit()

    should_restart = await _finish_learning_if_done(db, instance.id, ig.id)
    if should_restart:
        await restart_instance(instance.id, db)

    if workspace_id:
        await broadcast_event(workspace_id, "gene:forgotten", {
            "instance_id": ig.instance_id,
            "gene_id": ig.gene_id,
            "gene_name": gene_name,
        })
    return {"status": "forgotten"}


# ═══════════════════════════════════════════════════
#  Evolution Log
# ═══════════════════════════════════════════════════


async def get_evolution_log(
    db: AsyncSession,
    instance_id: str,
    page: int = 1,
    page_size: int = 20,
) -> list[dict]:
    offset = (page - 1) * page_size
    result = await db.execute(
        select(EvolutionEvent)
        .where(EvolutionEvent.instance_id == instance_id, not_deleted(EvolutionEvent))
        .order_by(EvolutionEvent.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    events = result.scalars().all()
    out = []
    for ev in events:
        details = _json_loads(ev.details)
        out.append({
            "id": ev.id,
            "instance_id": ev.instance_id,
            "event_type": ev.event_type,
            "gene_name": ev.gene_name,
            "gene_slug": ev.gene_slug,
            "gene_id": ev.gene_id,
            "genome_id": ev.genome_id,
            "details": details,
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
        })
    return out


# ═══════════════════════════════════════════════════
#  Admin
# ═══════════════════════════════════════════════════


async def admin_list_genes(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    category: str | None = None,
    is_published: bool | None = None,
    sort: str = "newest",
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    """Admin gene list -- includes unpublished, with extra fields."""
    base = select(Gene).where(not_deleted(Gene))

    if keyword:
        base = base.where(Gene.name.ilike(f"%{keyword}%") | Gene.slug.ilike(f"%{keyword}%"))
    if category:
        base = base.where(Gene.category == category)
    if is_published is not None:
        base = base.where(Gene.is_published.is_(is_published))

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    sort_map = {
        "newest": Gene.created_at.desc(),
        "popularity": Gene.install_count.desc(),
        "rating": Gene.avg_rating.desc(),
        "effectiveness": Gene.effectiveness_score.desc(),
    }
    base = base.order_by(sort_map.get(sort, Gene.created_at.desc()))
    base = base.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(base)
    return [_gene_to_dict(g) for g in result.scalars().all()], total


async def admin_list_genomes(
    db: AsyncSession,
    *,
    keyword: str | None = None,
    is_published: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    base = select(Genome).where(not_deleted(Genome))
    if keyword:
        base = base.where(Genome.name.ilike(f"%{keyword}%") | Genome.slug.ilike(f"%{keyword}%"))
    if is_published is not None:
        base = base.where(Genome.is_published.is_(is_published))

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    base = base.order_by(Genome.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(base)
    items = await _enrich_genomes_tool_counts(db, [_genome_to_dict(g) for g in result.scalars().all()])
    return items, total


async def update_gene(db: AsyncSession, gene_id: str, req: UpdateGeneRequest) -> dict:
    result = await db.execute(select(Gene).where(Gene.id == gene_id, not_deleted(Gene)))
    gene = result.scalar_one_or_none()
    if not gene:
        raise NotFoundError("基因不存在")

    updates = req.model_dump(exclude_unset=True)
    if "tags" in updates and updates["tags"] is not None:
        updates["tags"] = _json_dumps(updates["tags"])
    if "manifest" in updates and updates["manifest"] is not None:
        updates["manifest"] = _json_dumps(updates["manifest"])

    for field, value in updates.items():
        setattr(gene, field, value)

    await db.commit()
    await db.refresh(gene)
    return _gene_to_dict(gene)


async def soft_delete_gene(db: AsyncSession, gene_id: str) -> dict:
    result = await db.execute(select(Gene).where(Gene.id == gene_id, not_deleted(Gene)))
    gene = result.scalar_one_or_none()
    if not gene:
        raise NotFoundError("基因不存在")
    gene.soft_delete()
    await db.commit()
    return {"deleted": True}


async def update_genome(db: AsyncSession, genome_id: str, req: UpdateGenomeRequest) -> dict:
    result = await db.execute(select(Genome).where(Genome.id == genome_id, not_deleted(Genome)))
    genome = result.scalar_one_or_none()
    if not genome:
        raise NotFoundError("基因组不存在")

    updates = req.model_dump(exclude_unset=True)
    if "gene_slugs" in updates and updates["gene_slugs"] is not None:
        updates["gene_slugs"] = _json_dumps(updates["gene_slugs"])
    if "config_override" in updates and updates["config_override"] is not None:
        updates["config_override"] = _json_dumps(updates["config_override"])

    for field, value in updates.items():
        setattr(genome, field, value)

    await db.commit()
    await db.refresh(genome)
    return _genome_to_dict(genome)


async def soft_delete_genome(db: AsyncSession, genome_id: str) -> dict:
    result = await db.execute(select(Genome).where(Genome.id == genome_id, not_deleted(Genome)))
    genome = result.scalar_one_or_none()
    if not genome:
        raise NotFoundError("基因组不存在")
    genome.soft_delete()
    await db.commit()
    return {"deleted": True}


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
