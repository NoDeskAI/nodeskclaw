"""Tests for GeneHub integration: client, converter, and fallback behavior."""

from __future__ import annotations

import pytest

from app.services.genehub_converter import (
    extract_paginated_items,
    genehub_gene_to_local,
    genehub_genome_to_local,
    genehub_tags_to_local,
)


# ═══════════════════════════════════════════════════
#  genehub_converter unit tests
# ═══════════════════════════════════════════════════


class TestGenehubGeneToLocal:
    def test_basic_mapping(self):
        gene = {
            "id": "uuid-from-genehub",
            "name": "Test Gene",
            "slug": "test-gene",
            "version": "1.0.0",
            "description": "A test gene",
            "short_description": "test",
            "category": "skill",
            "tags": ["test", "demo"],
            "source": "official",
            "icon": "brain",
            "install_count": 42,
            "avg_rating": 4.5,
            "effectiveness_score": 3.8,
            "is_published": True,
            "review_status": "approved",
            "manifest": {"skill": {"name": "test-gene", "content": "test content"}},
            "dependencies": [],
            "synergies": ["other-gene"],
            "created_at": "2026-03-01T00:00:00Z",
            "updated_at": "2026-03-01T12:00:00Z",
        }
        result = genehub_gene_to_local(gene)
        assert result["name"] == "Test Gene"
        assert result["slug"] == "test-gene"
        assert result["tags"] == ["test", "demo"]
        assert result["install_count"] == 42
        assert result["avg_rating"] == 4.5
        assert result["is_published"] is True
        assert result["manifest"]["skill"]["name"] == "test-gene"

    def test_local_cache_supplements_uuid(self):
        gene = {"slug": "test-gene", "name": "Test"}
        cache = {"id": "local-uuid-123", "org_id": "org-456", "created_by": "user-789"}
        result = genehub_gene_to_local(gene, cache)
        assert result["id"] == "local-uuid-123"
        assert result["org_id"] == "org-456"
        assert result["created_by"] == "user-789"

    def test_missing_fields_default_gracefully(self):
        gene = {"slug": "minimal-gene"}
        result = genehub_gene_to_local(gene)
        assert result["slug"] == "minimal-gene"
        assert result["name"] == ""
        assert result["tags"] == []
        assert result["install_count"] == 0
        assert result["avg_rating"] == 0
        assert result["is_published"] is True


class TestGenehubGenomeToLocal:
    def test_basic_mapping(self):
        genome = {
            "id": "genome-id",
            "name": "Starter Pack",
            "slug": "starter-pack",
            "description": "A starter genome",
            "genes": [
                {"slug": "gene-a", "version": "1.0.0"},
                {"slug": "gene-b", "version": "2.0.0"},
            ],
            "install_count": 10,
        }
        result = genehub_genome_to_local(genome)
        assert result["name"] == "Starter Pack"
        assert result["slug"] == "starter-pack"
        assert result["gene_slugs"] == ["gene-a", "gene-b"]
        assert result["install_count"] == 10


class TestExtractPaginatedItems:
    def test_genehub_format(self):
        body = {
            "code": 0,
            "data": {
                "items": [{"slug": "a"}, {"slug": "b"}],
                "total": 42,
                "page": 1,
                "page_size": 20,
            },
        }
        items, total = extract_paginated_items(body)
        assert len(items) == 2
        assert total == 42

    def test_empty_response(self):
        body = {"code": 0, "data": {}}
        items, total = extract_paginated_items(body)
        assert items == []
        assert total == 0

    def test_flat_array_fallback(self):
        body = {"code": 0, "data": [{"slug": "x"}]}
        items, total = extract_paginated_items(body)
        assert len(items) == 1
        assert total == 1


class TestGenehubTagsToLocal:
    def test_conversion(self):
        tags = [{"tag": "ai", "count": 10}, {"tag": "coding", "count": 5}]
        result = genehub_tags_to_local(tags)
        assert len(result) == 2
        assert result[0]["tag"] == "ai"
        assert result[0]["count"] == 10


# ═══════════════════════════════════════════════════
#  genehub_client unit tests (no network)
# ═══════════════════════════════════════════════════


class TestGenehubClientDisabled:
    """When GENEHUB_REGISTRY_URL is empty, all calls should return None."""

    @pytest.fixture(autouse=True)
    def _patch_settings(self, monkeypatch):
        monkeypatch.setattr("app.services.genehub_client.settings.GENEHUB_REGISTRY_URL", "")

    @pytest.mark.asyncio
    async def test_list_genes_returns_none(self):
        from app.services import genehub_client

        result = await genehub_client.list_genes()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_gene_returns_none(self):
        from app.services import genehub_client

        result = await genehub_client.get_gene("any-slug")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_manifest_returns_none(self):
        from app.services import genehub_client

        result = await genehub_client.get_manifest("any-slug")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_featured_genes_returns_none(self):
        from app.services import genehub_client

        result = await genehub_client.get_featured_genes()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_gene_tags_returns_none(self):
        from app.services import genehub_client

        result = await genehub_client.get_gene_tags()
        assert result is None

    @pytest.mark.asyncio
    async def test_report_install_returns_false(self):
        from app.services import genehub_client

        result = await genehub_client.report_install("any-slug")
        assert result is False

    @pytest.mark.asyncio
    async def test_publish_gene_returns_none(self):
        from app.services import genehub_client

        result = await genehub_client.publish_gene({"slug": "test"})
        assert result is None


class TestGenehubClientEnabled:
    """When GENEHUB_REGISTRY_URL is set but unreachable, calls should return None gracefully."""

    @pytest.fixture(autouse=True)
    def _patch_settings(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.genehub_client.settings.GENEHUB_REGISTRY_URL",
            "http://127.0.0.1:19999",
        )
        monkeypatch.setattr("app.services.genehub_client.settings.GENEHUB_API_KEY", "test-key")
        monkeypatch.setattr("app.services.genehub_client._client", None)
        monkeypatch.setattr("app.services.genehub_client._TIMEOUT", 0.5)

    @pytest.mark.asyncio
    async def test_list_genes_returns_none_on_connection_error(self):
        from app.services import genehub_client

        result = await genehub_client.list_genes()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_gene_returns_none_on_connection_error(self):
        from app.services import genehub_client

        result = await genehub_client.get_gene("test")
        assert result is None

    @pytest.mark.asyncio
    async def test_report_install_returns_false_on_connection_error(self):
        from app.services import genehub_client

        result = await genehub_client.report_install("test")
        assert result is False
