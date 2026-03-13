import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import { emptyPluginConfigSchema } from "openclaw/plugin-sdk";
import { connect, disconnect, evaluateBefore, evaluateAfter } from "./src/ws-client.js";

const ENABLED = (process.env.SECURITY_LAYER_ENABLED ?? "true") !== "false";

const plugin = {
  id: "security-layer",
  name: "Security Layer",
  description: "Thin WebSocket client that delegates tool execution security to centralized backend",
  configSchema: emptyPluginConfigSchema(),

  register(api: OpenClawPluginApi) {
    if (!ENABLED) {
      console.error("[SecurityLayer] Disabled via SECURITY_LAYER_ENABLED=false");
      return;
    }

    connect();
    console.error("[SecurityLayer] Thin client registered, connecting to backend");

    api.on("before_tool_call", async (event) => {
      const result = await evaluateBefore({
        toolName: event.toolName,
        params: (event.params ?? {}) as Record<string, unknown>,
        runId: event.runId,
        toolCallId: event.toolCallId,
      });

      if (result.action === "deny") {
        return {
          block: true,
          blockReason: result.message ?? result.reason ?? "Blocked by security policy",
        };
      }

      if (result.action === "modify" && result.modifiedParams) {
        return { params: result.modifiedParams };
      }

      return {};
    });

    api.on("after_tool_call", async (event) => {
      await evaluateAfter(
        {
          toolName: event.toolName,
          params: (event.params ?? {}) as Record<string, unknown>,
          runId: event.runId,
          toolCallId: event.toolCallId,
        },
        {
          result: event.result,
          error: event.error,
          durationMs: event.durationMs,
        },
      );
    });
  },
};

export default plugin;
