from __future__ import annotations

import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hermes_nodeskclaw_bridge import plugin


def test_resolve_tool_config_prefers_hook_session_workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("NODESKCLAW_API_URL", "http://example.test/api/v1")
    monkeypatch.setenv("NODESKCLAW_TOKEN", "secret")
    monkeypatch.setenv("NODESKCLAW_INSTANCE_ID", "inst-1")
    monkeypatch.setenv("NODESKCLAW_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.delenv("NODESKCLAW_WORKSPACE_ID", raising=False)
    monkeypatch.delenv("DESKCLAW_WORKSPACE_ID", raising=False)

    plugin._on_pre_tool_call(session_id="workspace:ws-123")
    cfg = plugin._resolve_tool_config({})
    plugin._on_post_tool_call()

    assert cfg.api_url == "http://example.test/api/v1"
    assert cfg.token == "secret"
    assert cfg.instance_id == "inst-1"
    assert cfg.workspace_id == "ws-123"
    assert cfg.workspace_root == tmp_path


def test_resolve_tool_config_uses_hook_task_workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("NODESKCLAW_API_URL", "http://example.test/api/v1")
    monkeypatch.setenv("NODESKCLAW_TOKEN", "secret")
    monkeypatch.setenv("NODESKCLAW_INSTANCE_ID", "inst-1")
    monkeypatch.setenv("NODESKCLAW_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.delenv("NODESKCLAW_WORKSPACE_ID", raising=False)
    monkeypatch.delenv("DESKCLAW_WORKSPACE_ID", raising=False)

    try:
        plugin._on_pre_tool_call(task_id="workspace:ws-task")
        cfg = plugin._resolve_tool_config({})
    finally:
        plugin._on_post_tool_call()

    assert cfg.workspace_id == "ws-task"


def test_resolve_workspace_id_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("NODESKCLAW_WORKSPACE_ID", "ws-env")

    workspace_id = plugin._resolve_workspace_id(task_id="", session_id="")

    assert workspace_id == "ws-env"


def test_blackboard_tool_returns_clear_error_without_workspace(monkeypatch):
    monkeypatch.delenv("NODESKCLAW_WORKSPACE_ID", raising=False)
    monkeypatch.delenv("DESKCLAW_WORKSPACE_ID", raising=False)
    plugin._on_post_tool_call()

    payload = json.loads(plugin.blackboard_tool({"action": "get_blackboard"}))

    assert payload["error"] is True
    assert "Workspace context is missing" in payload["message"]


def test_resolve_tool_config_accepts_official_deskclaw_env(monkeypatch, tmp_path):
    monkeypatch.delenv("NODESKCLAW_API_URL", raising=False)
    monkeypatch.delenv("NODESKCLAW_TOKEN", raising=False)
    monkeypatch.delenv("NODESKCLAW_INSTANCE_ID", raising=False)
    monkeypatch.delenv("NODESKCLAW_WORKSPACE_ROOT", raising=False)
    monkeypatch.setenv("DESKCLAW_API_URL", "http://deskclaw.test/api/v1")
    monkeypatch.setenv("DESKCLAW_TOKEN", "desk-secret")
    monkeypatch.setenv("DESKCLAW_INSTANCE_ID", "desk-inst")
    monkeypatch.setenv("DESKCLAW_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("DESKCLAW_WORKSPACE_ID", "desk-ws")

    cfg = plugin._resolve_tool_config({})

    assert cfg.api_url == "http://deskclaw.test/api/v1"
    assert cfg.token == "desk-secret"
    assert cfg.instance_id == "desk-inst"
    assert cfg.workspace_id == "desk-ws"
    assert cfg.workspace_root == tmp_path


def test_resolve_unique_file_path_strips_path_traversal(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()

    path = plugin._resolve_unique_file_path(uploads, "../../secret.txt")

    assert path == uploads.resolve() / "secret.txt"
    assert path.is_relative_to(uploads.resolve())


def test_resolve_unique_file_path_strips_absolute_path(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()

    path = plugin._resolve_unique_file_path(uploads, "/etc/passwd")

    assert path == uploads.resolve() / "passwd"
    assert path.is_relative_to(uploads.resolve())


def test_resolve_unique_file_path_falls_back_for_empty_name(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()

    path = plugin._resolve_unique_file_path(uploads, "../..")

    assert path == uploads.resolve() / "unnamed"


def test_resolve_unique_file_path_suffixes_existing_file(tmp_path):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "report.txt").write_text("existing", encoding="utf-8")

    path = plugin._resolve_unique_file_path(uploads, "report.txt")

    assert path == uploads.resolve() / "report(1).txt"
