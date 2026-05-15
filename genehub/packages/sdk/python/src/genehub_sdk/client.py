"""GeneHub Registry HTTP 客户端，与 TypeScript SDK client 对齐。"""

import json
from typing import Any

import httpx

from genehub_sdk.types import Gene, GeneManifest


class GeneHubError(Exception):
    """Registry API 返回错误时抛出。"""

    def __init__(self, message: str, error_code: str | None = None) -> None:
        self.error_code = error_code
        super().__init__(f"[GeneHub] {error_code or 'error'}: {message}")


class GeneHubClient:
    """封装 GeneHub Registry API 的 HTTP 调用。"""

    def __init__(self, base_url: str, token: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self._base_url}{path}"
        with httpx.Client(timeout=30.0) as client:
            resp = client.request(
                method,
                url,
                headers=self._headers(),
                **kwargs,
            )
        try:
            data = resp.json()
        except json.JSONDecodeError:
            msg = resp.text or f"HTTP {resp.status_code}"
            raise GeneHubError(msg) from None
        body = data if isinstance(data, dict) else {}
        code = body.get("code", -1)
        if not resp.is_success or code != 0:
            msg = body.get("message") or f"HTTP {resp.status_code}"
            err_code = body.get("error_code")
            raise GeneHubError(msg, error_code=err_code)
        return body.get("data")

    def search_genes(
        self,
        query: str = "",
        *,
        category: str | None = None,
        tags: list[str] | None = None,
        compatibility: str | None = None,
        sort: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> list[Gene]:
        """搜索基因列表。返回当前页的 items；完整分页信息可后续扩展。"""
        params: dict[str, str | int] = {}
        if query:
            params["q"] = query
        if category:
            params["category"] = category
        if tags:
            params["tags"] = ",".join(tags)
        if compatibility:
            params["compatibility"] = compatibility
        if sort:
            params["sort"] = sort
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["page_size"] = page_size
        result = self._request("GET", "/api/v1/genes", params=params)
        if isinstance(result, dict) and "items" in result:
            return result["items"]
        return result if isinstance(result, list) else []

    def get_gene(self, slug: str) -> Gene:
        """获取基因详情（最新版本）。"""
        return self._request("GET", f"/api/v1/genes/{slug}")

    def get_manifest(self, slug: str, version: str | None = None) -> GeneManifest:
        """获取基因 Manifest；可选 version 指定版本。"""
        params = {"version": version} if version else None
        return self._request("GET", f"/api/v1/genes/{slug}/manifest", params=params)

    def publish(self, manifest: GeneManifest, files: dict[str, str] | None = None) -> Gene:
        """发布新基因。body: { manifest, files? }。"""
        body: dict[str, Any] = {"manifest": manifest}
        if files:
            body["files"] = files
        return self._request("POST", "/api/v1/genes", json=body)
