"""Container-side integration test for nanobot security layer.

Verifies:
1. WebSocket client connects to backend security endpoint
2. evaluate_before / evaluate_after protocol works end-to-end
3. Monkey-patch injector patches ToolRegistry.execute correctly

Run inside Docker container with:
  SECURITY_WS_ENDPOINT=ws://host.docker.internal:8000
  SECURITY_LAYER_ENABLED=true
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("security-test")

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        logger.info("[PASS] %s", name)
    else:
        FAIL += 1
        logger.error("[FAIL] %s — %s", name, detail or "condition not met")


async def test_ws_client_direct() -> None:
    """Test the ws_client module directly (no monkey-patching)."""
    from nanobot_security_layer.ws_client import connect, disconnect, evaluate_after, evaluate_before

    logger.info("--- Test 1: WebSocket client direct ---")

    await connect()
    await asyncio.sleep(1.0)

    from nanobot_security_layer import ws_client
    check("WS connected", ws_client._ws is not None, "ws_client._ws is None")

    result = await evaluate_before("exec", {"command": "ls -la"})
    check(
        "evaluate_before(ls) -> allow",
        result.action.value == "allow",
        f"got action={result.action.value}",
    )

    result = await evaluate_before("exec", {"command": "sudo rm -rf /"})
    logger.info("  evaluate_before(sudo rm) -> action=%s, message=%s", result.action.value, result.message)
    check(
        "evaluate_before(sudo rm) returns result",
        result.action.value in ("allow", "deny"),
        f"got action={result.action.value}",
    )

    result_after = await evaluate_after(
        "exec",
        {"command": "cat creds.txt"},
        exec_result="aws_access_key_id = AKIAIOSFODNN7EXAMPLE",
        duration_ms=10.0,
    )
    logger.info("  evaluate_after(aws key) -> action=%s", result_after.action.value)
    check(
        "evaluate_after returns result",
        result_after.action.value in ("pass", "redact", "flag"),
        f"got action={result_after.action.value}",
    )

    await disconnect()
    logger.info("  WS disconnected")


async def test_monkey_patch() -> None:
    """Test injector monkey-patches a mock ToolRegistry."""
    logger.info("--- Test 2: Monkey-patch injector ---")

    class MockToolRegistry:
        async def execute(self, name: str, params: dict) -> str:
            return f"executed {name} with {params}"

    import nanobot_security_layer.injector as injector

    original_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    import types
    mock_module = types.ModuleType("nanobot.agent.tools.registry")
    mock_module.ToolRegistry = MockToolRegistry
    sys.modules["nanobot.agent.tools.registry"] = mock_module

    from nanobot_security_layer.ws_client import connect
    await connect()
    await asyncio.sleep(0.5)

    if hasattr(MockToolRegistry.execute, "_security_patched"):
        MockToolRegistry.execute._security_patched = False

    from nanobot_security_layer.injector import inject_security_layer
    inject_security_layer()

    check(
        "ToolRegistry.execute patched",
        getattr(MockToolRegistry.execute, "_security_patched", False),
        "execute._security_patched is False",
    )

    registry = MockToolRegistry()
    result = await registry.execute("echo", {"command": "hello"})
    check(
        "Patched execute returns result",
        isinstance(result, str) and len(result) > 0,
        f"result={result!r}",
    )
    logger.info("  Patched execute returned: %s", result[:100])

    from nanobot_security_layer.ws_client import disconnect
    await disconnect()

    del sys.modules["nanobot.agent.tools.registry"]


async def main() -> None:
    endpoint = os.environ.get("SECURITY_WS_ENDPOINT", "ws://localhost:8000")
    enabled = os.environ.get("SECURITY_LAYER_ENABLED", "true")
    logger.info("Security WS endpoint: %s", endpoint)
    logger.info("Security layer enabled: %s", enabled)

    await test_ws_client_direct()
    await test_monkey_patch()

    logger.info("")
    logger.info("=" * 50)
    logger.info("Results: %d passed, %d failed", PASS, FAIL)
    logger.info("=" * 50)

    if FAIL > 0:
        sys.exit(1)
    logger.info("All tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
