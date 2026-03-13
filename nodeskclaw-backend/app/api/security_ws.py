"""WebSocket endpoint for tool execution security evaluation.

Runtime security layers (OpenClaw, nanobot, ZeroClaw) connect here and send
evaluate_before / evaluate_after requests. The pipeline runs all registered
plugins and returns results (or pending + deferred result for approval flows).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.security.pipeline import SecurityPipeline
from app.services.security.types import ExecutionContext, ExecutionResult

logger = logging.getLogger(__name__)

router = APIRouter()

_pipeline: SecurityPipeline | None = None


def set_pipeline(pipeline: SecurityPipeline) -> None:
    global _pipeline
    _pipeline = pipeline


def get_pipeline() -> SecurityPipeline | None:
    return _pipeline


def _parse_ctx(raw: dict[str, Any]) -> ExecutionContext:
    return ExecutionContext(
        tool_name=raw.get("tool_name", ""),
        params=raw.get("params", {}),
        agent_instance_id=raw.get("agent_instance_id", ""),
        workspace_id=raw.get("workspace_id", ""),
        timestamp=raw.get("timestamp", 0.0),
        metadata=raw.get("metadata", {}),
    )


def _parse_exec_result(raw: dict[str, Any] | None) -> ExecutionResult:
    if not raw:
        return ExecutionResult()
    return ExecutionResult(
        result=raw.get("result"),
        error=raw.get("error"),
        duration_ms=raw.get("duration_ms"),
    )


@router.websocket("/security/ws")
async def security_ws(websocket: WebSocket, token: str = ""):
    pipeline = get_pipeline()
    if pipeline is None:
        await websocket.close(code=1011, reason="Security pipeline not initialized")
        return

    await websocket.accept()
    logger.info("Security WS connected (agent_token=%s...)", token[:8] if token else "none")

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from security WS client")
                continue

            msg_type = msg.get("type")
            msg_id = msg.get("id")

            if not msg_type or not msg_id:
                continue

            if msg_type == "evaluate_before":
                ctx = _parse_ctx(msg.get("ctx", {}))
                result = await pipeline.run_before(ctx)
                await websocket.send_text(json.dumps({
                    "type": "result",
                    "id": msg_id,
                    "result": result.to_dict(),
                }))

            elif msg_type == "evaluate_after":
                ctx = _parse_ctx(msg.get("ctx", {}))
                exec_result = _parse_exec_result(msg.get("exec_result"))
                result = await pipeline.run_after(ctx, exec_result)
                await websocket.send_text(json.dumps({
                    "type": "result",
                    "id": msg_id,
                    "result": result.to_dict(),
                }))

    except WebSocketDisconnect:
        logger.info("Security WS disconnected")
    except Exception:
        logger.exception("Security WS error")
