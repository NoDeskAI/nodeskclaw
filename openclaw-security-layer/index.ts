import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import { emptyPluginConfigSchema } from "openclaw/plugin-sdk";
import { SecurityPipeline } from "./src/pipeline.js";
import { loadSecurityConfig, createPlugins } from "./src/loader.js";
import type { ExecutionContext, ExecutionResult } from "./src/types.js";

let pipeline: SecurityPipeline | null = null;

const plugin = {
  id: "security-layer",
  name: "Security Layer",
  description: "Tool execution security pipeline: policy gate, DLP, audit, approval",
  configSchema: emptyPluginConfigSchema(),

  register(api: OpenClawPluginApi) {
    const config = loadSecurityConfig();
    pipeline = new SecurityPipeline();

    createPlugins(config)
      .then((plugins) => {
        for (const p of plugins) pipeline!.addPlugin(p);
        console.error(`[SecurityLayer] Pipeline ready (${plugins.length} plugins active)`);
      })
      .catch((err) => {
        console.error("[SecurityLayer] Failed to initialize pipeline:", err);
      });

    api.on("before_tool_call", async (event) => {
      if (!pipeline) return {};

      const ctx: ExecutionContext = {
        toolName: event.toolName,
        params: (event.params ?? {}) as Record<string, unknown>,
        runId: event.runId,
        toolCallId: event.toolCallId,
        timestamp: Date.now(),
        metadata: {},
      };

      const result = await pipeline.runBefore(ctx);

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
      if (!pipeline) return;

      const ctx: ExecutionContext = {
        toolName: event.toolName,
        params: (event.params ?? {}) as Record<string, unknown>,
        runId: event.runId,
        toolCallId: event.toolCallId,
        timestamp: Date.now(),
        metadata: {},
      };

      const execResult: ExecutionResult = {
        result: event.result,
        error: event.error,
        durationMs: event.durationMs,
      };

      await pipeline.runAfter(ctx, execResult);
    });
  },
};

export default plugin;
