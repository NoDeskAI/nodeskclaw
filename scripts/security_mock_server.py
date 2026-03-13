"""Minimal WebSocket server for local security layer testing.

Only starts the security WS endpoint + Pipeline with built-in plugins.
No database, no EE modules, no alembic — zero external dependencies.

Usage:
    cd nodeskclaw-backend
    uv run python ../scripts/security_mock_server.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parent.parent / "nodeskclaw-backend"
sys.path.insert(0, str(backend_root))

from app.services.security.pipeline import SecurityPipeline  # noqa: E402
from app.services.security.loader import create_plugins  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s")
logger = logging.getLogger("security-mock-server")

from app.services.security.types import ExecutionContext, ExecutionResult  # noqa: E402


def _parse_ctx(raw: dict) -> ExecutionContext:
    return ExecutionContext(
        tool_name=raw.get("tool_name", ""),
        params=raw.get("params", {}),
        agent_instance_id=raw.get("agent_instance_id", ""),
        workspace_id=raw.get("workspace_id", ""),
        timestamp=raw.get("timestamp", 0.0),
        metadata=raw.get("metadata", {}),
    )


def _parse_exec_result(raw: dict | None) -> ExecutionResult:
    if not raw:
        return ExecutionResult()
    return ExecutionResult(
        result=raw.get("result"),
        error=raw.get("error"),
        duration_ms=raw.get("duration_ms"),
    )


async def main() -> None:
    try:
        import websockets
    except ImportError:
        logger.error("websockets not installed: pip install websockets")
        return

    pipeline = SecurityPipeline()
    plugins = await create_plugins([
        {"id": "policy-gate", "config": {
            "mode": "enforce",
            "command_blacklist": ["rm -rf /", "sudo rm"],
        }},
        {"id": "dlp-scanner", "config": {
            "mode": "flag",
            "patterns": [
                {"name": "aws_key", "pattern": r"AKIA[0-9A-Z]{16}", "severity": "high"},
            ],
        }},
    ])
    for p in plugins:
        pipeline.add_plugin(p)
    logger.info("Pipeline ready with %d plugins", pipeline.plugin_count)

    async def handler(ws: websockets.WebSocketServerProtocol) -> None:
        logger.info("Client connected from %s", ws.remote_address)
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type")
                msg_id = msg.get("id")
                if not msg_type or not msg_id:
                    continue

                if msg_type == "evaluate_before":
                    ctx = _parse_ctx(msg.get("ctx", {}))
                    result = await pipeline.run_before(ctx)
                    await ws.send(json.dumps({
                        "type": "result",
                        "id": msg_id,
                        "result": result.to_dict(),
                    }))
                elif msg_type == "evaluate_after":
                    ctx = _parse_ctx(msg.get("ctx", {}))
                    exec_result = _parse_exec_result(msg.get("exec_result"))
                    result = await pipeline.run_after(ctx, exec_result)
                    await ws.send(json.dumps({
                        "type": "result",
                        "id": msg_id,
                        "result": result.to_dict(),
                    }))
        except websockets.ConnectionClosed:
            logger.info("Client disconnected")

    host = "0.0.0.0"
    port = 8000
    logger.info("Starting security mock server on ws://%s:%d/api/v1/security/ws", host, port)

    stop = asyncio.get_event_loop().create_future()

    async with websockets.serve(handler, host, port):
        logger.info("Server ready — waiting for connections")
        await stop


if __name__ == "__main__":
    asyncio.run(main())
