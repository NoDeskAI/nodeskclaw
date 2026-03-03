"""Convert GeneHub Registry responses to NoDeskClaw format.

GeneHub uses slug-based identifiers and a different response envelope.
NoDeskClaw frontends expect UUID-based ids and specific field names.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def genehub_gene_to_local(
    gene: dict[str, Any],
    local_cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Map a GeneHub gene object to the dict format NoDeskClaw frontends expect."""
    cache = local_cache or {}
    return {
        "id": cache.get("id", gene.get("id", gene.get("slug", ""))),
        "name": gene.get("name", ""),
        "slug": gene.get("slug", ""),
        "description": gene.get("description", ""),
        "short_description": gene.get("short_description", ""),
        "category": gene.get("category", ""),
        "tags": gene.get("tags") or [],
        "source": gene.get("source", "official"),
        "source_ref": gene.get("source_ref"),
        "icon": gene.get("icon"),
        "version": gene.get("version", ""),
        "manifest": gene.get("manifest"),
        "dependencies": gene.get("dependencies") or [],
        "synergies": gene.get("synergies") or [],
        "parent_gene_id": cache.get("parent_gene_id", gene.get("parent_gene_id")),
        "created_by_instance_id": cache.get("created_by_instance_id"),
        "install_count": gene.get("install_count", 0),
        "avg_rating": gene.get("avg_rating", 0),
        "effectiveness_score": gene.get("effectiveness_score", 0),
        "is_featured": gene.get("is_featured", gene.get("install_count", 0) > 0),
        "review_status": gene.get("review_status", "approved"),
        "is_published": gene.get("is_published", True),
        "created_by": cache.get("created_by"),
        "org_id": cache.get("org_id"),
        "created_at": _parse_dt(gene.get("created_at")) or cache.get("created_at"),
        "updated_at": _parse_dt(gene.get("updated_at")) or cache.get("updated_at"),
    }


def genehub_genome_to_local(
    genome: dict[str, Any],
    local_cache: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Map a GeneHub genome object to the dict format NoDeskClaw frontends expect."""
    cache = local_cache or {}
    raw_genes = genome.get("genes") or []
    gene_slugs = []
    for g in raw_genes:
        if isinstance(g, dict):
            slug = g.get("slug")
            if slug:
                gene_slugs.append(str(slug))
        elif isinstance(g, str):
            gene_slugs.append(g)
    return {
        "id": cache.get("id", genome.get("id", genome.get("slug", ""))),
        "name": genome.get("name", ""),
        "slug": genome.get("slug", ""),
        "description": genome.get("description", ""),
        "short_description": genome.get("short_description", ""),
        "icon": genome.get("icon"),
        "gene_slugs": gene_slugs,
        "config_override": cache.get("config_override"),
        "install_count": genome.get("install_count", 0),
        "avg_rating": genome.get("avg_rating", 0),
        "is_featured": genome.get("is_featured", genome.get("install_count", 0) > 0),
        "is_published": genome.get("is_published", True),
        "created_by": cache.get("created_by"),
        "org_id": cache.get("org_id"),
        "created_at": _parse_dt(genome.get("created_at")) or cache.get("created_at"),
    }


def extract_paginated_items(body: dict[str, Any]) -> tuple[list[dict], int]:
    """Extract items and total from a GeneHub paginated response.

    GeneHub format: { code: 0, data: { items: [...], total: N, ... } }
    Returns (items, total).
    """
    data = body.get("data", {})
    if isinstance(data, dict):
        return data.get("items", []), data.get("total", 0)
    if isinstance(data, list):
        return data, len(data)
    return [], 0


def genehub_tags_to_local(tags: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert GeneHub tag stats to NoDeskClaw TagStats format."""
    return [{"tag": t.get("tag", ""), "count": t.get("count", 0)} for t in tags]


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    return None
