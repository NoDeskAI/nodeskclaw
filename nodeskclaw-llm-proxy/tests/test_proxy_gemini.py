import asyncio
import inspect
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://nodeskclaw:nodeskclaw@localhost:5432/nodeskclaw_test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import proxy


class FakeRequest:
    def __init__(self, body: dict | bytes, *, method: str = "POST") -> None:
        self.method = method
        self.headers = {}
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")

    async def body(self) -> bytes:
        return self._body


class FakeClient:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.post_calls: list[dict] = []
        self.get_calls: list[dict] = []

    async def post(self, url: str, *, json: dict, headers: dict, timeout: int) -> httpx.Response:
        self.post_calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return self.response

    async def get(self, url: str, *, timeout: int) -> httpx.Response:
        self.get_calls.append({"url": url, "timeout": timeout})
        return self.response


def _json_response_body(response) -> dict:
    return json.loads(response.body.decode("utf-8"))


def test_gemini_models_are_openai_compatible() -> None:
    result = proxy._gemini_models_to_openai({
        "models": [
            {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/embedding-001", "supportedGenerationMethods": ["embedContent"]},
        ]
    })

    assert result == {
        "object": "list",
        "data": [{
            "id": "gemini-2.5-flash",
            "object": "model",
            "created": 0,
            "owned_by": "google",
        }],
    }


def test_openai_chat_payload_converts_to_gemini_generate_content() -> None:
    result = proxy._openai_chat_to_gemini_request({
        "messages": [
            {"role": "system", "content": "你是助手"},
            {"role": "user", "content": "查一下"},
        ],
        "tools": [{
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "查数据",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"query": {"type": "string"}},
                },
            },
        }],
        "tool_choice": {"type": "function", "function": {"name": "lookup"}},
        "temperature": 0.2,
        "max_tokens": 128,
    })

    assert result["systemInstruction"] == {"parts": [{"text": "你是助手"}]}
    assert result["contents"] == [{"role": "user", "parts": [{"text": "查一下"}]}]
    assert result["generationConfig"] == {"temperature": 0.2, "maxOutputTokens": 128}
    assert result["tools"] == [{
        "functionDeclarations": [{
            "name": "lookup",
            "description": "查数据",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
        }]
    }]
    assert result["toolConfig"] == {
        "functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": ["lookup"]}
    }


def test_gemini_function_call_converts_to_openai_tool_call() -> None:
    result = proxy._gemini_response_to_openai({
        "candidates": [{
            "content": {"parts": [{"functionCall": {"name": "lookup", "args": {"query": "NoDeskClaw"}}}]},
            "finishReason": "STOP",
        }],
        "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 5, "totalTokenCount": 8},
    }, "gemini-2.5-flash")

    choice = result["choices"][0]
    tool_call = choice["message"]["tool_calls"][0]
    assert choice["finish_reason"] == "tool_calls"
    assert choice["message"]["content"] is None
    assert tool_call["type"] == "function"
    assert tool_call["function"] == {"name": "lookup", "arguments": '{"query": "NoDeskClaw"}'}
    assert result["usage"] == {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8}


def test_gemini_non_stream_chat_completion_uses_generate_content(monkeypatch) -> None:
    async def run_test() -> None:
        recorded: list[dict] = []

        async def fake_record_usage(ctx, **kwargs) -> None:
            recorded.append(kwargs)

        monkeypatch.setattr(proxy, "_record_usage", fake_record_usage)
        upstream = httpx.Response(
            200,
            json={
                "candidates": [{
                    "content": {"parts": [{"text": "完成"}]},
                    "finishReason": "STOP",
                }],
                "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 2, "totalTokenCount": 6},
            },
            request=httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"),
        )
        client = FakeClient(upstream)
        ctx = SimpleNamespace(
            instance=SimpleNamespace(id="inst-1", created_by="user-1", org_id="org-1"),
            provider="gemini",
            key_source="org",
            org_key_id="org-key-1",
            request_path="/chat/completions",
            is_stream=False,
            raw_body=b"",
        )

        response = await proxy._handle_gemini_proxy(
            FakeRequest({
                "model": "gemini-2.5-flash",
                "messages": [{"role": "user", "content": "hello"}],
            }),
            "chat/completions",
            ctx,
            client=client,
            base_url="https://generativelanguage.googleapis.com",
            api_key="real-key",
        )

        body = _json_response_body(response)
        assert response.status_code == 200
        assert client.post_calls[0]["url"] == (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.5-flash:generateContent?key=real-key"
        )
        assert client.post_calls[0]["json"] == {
            "contents": [{"role": "user", "parts": [{"text": "hello"}]}]
        }
        assert body["choices"][0]["message"]["content"] == "完成"
        assert recorded[0]["usage"] == {
            "prompt_tokens": 4,
            "completion_tokens": 2,
            "total_tokens": 6,
            "model": "gemini-2.5-flash",
        }

    asyncio.run(run_test())


def test_gemini_streaming_returns_explicit_400(monkeypatch) -> None:
    async def run_test() -> None:
        recorded: list[dict] = []

        async def fake_record_usage(ctx, **kwargs) -> None:
            recorded.append(kwargs)

        monkeypatch.setattr(proxy, "_record_usage", fake_record_usage)
        client = FakeClient(httpx.Response(200, json={}, request=httpx.Request("POST", "https://example.com")))

        response = await proxy._handle_gemini_proxy(
            FakeRequest({
                "model": "gemini-2.5-flash",
                "stream": True,
                "messages": [{"role": "user", "content": "hello"}],
            }),
            "v1/chat/completions",
            SimpleNamespace(),
            client=client,
            base_url=None,
            api_key="real-key",
        )

        assert response.status_code == 400
        assert client.post_calls == []
        assert _json_response_body(response)["error"]["message"] == "Gemini proxy 暂不支持 stream=true"
        assert recorded[0]["error_message"] == "Gemini proxy 暂不支持 stream=true"

    asyncio.run(run_test())


def test_codex_branch_does_not_reference_removed_config_name() -> None:
    assert 'if config.key_source != "personal"' not in inspect.getsource(proxy.llm_proxy)
