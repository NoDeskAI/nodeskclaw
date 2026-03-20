"""DeskClaw API client -- shared HTTP helper for all tool scripts.

Uses only Python standard library (urllib.request + json).
Authentication via environment variables:
  DESKCLAW_API_URL        Backend API base URL (e.g. http://localhost:8000/api/v1)
  DESKCLAW_TOKEN          Instance proxy_token for Bearer auth
  DESKCLAW_WORKSPACE_ID   Current workspace ID
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

API_URL = os.environ.get("DESKCLAW_API_URL", "http://localhost:8000/api/v1")
TOKEN = os.environ.get("DESKCLAW_TOKEN", "")
WORKSPACE_ID = os.environ.get("DESKCLAW_WORKSPACE_ID", "")


def _ws_base() -> str:
    if not WORKSPACE_ID:
        _fatal("DESKCLAW_WORKSPACE_ID is not set")
    return f"{API_URL}/workspaces/{WORKSPACE_ID}"


def _headers() -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return h


def api_call(method: str, path: str, body: dict | None = None, *, ws: bool = True) -> Any:
    """Make an HTTP request to the DeskClaw backend API.

    Args:
        method: HTTP method (GET, POST, PUT, PATCH, DELETE).
        path: URL path relative to workspace base (when ws=True) or API base.
        body: Optional JSON body.
        ws: If True, prepend /workspaces/{WORKSPACE_ID} to path.

    Returns:
        Parsed JSON response.
    """
    base = _ws_base() if ws else API_URL
    url = f"{base}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        try:
            err = json.loads(error_body)
        except (json.JSONDecodeError, ValueError):
            err = {"status": e.code, "detail": error_body}
        _output({"error": True, **err})
        sys.exit(1)
    except (urllib.error.URLError, OSError) as e:
        _output({"error": True, "message": f"Network error: {e}"})
        sys.exit(1)


def _output(data: Any) -> None:
    """Print JSON to stdout for agent consumption."""
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _fatal(msg: str) -> None:
    _output({"error": True, "message": msg})
    sys.exit(1)
