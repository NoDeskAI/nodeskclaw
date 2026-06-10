from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hermes_nodeskclaw_bridge import plugin
from hermes_nodeskclaw_bridge.hermes_channel import (
    HermesChannel,
    _ThinkingPreambleFilter,
    _attribution_session_key_for,
    _build_learning_prompt,
    _extract_learning_result,
    _failed_learning_result,
    _post_learning_callback,
    _session_id_for,
)


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


def test_proposals_schema_does_not_expose_agent_override():
    properties = plugin._PROPOSALS_SCHEMA["parameters"]["properties"]

    assert "agent_instance_id" not in properties


def test_hermes_channel_session_keys_use_workspace_context():
    assert _session_id_for("ws-1", "req-1") == "workspace:ws-1"
    assert _attribution_session_key_for(" ws-1 ") == "workspace:ws-1"
    assert _session_id_for("", "req-1") == "nodeskclaw:req-1"
    assert _attribution_session_key_for("") == ""


def test_hermes_channel_sends_attribution_session_key(monkeypatch):
    captured = {}

    async def fake_stream_response(self, headers, payload, request_id, trace_id):
        captured["headers"] = headers
        captured["payload"] = payload
        captured["request_id"] = request_id
        captured["trace_id"] = trace_id

    monkeypatch.setattr(HermesChannel, "_stream_response", fake_stream_response)
    channel = HermesChannel(object(), api_key="secret")

    asyncio.run(
        channel.handle_chat_request(
            request_id="req-1",
            trace_id="trace-1",
            messages=[{"role": "user", "content": "hello"}],
            workspace_id="ws-1",
            no_reply=False,
        )
    )

    assert captured["headers"]["X-Hermes-Session-Id"] == "workspace:ws-1"
    assert captured["headers"]["X-NoDeskClaw-Session-Key"] == "workspace:ws-1"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["payload"]["messages"] == [{"role": "user", "content": "hello"}]


def test_proposals_tool_check_trust_uses_current_instance(monkeypatch):
    recorded = {}

    def fake_api_fetch(cfg, path, *, method="GET", body=None):
        recorded["path"] = path
        recorded["method"] = method
        recorded["body"] = body
        return {"ok": True}

    monkeypatch.setenv("NODESKCLAW_WORKSPACE_ID", "ws-1")
    monkeypatch.setenv("NODESKCLAW_INSTANCE_ID", "inst-1")
    monkeypatch.setenv("NODESKCLAW_TOKEN", "tok")
    monkeypatch.setenv("NODESKCLAW_API_URL", "http://example.test/api/v1")
    monkeypatch.setattr(plugin, "_api_fetch", fake_api_fetch)
    plugin._on_post_tool_call()

    payload = json.loads(
        plugin.proposals_tool(
            {
                "action": "check_trust_policy",
                "agent_instance_id": "inst-other",
                "action_type": "deploy",
            }
        )
    )

    assert payload == {"ok": True}
    assert "agent_instance_id=inst-1" in recorded["path"]
    assert "inst-other" not in recorded["path"]


def test_proposals_tool_submit_uses_current_instance(monkeypatch):
    recorded = {}

    def fake_api_fetch(cfg, path, *, method="GET", body=None):
        recorded["path"] = path
        recorded["method"] = method
        recorded["body"] = body
        return {"ok": True}

    monkeypatch.setenv("NODESKCLAW_WORKSPACE_ID", "ws-1")
    monkeypatch.setenv("NODESKCLAW_INSTANCE_ID", "inst-1")
    monkeypatch.setenv("NODESKCLAW_TOKEN", "tok")
    monkeypatch.setenv("NODESKCLAW_API_URL", "http://example.test/api/v1")
    monkeypatch.setattr(plugin, "_api_fetch", fake_api_fetch)
    plugin._on_post_tool_call()

    payload = json.loads(
        plugin.proposals_tool(
            {
                "action": "submit_approval_request",
                "agent_instance_id": "inst-other",
                "action_type": "deploy",
                "proposal": {"kind": "deployment"},
            }
        )
    )

    assert payload == {"ok": True}
    assert recorded["path"] == "/workspaces/approval-requests"
    assert recorded["method"] == "POST"
    assert recorded["body"]["agent_instance_id"] == "inst-1"


def test_proposals_tool_list_decisions_uses_current_instance(monkeypatch):
    recorded = {}

    def fake_api_fetch(cfg, path, *, method="GET", body=None):
        recorded["path"] = path
        recorded["method"] = method
        recorded["body"] = body
        return {"ok": True}

    monkeypatch.setenv("NODESKCLAW_WORKSPACE_ID", "ws-1")
    monkeypatch.setenv("NODESKCLAW_INSTANCE_ID", "inst-1")
    monkeypatch.setenv("NODESKCLAW_TOKEN", "tok")
    monkeypatch.setenv("NODESKCLAW_API_URL", "http://example.test/api/v1")
    monkeypatch.setattr(plugin, "_api_fetch", fake_api_fetch)
    plugin._on_post_tool_call()

    payload = json.loads(
        plugin.proposals_tool({"action": "list_my_decisions", "agent_instance_id": "inst-other"})
    )

    assert payload == {"ok": True}
    assert recorded["path"] == "/workspaces/ws-1/decision-records?agent_id=inst-1"


def test_shared_files_tool_returns_error_without_workspace(monkeypatch):
    monkeypatch.delenv("NODESKCLAW_WORKSPACE_ID", raising=False)
    monkeypatch.delenv("DESKCLAW_WORKSPACE_ID", raising=False)
    plugin._on_post_tool_call()

    payload = json.loads(plugin.shared_files_tool({"action": "list"}))

    assert payload["error"] is True
    assert "Workspace context is missing" in payload["message"]


def test_shared_files_upload_uses_multipart(monkeypatch):
    recorded = {}

    def fake_multipart_upload(cfg, path, file_content, filename, fields=None):
        recorded["path"] = path
        recorded["file_content"] = file_content
        recorded["filename"] = filename
        recorded["fields"] = fields
        return {
            "code": 0,
            "data": {
                "id": "file-1",
                "name": filename,
                "parent_path": (fields or {}).get("parent_path", "/"),
            },
        }

    monkeypatch.setenv("NODESKCLAW_WORKSPACE_ID", "ws-1")
    monkeypatch.setenv("NODESKCLAW_TOKEN", "tok")
    monkeypatch.setenv("NODESKCLAW_API_URL", "http://example.test/api/v1")
    monkeypatch.setattr(plugin, "_bb_multipart_upload", fake_multipart_upload)
    plugin._on_post_tool_call()

    payload = json.loads(
        plugin.shared_files_tool(
            {
                "action": "upload",
                "filename": "daily-tech-news.md",
                "content": "# 科技新闻\n\n中文内容",
                "parent_path": "/news",
                "content_type": "text/markdown",
            }
        )
    )

    assert recorded["path"] == "/workspaces/ws-1/blackboard/files/upload-multipart"
    assert recorded["file_content"] == "# 科技新闻\n\n中文内容".encode("utf-8")
    assert recorded["filename"] == "daily-tech-news.md"
    assert recorded["fields"]["parent_path"] == "/news"
    assert recorded["fields"]["filename"] == "daily-tech-news.md"
    assert recorded["fields"]["content_type"] == "text/markdown"
    assert payload["data"]["file_id"] == "file-1"
    assert payload["data"]["filename"] == "daily-tech-news.md"


def test_shared_files_upload_local(monkeypatch, tmp_path):
    recorded = {}

    def fake_multipart_upload(cfg, path, file_content, filename, fields=None):
        recorded["path"] = path
        recorded["file_content"] = file_content
        recorded["filename"] = filename
        recorded["fields"] = fields
        return {
            "code": 0,
            "data": {"id": "file-2", "name": filename},
        }

    test_file = tmp_path / "report.pdf"
    test_file.write_bytes(b"\x00\x01\x02binary content")

    monkeypatch.setenv("NODESKCLAW_WORKSPACE_ID", "ws-1")
    monkeypatch.setenv("NODESKCLAW_TOKEN", "tok")
    monkeypatch.setenv("NODESKCLAW_API_URL", "http://example.test/api/v1")
    monkeypatch.setattr(plugin, "_bb_multipart_upload", fake_multipart_upload)
    plugin._on_post_tool_call()

    payload = json.loads(
        plugin.shared_files_tool(
            {
                "action": "upload_local",
                "local_path": str(test_file),
                "parent_path": "/reports",
            }
        )
    )

    assert recorded["path"] == "/workspaces/ws-1/blackboard/files/upload-multipart"
    assert recorded["file_content"] == b"\x00\x01\x02binary content"
    assert recorded["filename"] == "report.pdf"
    assert recorded["fields"]["parent_path"] == "/reports"
    assert payload["data"]["file_id"] == "file-2"


def test_shared_files_upload_local_missing_file(monkeypatch):
    monkeypatch.setenv("NODESKCLAW_WORKSPACE_ID", "ws-1")
    monkeypatch.setenv("NODESKCLAW_TOKEN", "tok")
    monkeypatch.setenv("NODESKCLAW_API_URL", "http://example.test/api/v1")
    plugin._on_post_tool_call()

    payload = json.loads(
        plugin.shared_files_tool(
            {
                "action": "upload_local",
                "local_path": "/nonexistent/path/file.txt",
            }
        )
    )

    assert "File not found" in payload["error"]


def test_shared_files_mkdir_splits_path_for_backend(monkeypatch):
    recorded = {}

    def fake_api_fetch(cfg, path, *, method="GET", body=None):
        recorded["path"] = path
        recorded["method"] = method
        recorded["body"] = body
        return {"code": 0, "data": {"id": "dir-1"}}

    monkeypatch.setenv("NODESKCLAW_WORKSPACE_ID", "ws-1")
    monkeypatch.setenv("NODESKCLAW_TOKEN", "tok")
    monkeypatch.setenv("NODESKCLAW_API_URL", "http://example.test/api/v1")
    monkeypatch.setattr(plugin, "_api_fetch", fake_api_fetch)
    plugin._on_post_tool_call()

    payload = json.loads(plugin.shared_files_tool({"action": "mkdir", "path": "/reports/2026"}))

    assert payload == {"code": 0, "data": {"id": "dir-1"}}
    assert recorded["path"] == "/workspaces/ws-1/blackboard/files/mkdir"
    assert recorded["method"] == "POST"
    assert recorded["body"] == {"parent_path": "/reports/", "name": "2026"}

    payload = json.loads(plugin.shared_files_tool({"action": "mkdir", "path": "/news"}))

    assert payload == {"code": 0, "data": {"id": "dir-1"}}
    assert recorded["body"] == {"parent_path": "/", "name": "news"}


def test_shared_files_tool_keeps_backend_error(monkeypatch):
    def fake_multipart_upload(cfg, path, file_content, filename, fields=None):
        return {
            "error": True,
            "status": 400,
            "message": "Bad request: file too large",
        }

    monkeypatch.setenv("NODESKCLAW_WORKSPACE_ID", "ws-1")
    monkeypatch.setenv("NODESKCLAW_TOKEN", "tok")
    monkeypatch.setenv("NODESKCLAW_API_URL", "http://example.test/api/v1")
    monkeypatch.setattr(plugin, "_bb_multipart_upload", fake_multipart_upload)
    plugin._on_post_tool_call()

    payload = json.loads(plugin.shared_files_tool({"action": "upload", "content": "hello"}))

    assert payload["error"] is True
    assert payload["status"] == 400
    assert "file too large" in payload["message"]


# ── _ThinkingPreambleFilter tests ─────────────────────


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


# ── learning.task tests ─────────────────────────────


def test_extract_learning_result_parses_fenced_json_with_think(monkeypatch):
    monkeypatch.setenv("NODESKCLAW_INSTANCE_ID", "inst-env")
    task = {"task_id": "task-1", "mode": "learn"}
    raw = "<think>internal</think>```json\n{\n  \"decision\": \"learned\",\n  \"content\": \"---\\nname: demo\",\n  \"self_eval\": 0.8,\n  \"reason\": \"ok\"\n}\n```"

    result = _extract_learning_result(task, raw)

    assert result["task_id"] == "task-1"
    assert result["instance_id"] == "inst-env"
    assert result["mode"] == "learn"
    assert result["decision"] == "learned"
    assert result["self_eval"] == 0.8


def test_extract_learning_result_parses_json_after_preamble():
    task = {"task_id": "task-2", "instance_id": "inst-2", "mode": "create"}
    raw = "I will return the JSON now. {\"decision\": \"created\", \"meta\": {\"gene_slug\": \"demo\"}}"

    result = _extract_learning_result(task, raw)

    assert result["task_id"] == "task-2"
    assert result["instance_id"] == "inst-2"
    assert result["decision"] == "created"
    assert result["meta"]["gene_slug"] == "demo"


def test_failed_learning_result_uses_forget_failed_for_forget_tasks():
    result = _failed_learning_result({"task_id": "task-3", "instance_id": "inst-3", "mode": "forget"}, "bad")

    assert result == {
        "task_id": "task-3",
        "instance_id": "inst-3",
        "mode": "forget",
        "decision": "forget_failed",
        "reason": "bad",
    }


def test_build_learning_prompt_does_not_use_openclaw_send_command():
    prompt = _build_learning_prompt({"task_id": "task-4", "mode": "learn", "gene_slug": "demo"})

    assert "Return only JSON" in prompt
    assert "send -t learning" not in prompt


class _CallbackResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _CallbackClient:
    responses: list[_CallbackResponse | Exception] = []
    requests: list[dict] = []

    def __init__(self, timeout: int) -> None:
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url: str, *, headers: dict, json: dict):
        self.requests.append({"url": url, "headers": headers, "json": json})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def callback_client(monkeypatch):
    _CallbackClient.responses = []
    _CallbackClient.requests = []
    monkeypatch.setattr("hermes_nodeskclaw_bridge.hermes_channel.httpx.AsyncClient", _CallbackClient)
    return _CallbackClient


@pytest.fixture
def no_sleep(monkeypatch):
    calls = []

    async def fake_sleep(delay: float):
        calls.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return calls


def test_post_learning_callback_succeeds_without_retry(callback_client, no_sleep):
    callback_client.responses = [_CallbackResponse(200, "ok")]

    asyncio.run(_post_learning_callback("http://backend.test/callback", {"task_id": "task-1"}))

    assert len(callback_client.requests) == 1
    assert no_sleep == []


def test_post_learning_callback_retries_429_and_5xx(callback_client, no_sleep):
    callback_client.responses = [
        _CallbackResponse(429, "rate limit"),
        _CallbackResponse(502, "bad gateway"),
        _CallbackResponse(200, "ok"),
    ]

    asyncio.run(_post_learning_callback("http://backend.test/callback", {"task_id": "task-1"}))

    assert len(callback_client.requests) == 3
    assert no_sleep == [0.5, 1.5]


def test_post_learning_callback_does_not_retry_400(callback_client, no_sleep):
    callback_client.responses = [_CallbackResponse(400, "bad request")]

    with pytest.raises(RuntimeError, match="HTTP 400"):
        asyncio.run(_post_learning_callback("http://backend.test/callback", {"task_id": "task-1"}))

    assert len(callback_client.requests) == 1
    assert no_sleep == []


def test_post_learning_callback_raises_after_transport_retries(callback_client, no_sleep):
    import httpx

    callback_client.responses = [
        httpx.ConnectError("connect failed"),
        httpx.ReadTimeout("timeout"),
        _CallbackResponse(500, "server error"),
    ]

    with pytest.raises(RuntimeError, match="after 3 attempts"):
        asyncio.run(_post_learning_callback("http://backend.test/callback", {"task_id": "task-1"}))

    assert len(callback_client.requests) == 3
    assert no_sleep == [0.5, 1.5]
