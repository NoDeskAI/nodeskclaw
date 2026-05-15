"""GeneHubClient 单元测试（pytest-httpx 模拟 HTTP）。"""

import pytest

from genehub_sdk import GeneHubClient, GeneHubError
from genehub_sdk.types import GeneManifest


def test_search_genes_returns_items(httpx_mock: pytest.FixtureRequest) -> None:
    httpx_mock.add_response(
        url="https://registry.example.com/api/v1/genes?q=code",
        json={
            "code": 0,
            "message": "success",
            "data": {
                "items": [
                    {"id": "1", "slug": "clean-code", "name": "Clean Code", "version": "1.0.0"},
                ],
                "total": 1,
                "page": 1,
                "page_size": 20,
                "total_pages": 1,
            },
        },
    )
    client = GeneHubClient(base_url="https://registry.example.com")
    items = client.search_genes("code")
    assert len(items) == 1
    assert items[0]["slug"] == "clean-code"


def test_get_gene(httpx_mock: pytest.FixtureRequest) -> None:
    httpx_mock.add_response(
        url="https://registry.example.com/api/v1/genes/clean-code",
        json={
            "code": 0,
            "message": "success",
            "data": {
                "id": "1",
                "slug": "clean-code",
                "name": "Clean Code",
                "version": "1.0.0",
            },
        },
    )
    client = GeneHubClient(base_url="https://registry.example.com")
    gene = client.get_gene("clean-code")
    assert gene["slug"] == "clean-code"
    assert gene["version"] == "1.0.0"


def test_get_manifest(httpx_mock: pytest.FixtureRequest) -> None:
    httpx_mock.add_response(
        url="https://registry.example.com/api/v1/genes/clean-code/manifest?version=1.0.0",
        json={
            "code": 0,
            "message": "success",
            "data": {
                "slug": "clean-code",
                "name": "Clean Code",
                "version": "1.0.0",
                "skill": {"name": "clean-code", "always": False},
                "compatibility": [{"product": "openclaw"}],
            },
        },
    )
    client = GeneHubClient(base_url="https://registry.example.com")
    manifest = client.get_manifest("clean-code", version="1.0.0")
    assert manifest["slug"] == "clean-code"
    assert manifest["version"] == "1.0.0"


def test_publish(httpx_mock: pytest.FixtureRequest) -> None:
    httpx_mock.add_response(
        url="https://registry.example.com/api/v1/genes",
        method="POST",
        json={
            "code": 0,
            "message": "success",
            "data": {
                "id": "1",
                "slug": "my-gene",
                "name": "My Gene",
                "version": "1.0.0",
            },
        },
    )
    client = GeneHubClient(base_url="https://registry.example.com")
    manifest: GeneManifest = {
        "slug": "my-gene",
        "name": "My Gene",
        "version": "1.0.0",
        "description": "Desc",
        "short_description": "Short",
        "category": "development",
        "tags": ["ability"],
        "compatibility": [{"product": "openclaw"}],
        "skill": {"name": "my-gene", "always": False},
    }
    gene = client.publish(manifest)
    assert gene["slug"] == "my-gene"


def test_api_error_raises(httpx_mock: pytest.FixtureRequest) -> None:
    httpx_mock.add_response(
        url="https://registry.example.com/api/v1/genes/not-found",
        status_code=404,
        json={"code": 20001, "error_code": "gene_not_found", "message": "基因不存在", "data": None},
    )
    client = GeneHubClient(base_url="https://registry.example.com")
    with pytest.raises(GeneHubError) as exc_info:
        client.get_gene("not-found")
    assert "gene_not_found" in str(exc_info.value) or "基因" in str(exc_info.value)


def test_non_json_response_raises_genehub_error(httpx_mock: pytest.FixtureRequest) -> None:
    """服务端返回非 JSON（如 502 HTML）时应抛出 GeneHubError。"""
    httpx_mock.add_response(
        url="https://registry.example.com/api/v1/genes/clean-code",
        status_code=502,
        content=b"<html>Bad Gateway</html>",
    )
    client = GeneHubClient(base_url="https://registry.example.com")
    with pytest.raises(GeneHubError) as exc_info:
        client.get_gene("clean-code")
    assert "502" in str(exc_info.value) or "Bad Gateway" in str(exc_info.value)
