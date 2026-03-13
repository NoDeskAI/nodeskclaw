import type {
  SecurityPlugin,
  ExecutionContext,
  ExecutionResult,
  BeforeResult,
  AfterResult,
  Finding,
} from "./types.js";

export class SecurityPipeline {
  private plugins: SecurityPlugin[] = [];

  addPlugin(plugin: SecurityPlugin): void {
    this.plugins.push(plugin);
    this.plugins.sort((a, b) => a.priority - b.priority);
  }

  async runBefore(ctx: ExecutionContext): Promise<BeforeResult> {
    const allFindings: Finding[] = [];

    for (const plugin of this.plugins) {
      if (!plugin.beforeExecute) continue;
      try {
        const result = await plugin.beforeExecute(ctx);
        if (result.findings) allFindings.push(...result.findings);

        if (result.action === "deny") {
          result.findings = allFindings;
          return result;
        }
        if (result.action === "modify" && result.modifiedParams) {
          Object.assign(ctx.params, result.modifiedParams);
        }
      } catch (err) {
        console.error(`[SecurityPipeline] Plugin '${plugin.id}' beforeExecute error:`, err);
      }
    }

    return { action: "allow", findings: allFindings.length ? allFindings : undefined };
  }

  async runAfter(ctx: ExecutionContext, execResult: ExecutionResult): Promise<AfterResult> {
    let finalAction: AfterResult["action"] = "pass";
    let finalMessage: string | undefined;
    let finalModifiedResult: string | undefined;
    let finalReason: string | undefined;
    const allFindings: Finding[] = [];

    for (const plugin of this.plugins) {
      if (!plugin.afterExecute) continue;
      try {
        const result = await plugin.afterExecute(ctx, execResult);
        if (result.findings) allFindings.push(...result.findings);

        if (result.action === "redact") {
          finalAction = "redact";
          finalReason = result.reason;
          finalMessage = result.message;
          if (result.modifiedResult !== undefined) {
            finalModifiedResult = result.modifiedResult;
            execResult = { ...execResult, result: result.modifiedResult };
          }
        } else if (result.action === "flag" && finalAction === "pass") {
          finalAction = "flag";
          finalReason = result.reason;
          finalMessage = result.message;
        }
      } catch (err) {
        console.error(`[SecurityPipeline] Plugin '${plugin.id}' afterExecute error:`, err);
      }
    }

    return {
      action: finalAction,
      reason: finalReason,
      message: finalMessage,
      modifiedResult: finalModifiedResult,
      findings: allFindings.length ? allFindings : undefined,
    };
  }

  async destroy(): Promise<void> {
    for (const plugin of this.plugins) {
      try {
        await plugin.destroy();
      } catch (err) {
        console.error(`[SecurityPipeline] Plugin '${plugin.id}' destroy error:`, err);
      }
    }
    this.plugins = [];
  }
}
