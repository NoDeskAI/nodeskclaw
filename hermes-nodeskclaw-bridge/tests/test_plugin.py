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


def test_parse_content_disposition_filename_decodes_utf8_value():
    assert (
        plugin._parse_content_disposition_filename(
            "attachment; filename*=UTF-8''report%20final.txt"
        )
        == "report final.txt"
    )
    assert (
        plugin._parse_content_disposition_filename(
            "attachment; filename*=UTF-8''%E6%8A%A5%E5%91%8A.txt"
        )
        == "报告.txt"
    )
    assert (
        plugin._parse_content_disposition_filename(
            "attachment; filename*=UTF-8''report.txt; size=12"
        )
        == "report.txt"
    )


def test_file_download_tool_uses_utf8_content_disposition_filename(monkeypatch, tmp_path):
    class _Response:
        headers = {
            "Content-Type": "text/plain",
            "Content-Disposition": "attachment; filename*=UTF-8''report%20final.txt",
        }

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return b"file-body"

    monkeypatch.setenv("NODESKCLAW_API_URL", "http://example.test/api/v1")
    monkeypatch.setenv("NODESKCLAW_TOKEN", "secret")
    monkeypatch.setenv("NODESKCLAW_WORKSPACE_ID", "ws-1")
    monkeypatch.setenv("NODESKCLAW_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(plugin.urllib.request, "urlopen", lambda _request: _Response())
    plugin._on_post_tool_call()

    payload = json.loads(plugin.file_download_tool({"file_id": "file-1"}))

    local_path = tmp_path / "uploads" / "report final.txt"
    assert payload["name"] == "report final.txt"
    assert payload["path"] == str(local_path)
    assert local_path.read_bytes() == b"file-body"


def test_collaboration_tool_returns_error_without_workspace(monkeypatch):
    monkeypatch.delenv("NODESKCLAW_WORKSPACE_ID", raising=False)
    monkeypatch.delenv("DESKCLAW_WORKSPACE_ID", raising=False)
    plugin._on_post_tool_call()

    payload = json.loads(plugin.collaboration_tool({"action": "send_message", "target": "agent:test", "text": "hi"}))

    assert payload["error"] is True
    assert "Workspace context is missing" in payload["message"]


def test_collaboration_tool_returns_error_without_instance(monkeypatch):
    monkeypatch.setenv("NODESKCLAW_WORKSPACE_ID", "ws-1")
    monkeypatch.delenv("NODESKCLAW_INSTANCE_ID", raising=False)
    monkeypatch.delenv("DESKCLAW_INSTANCE_ID", raising=False)
    plugin._on_post_tool_call()

    payload = json.loads(plugin.collaboration_tool({"action": "send_message", "target": "agent:test", "text": "hi"}))

    assert payload["error"] is True
    assert "NODESKCLAW_INSTANCE_ID" in payload["message"]


def test_collaboration_tool_auto_prefixes_target(monkeypatch):
    monkeypatch.setenv("NODESKCLAW_WORKSPACE_ID", "ws-1")
    monkeypatch.setenv("NODESKCLAW_INSTANCE_ID", "inst-1")
    monkeypatch.setenv("NODESKCLAW_TOKEN", "tok")
    monkeypatch.setenv("NODESKCLAW_API_URL", "http://unreachable.test/api/v1")
    plugin._on_post_tool_call()

    result = json.loads(plugin.collaboration_tool({"action": "send_message", "target": "Bob", "text": "hello"}))
    assert isinstance(result, dict)


def test_shared_files_tool_returns_error_without_workspace(monkeypatch):
    monkeypatch.delenv("NODESKCLAW_WORKSPACE_ID", raising=False)
    monkeypatch.delenv("DESKCLAW_WORKSPACE_ID", raising=False)
    plugin._on_post_tool_call()

    payload = json.loads(plugin.shared_files_tool({"action": "list"}))

    assert payload["error"] is True
    assert "Workspace context is missing" in payload["message"]


# ── _ThinkingPreambleFilter tests ─────────────────────

from hermes_nodeskclaw_bridge.hermes_channel import _ThinkingPreambleFilter


def test_filter_strips_english_preamble():
    f = _ThinkingPreambleFilter()
    assert f.feed("The user is asking me to ") == ""
    assert f.feed("greet everyone. I should respond. ") == ""
    result = f.feed("大家好！我是项目协调员。")
    assert result == "大家好！我是项目协调员。"


def test_filter_passes_pure_chinese():
    f = _ThinkingPreambleFilter()
    assert f.feed("你好世界") == "你好世界"


def test_filter_strips_think_tags():
    f = _ThinkingPreambleFilter()
    assert f.feed("<think>reasoning here</think>回复内容") == "回复内容"


def test_filter_strips_think_tags_across_chunks():
    f = _ThinkingPreambleFilter()
    assert f.feed("<think>start") == ""
    assert f.feed(" reasoning</think>") == ""
    assert f.feed("你好") == "你好"


def test_filter_flush_returns_buffer_for_english_only():
    f = _ThinkingPreambleFilter()
    f.feed("Pure English response with no CJK.")
    result = f.flush()
    assert "Pure English" in result


def test_filter_handles_mixed_preamble():
    f = _ThinkingPreambleFilter()
    assert f.feed("Let me think about this. ") == ""
    result = f.feed("好的，这是我的回复。And some English after.")
    assert result.startswith("好的")
    assert "And some English after." in result
