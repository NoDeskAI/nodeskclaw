"""Security layer tests — Pipeline unit tests + WebSocket endpoint integration tests.

These tests do NOT require a running database or backend server.
"""

from __future__ import annotations

import json
import time

import pytest

from app.services.security.pipeline import SecurityPipeline
from app.services.security.plugins.dlp_scanner import DlpScannerPlugin
from app.services.security.plugins.policy_gate import PolicyGatePlugin
from app.services.security.types import (
    AfterAction,
    BeforeAction,
    ExecutionContext,
    ExecutionResult,
)


# ── Helpers ────────────────────────────────────────────────

def _ctx(tool_name: str, params: dict | None = None) -> ExecutionContext:
    return ExecutionContext(
        tool_name=tool_name,
        params=params or {},
        agent_instance_id="test-agent",
        workspace_id="test-ws",
        timestamp=time.time(),
    )


def _exec_result(result: str = "", error: str | None = None) -> ExecutionResult:
    return ExecutionResult(result=result, error=error, duration_ms=10.0)


# ── PolicyGatePlugin 单元测试 ──────────────────────────────


class TestPolicyGatePlugin:
    @pytest.fixture
    async def gate_enforce(self):
        plugin = PolicyGatePlugin(priority=10)
        await plugin.initialize({
            "mode": "enforce",
            "tools": {
                "exec": {
                    "denied_commands": [r"^sudo\b", r"\brm\s+-rf\s+/"],
                },
                "read_file": {
                    "denied_paths": ["**/.env", "**/.env.*"],
                },
                "dangerous_tool": {
                    "action": "deny",
                },
            },
        })
        return plugin

    @pytest.fixture
    async def gate_monitor(self):
        plugin = PolicyGatePlugin(priority=10)
        await plugin.initialize({
            "mode": "monitor",
            "tools": {
                "exec": {
                    "denied_commands": [r"^sudo\b"],
                },
            },
        })
        return plugin

    async def test_allow_normal_command(self, gate_enforce):
        result = await gate_enforce.before_execute(_ctx("exec", {"command": "ls -la"}))
        assert result.action == BeforeAction.ALLOW

    async def test_deny_sudo(self, gate_enforce):
        result = await gate_enforce.before_execute(_ctx("exec", {"command": "sudo rm -rf /"}))
        assert result.action == BeforeAction.DENY
        assert result.message is not None
        assert "sudo" in result.message.lower() or "denied" in result.message.lower()

    async def test_deny_rm_rf_root(self, gate_enforce):
        result = await gate_enforce.before_execute(_ctx("exec", {"command": "rm -rf /"}))
        assert result.action == BeforeAction.DENY

    async def test_deny_tool_entirely(self, gate_enforce):
        result = await gate_enforce.before_execute(_ctx("dangerous_tool", {"anything": "goes"}))
        assert result.action == BeforeAction.DENY

    async def test_deny_read_env_file(self, gate_enforce):
        result = await gate_enforce.before_execute(_ctx("read_file", {"path": "/app/.env"}))
        assert result.action == BeforeAction.DENY

    async def test_allow_read_normal_file(self, gate_enforce):
        result = await gate_enforce.before_execute(_ctx("read_file", {"path": "/app/main.py"}))
        assert result.action == BeforeAction.ALLOW

    async def test_allow_unknown_tool(self, gate_enforce):
        result = await gate_enforce.before_execute(_ctx("unknown_tool", {}))
        assert result.action == BeforeAction.ALLOW

    async def test_monitor_mode_allows_but_flags(self, gate_monitor):
        result = await gate_monitor.before_execute(_ctx("exec", {"command": "sudo apt install vim"}))
        assert result.action == BeforeAction.ALLOW
        assert result.findings is not None
        assert len(result.findings) > 0


# ── DlpScannerPlugin 单元测试 ─────────────────────────────


class TestDlpScannerPlugin:
    @pytest.fixture
    async def dlp_flag(self):
        plugin = DlpScannerPlugin(priority=50)
        await plugin.initialize({"mode": "flag"})
        return plugin

    @pytest.fixture
    async def dlp_redact(self):
        plugin = DlpScannerPlugin(priority=50)
        await plugin.initialize({"mode": "redact"})
        return plugin

    async def test_clean_output_passes(self, dlp_flag):
        result = await dlp_flag.after_execute(
            _ctx("exec"),
            _exec_result("total 42\ndrwxr-xr-x 2 root root 4096 Mar 10 main.py"),
        )
        assert result.action == AfterAction.PASS

    async def test_flag_aws_key(self, dlp_flag):
        result = await dlp_flag.after_execute(
            _ctx("exec"),
            _exec_result("Found key: AKIAIOSFODNN7EXAMPLE"),
        )
        assert result.action == AfterAction.FLAG
        assert result.findings is not None
        assert any("AWS" in f.message for f in result.findings)

    async def test_redact_aws_key(self, dlp_redact):
        result = await dlp_redact.after_execute(
            _ctx("exec"),
            _exec_result("export AWS_KEY=AKIAIOSFODNN7EXAMPLE"),
        )
        assert result.action == AfterAction.REDACT
        assert result.modified_result is not None
        assert "AKIAIOSFODNN7EXAMPLE" not in result.modified_result
        assert "[REDACTED:" in result.modified_result

    async def test_flag_private_key(self, dlp_flag):
        result = await dlp_flag.after_execute(
            _ctx("exec"),
            _exec_result("-----BEGIN RSA PRIVATE KEY-----\nMIIEpA..."),
        )
        assert result.action == AfterAction.FLAG
        assert result.findings is not None

    async def test_flag_github_token(self, dlp_flag):
        result = await dlp_flag.after_execute(
            _ctx("exec"),
            _exec_result("token = ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"),
        )
        assert result.action == AfterAction.FLAG


# ── SecurityPipeline 编排测试 ─────────────────────────────


class TestSecurityPipeline:
    async def test_empty_pipeline_allows(self):
        pipeline = SecurityPipeline()
        before = await pipeline.run_before(_ctx("exec", {"command": "ls"}))
        assert before.action == BeforeAction.ALLOW

        after = await pipeline.run_after(_ctx("exec"), _exec_result("output"))
        assert after.action == AfterAction.PASS

    async def test_pipeline_with_policy_gate(self):
        pipeline = SecurityPipeline()
        gate = PolicyGatePlugin(priority=10)
        await gate.initialize({
            "mode": "enforce",
            "tools": {"exec": {"denied_commands": [r"^sudo\b"]}},
        })
        pipeline.add_plugin(gate)

        allow = await pipeline.run_before(_ctx("exec", {"command": "ls"}))
        assert allow.action == BeforeAction.ALLOW

        deny = await pipeline.run_before(_ctx("exec", {"command": "sudo reboot"}))
        assert deny.action == BeforeAction.DENY

    async def test_pipeline_with_dlp_scanner(self):
        pipeline = SecurityPipeline()
        dlp = DlpScannerPlugin(priority=50)
        await dlp.initialize({"mode": "redact"})
        pipeline.add_plugin(dlp)

        after = await pipeline.run_after(
            _ctx("exec"),
            _exec_result("key=AKIAIOSFODNN7EXAMPLE"),
        )
        assert after.action == AfterAction.REDACT
        assert "AKIAIOSFODNN7EXAMPLE" not in (after.modified_result or "")

    async def test_pipeline_combined(self):
        pipeline = SecurityPipeline()

        gate = PolicyGatePlugin(priority=10)
        await gate.initialize({
            "mode": "enforce",
            "tools": {"exec": {"denied_commands": [r"^sudo\b"]}},
        })
        pipeline.add_plugin(gate)

        dlp = DlpScannerPlugin(priority=50)
        await dlp.initialize({"mode": "redact"})
        pipeline.add_plugin(dlp)

        before_allow = await pipeline.run_before(_ctx("exec", {"command": "cat config.txt"}))
        assert before_allow.action == BeforeAction.ALLOW

        before_deny = await pipeline.run_before(_ctx("exec", {"command": "sudo cat /etc/shadow"}))
        assert before_deny.action == BeforeAction.DENY

        after_redact = await pipeline.run_after(
            _ctx("exec"),
            _exec_result("-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAK..."),
        )
        assert after_redact.action == AfterAction.REDACT


# ── WebSocket 端点集成测试 ─────────────────────────────────


class TestSecurityWebSocket:
    @pytest.fixture
    def pipeline_with_plugins(self):
        """Create a pipeline pre-loaded with policy-gate and dlp-scanner."""
        import asyncio

        pipeline = SecurityPipeline()

        gate = PolicyGatePlugin(priority=10)
        asyncio.get_event_loop().run_until_complete(gate.initialize({
            "mode": "enforce",
            "tools": {"exec": {"denied_commands": [r"^sudo\b"]}},
        }))
        pipeline.add_plugin(gate)

        dlp = DlpScannerPlugin(priority=50)
        asyncio.get_event_loop().run_until_complete(dlp.initialize({"mode": "redact"}))
        pipeline.add_plugin(dlp)

        return pipeline

    @pytest.fixture
    def test_app(self, pipeline_with_plugins):
        from fastapi import FastAPI
        from app.api.security_ws import router, set_pipeline

        test_app = FastAPI()
        test_app.include_router(router, prefix="/api/v1")
        set_pipeline(pipeline_with_plugins)
        yield test_app
        set_pipeline(None)

    def test_ws_evaluate_before_allow(self, test_app):
        from starlette.testclient import TestClient

        client = TestClient(test_app)
        with client.websocket_connect("/api/v1/security/ws") as ws:
            ws.send_json({
                "type": "evaluate_before",
                "id": "r-1",
                "ctx": {
                    "tool_name": "exec",
                    "params": {"command": "ls -la"},
                    "agent_instance_id": "test-agent",
                    "workspace_id": "test-ws",
                    "timestamp": time.time(),
                },
            })
            resp = ws.receive_json()
            assert resp["type"] == "result"
            assert resp["id"] == "r-1"
            assert resp["result"]["action"] == "allow"

    def test_ws_evaluate_before_deny(self, test_app):
        from starlette.testclient import TestClient

        client = TestClient(test_app)
        with client.websocket_connect("/api/v1/security/ws") as ws:
            ws.send_json({
                "type": "evaluate_before",
                "id": "r-2",
                "ctx": {
                    "tool_name": "exec",
                    "params": {"command": "sudo rm -rf /"},
                    "agent_instance_id": "test-agent",
                    "workspace_id": "test-ws",
                    "timestamp": time.time(),
                },
            })
            resp = ws.receive_json()
            assert resp["type"] == "result"
            assert resp["id"] == "r-2"
            assert resp["result"]["action"] == "deny"
            assert "message" in resp["result"]

    def test_ws_evaluate_after_redact(self, test_app):
        from starlette.testclient import TestClient

        client = TestClient(test_app)
        with client.websocket_connect("/api/v1/security/ws") as ws:
            ws.send_json({
                "type": "evaluate_after",
                "id": "r-3",
                "ctx": {
                    "tool_name": "exec",
                    "params": {"command": "cat credentials.txt"},
                    "agent_instance_id": "test-agent",
                    "workspace_id": "test-ws",
                    "timestamp": time.time(),
                },
                "exec_result": {
                    "result": "aws_access_key_id = AKIAIOSFODNN7EXAMPLE",
                    "error": None,
                    "duration_ms": 15.0,
                },
            })
            resp = ws.receive_json()
            assert resp["type"] == "result"
            assert resp["id"] == "r-3"
            assert resp["result"]["action"] == "redact"
            assert "AKIAIOSFODNN7EXAMPLE" not in resp["result"].get("modified_result", "")

    def test_ws_multiple_requests(self, test_app):
        from starlette.testclient import TestClient

        client = TestClient(test_app)
        with client.websocket_connect("/api/v1/security/ws") as ws:
            ws.send_json({
                "type": "evaluate_before",
                "id": "r-10",
                "ctx": {"tool_name": "exec", "params": {"command": "echo hello"}, "agent_instance_id": "", "workspace_id": "", "timestamp": 0},
            })
            resp1 = ws.receive_json()
            assert resp1["id"] == "r-10"
            assert resp1["result"]["action"] == "allow"

            ws.send_json({
                "type": "evaluate_before",
                "id": "r-11",
                "ctx": {"tool_name": "exec", "params": {"command": "sudo shutdown"}, "agent_instance_id": "", "workspace_id": "", "timestamp": 0},
            })
            resp2 = ws.receive_json()
            assert resp2["id"] == "r-11"
            assert resp2["result"]["action"] == "deny"

    def test_ws_invalid_json_ignored(self, test_app):
        from starlette.testclient import TestClient

        client = TestClient(test_app)
        with client.websocket_connect("/api/v1/security/ws") as ws:
            ws.send_text("not valid json {{{")
            ws.send_json({
                "type": "evaluate_before",
                "id": "r-20",
                "ctx": {"tool_name": "exec", "params": {"command": "ls"}, "agent_instance_id": "", "workspace_id": "", "timestamp": 0},
            })
            resp = ws.receive_json()
            assert resp["id"] == "r-20"
            assert resp["result"]["action"] == "allow"
