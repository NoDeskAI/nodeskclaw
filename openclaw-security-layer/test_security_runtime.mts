/**
 * Container-side integration test for OpenClaw security layer.
 *
 * Verifies:
 * 1. WebSocket client connects to backend security endpoint
 * 2. evaluateBefore / evaluateAfter protocol works end-to-end
 * 3. Plugin hook registration wires up correctly
 *
 * Run inside Docker container with:
 *   SECURITY_WS_ENDPOINT=ws://host.docker.internal:8000
 *   SECURITY_LAYER_ENABLED=true
 */

import { connect, disconnect, evaluateBefore, evaluateAfter } from "./src/ws-client.js";

let PASS = 0;
let FAIL = 0;

function check(name: string, ok: boolean, detail = "") {
  if (ok) {
    PASS++;
    console.log(`[PASS] ${name}`);
  } else {
    FAIL++;
    console.error(`[FAIL] ${name} — ${detail || "condition not met"}`);
  }
}

function sleep(ms: number) {
  return new Promise<void>((r) => setTimeout(r, ms));
}

async function testWsClientDirect() {
  console.log("--- Test 1: WebSocket client direct ---");

  connect();
  await sleep(2000);

  const afterResult = await evaluateAfter(
    { toolName: "exec", params: { command: "cat creds.txt" } },
    { result: "aws_access_key_id = AKIAIOSFODNN7EXAMPLE", durationMs: 10 },
  );
  console.log(`  evaluate_after(aws key) -> action=${afterResult.action}`);
  check(
    "WS connected (via DLP flag)",
    afterResult.action === "flag",
    `got '${afterResult.action}', expected 'flag'`,
  );

  const r1 = await evaluateBefore({
    toolName: "exec",
    params: { command: "ls -la" },
  });
  check("evaluate_before(ls) -> allow", r1.action === "allow", `got action=${r1.action}`);

  const r2 = await evaluateBefore({
    toolName: "exec",
    params: { command: "sudo rm -rf /" },
  });
  console.log(`  evaluate_before(sudo rm) -> action=${r2.action}, message=${r2.message}`);
  check(
    "evaluate_before(sudo rm) returns result",
    r2.action === "allow" || r2.action === "deny",
    `got action=${r2.action}`,
  );

  disconnect();
  console.log("  WS disconnected");
}

async function testPluginHooks() {
  console.log("--- Test 2: Plugin hook simulation ---");

  connect();
  await sleep(1500);

  const handlers: Record<string, ((...args: unknown[]) => unknown)[]> = {};
  const mockApi = {
    on(event: string, handler: (...args: unknown[]) => unknown) {
      if (!handlers[event]) handlers[event] = [];
      handlers[event].push(handler);
    },
  };

  mockApi.on("before_tool_call", async (event: any) => {
    const result = await evaluateBefore({
      toolName: event.toolName,
      params: (event.params ?? {}) as Record<string, unknown>,
    });
    if (result.action === "deny") {
      return { block: true, blockReason: result.message ?? "Blocked" };
    }
    if (result.action === "modify" && result.modifiedParams) {
      return { params: result.modifiedParams };
    }
    return {};
  });

  mockApi.on("after_tool_call", async (event: any) => {
    await evaluateAfter(
      { toolName: event.toolName, params: (event.params ?? {}) as Record<string, unknown> },
      { result: event.result, error: event.error, durationMs: event.durationMs },
    );
  });

  check(
    "Plugin hooks registered",
    (handlers["before_tool_call"]?.length ?? 0) > 0 &&
      (handlers["after_tool_call"]?.length ?? 0) > 0,
    "hooks not registered",
  );

  const hookResult = await (handlers["before_tool_call"][0] as Function)({
    toolName: "echo",
    params: { command: "hello" },
  });
  check("before_tool_call hook returns result", hookResult != null, "hook returned null");
  console.log(`  Hook result: ${JSON.stringify(hookResult)}`);

  disconnect();
}

async function main() {
  const endpoint = process.env.SECURITY_WS_ENDPOINT ?? "ws://localhost:8000";
  const enabled = process.env.SECURITY_LAYER_ENABLED ?? "true";
  console.log(`Security WS endpoint: ${endpoint}`);
  console.log(`Security layer enabled: ${enabled}`);

  await testWsClientDirect();
  await testPluginHooks();

  console.log("");
  console.log("=".repeat(50));
  console.log(`Results: ${PASS} passed, ${FAIL} failed`);
  console.log("=".repeat(50));

  if (FAIL > 0) process.exit(1);
  console.log("All tests passed.");
}

main().catch((err) => {
  console.error("Fatal:", err);
  process.exit(2);
});
