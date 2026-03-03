"""GeneHub Registry HTTP client.

Wraps GeneHub Registry API calls. All methods return None on failure
so callers can fallback to local data.
"""

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 5.0
_client: httpx.AsyncClient | None = None


def _is_enabled() -> bool:
    return bool(settings.GENEHUB_REGISTRY_URL)


def _base_url() -> str:
    return settings.GENEHUB_REGISTRY_URL.rstrip("/")


def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Accept": "application/json"}
    if settings.GENEHUB_API_KEY:
        h["Authorization"] = f"Bearer {settings.GENEHUB_API_KEY}"
    return h


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=_TIMEOUT, headers=_headers())
    return _client


def _log_error(method: str, path: str, exc: Exception) -> None:
    if isinstance(exc, httpx.TimeoutException):
        logger.warning("GeneHub timeout: %s %s", method, path)
    elif isinstance(exc, httpx.HTTPStatusError):
        logger.warning("GeneHub HTTP %d: %s %s", exc.response.status_code, method, path)
    elif isinstance(exc, httpx.RequestError):
        logger.warning("GeneHub connection error: %s %s -> %s", method, path, exc)
    else:
        logger.warning("GeneHub unexpected error: %s %s -> %s", method, path, exc)


async def _get(path: str, params: dict[str, Any] | None = None) -> dict | None:
    if not _is_enabled():
        return None
    try:
        client = await _get_client()
        resp = await client.get(f"{_base_url()}{path}", params=params)
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != 0:
            logger.warning("GeneHub API error: %s %s -> %s", path, params, body.get("message"))
            return None
        return body
    except Exception as e:
        _log_error("GET", path, e)
        return None


async def _post(path: str, json_body: dict | None = None) -> dict | None:
    if not _is_enabled():
        return None
    try:
        client = await _get_client()
        resp = await client.post(f"{_base_url()}{path}", json=json_body or {})
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != 0:
            logger.warning("GeneHub API error: POST %s -> %s", path, body.get("message"))
            return None
        return body
    except Exception as e:
        _log_error("POST", path, e)
        return None


# ═══════════════════════════════════════════════════
#  Gene Market APIs
# ═══════════════════════════════════════════════════


async def list_genes(
    *,
    keyword: str | None = None,
    tag: str | None = None,
    category: str | None = None,
    sort: str = "popularity",
    page: int = 1,
    page_size: int = 20,
) -> dict | None:
    """GET /api/v1/genes — returns full response body or None."""
    sort_map = {"popularity": "popular", "rating": "rating", "newest": "newest"}
    params: dict[str, Any] = {
        "page": page,
        "page_size": page_size,
    }
    if keyword:
        params["q"] = keyword
    if tag:
        params["tags"] = tag
    if category:
        params["category"] = category
    params["sort"] = sort_map.get(sort, sort)
    return await _get("/api/v1/genes", params)


async def get_gene(slug: str) -> dict | None:
    """GET /api/v1/genes/:slug — returns gene data or None."""
    body = await _get(f"/api/v1/genes/{slug}")
    return body.get("data") if body else None


async def get_manifest(slug: str, version: str | None = None) -> dict | None:
    """GET /api/v1/genes/:slug/manifest — returns manifest dict or None."""
    params = {"version": version} if version else None
    body = await _get(f"/api/v1/genes/{slug}/manifest", params)
    return body.get("data") if body else None


async def get_featured_genes(limit: int = 10) -> list[dict] | None:
    """GET /api/v1/genes/featured"""
    body = await _get("/api/v1/genes/featured", {"limit": limit})
    return body.get("data") if body else None


async def get_gene_tags() -> list[dict] | None:
    """GET /api/v1/genes/tags"""
    body = await _get("/api/v1/genes/tags")
    return body.get("data") if body else None


async def get_gene_synergies(slug: str) -> list[dict] | None:
    """GET /api/v1/genes/:slug/synergies"""
    body = await _get(f"/api/v1/genes/{slug}/synergies")
    return body.get("data") if body else None


# ═══════════════════════════════════════════════════
#  Genome Market APIs
# ═══════════════════════════════════════════════════


async def list_genomes(
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict | None:
    """GET /api/v1/genomes"""
    params: dict[str, Any] = {"page": page, "page_size": page_size}
    if keyword:
        params["q"] = keyword
    return await _get("/api/v1/genomes", params)


async def get_genome(slug: str) -> dict | None:
    """GET /api/v1/genomes/:slug"""
    body = await _get(f"/api/v1/genomes/{slug}")
    return body.get("data") if body else None


async def get_featured_genomes(limit: int = 10) -> list[dict] | None:
    """GET /api/v1/genomes/featured"""
    body = await _get("/api/v1/genomes/featured", {"limit": limit})
    return body.get("data") if body else None


# ═══════════════════════════════════════════════════
#  Write-back APIs
# ═══════════════════════════════════════════════════


async def report_install(slug: str) -> bool:
    """POST /api/v1/genes/:slug/installed"""
    result = await _post(f"/api/v1/genes/{slug}/installed")
    return result is not None


async def report_effectiveness(slug: str, metric_type: str, value: float) -> bool:
    """POST /api/v1/genes/:slug/effectiveness"""
    result = await _post(
        f"/api/v1/genes/{slug}/effectiveness",
        {"metric_type": metric_type, "value": value},
    )
    return result is not None


async def publish_gene(manifest: dict) -> dict | None:
    """POST /api/v1/genes — push a new gene to GeneHub."""
    body = await _post("/api/v1/genes", {"manifest": manifest})
    return body.get("data") if body else None


async def close() -> None:
    """Shutdown the shared HTTP client."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
