import type {
  SecurityPlugin,
  ExecutionContext,
  ExecutionResult,
  BeforeResult,
  AfterResult,
  Finding,
} from "../types.js";

interface ToolRule {
  action: "allow" | "deny";
  denied_paths?: string[];
  allowed_paths?: string[];
  denied_commands?: RegExp[];
  allowed_domains?: string[];
  denied_domains?: string[];
}

interface PolicyGateConfig {
  mode?: "enforce" | "monitor" | "disable";
  tools?: Record<string, {
    action?: string;
    denied_paths?: string[];
    allowed_paths?: string[];
    denied_commands?: string[];
    allowed_domains?: string[];
    denied_domains?: string[];
  }>;
}

export class PolicyGatePlugin implements SecurityPlugin {
  id = "policy-gate";
  priority = 10;

  private mode: "enforce" | "monitor" | "disable" = "monitor";
  private rules: Record<string, ToolRule> = {};

  async initialize(config: Record<string, unknown>): Promise<void> {
    const c = config as unknown as PolicyGateConfig;
    this.mode = c.mode ?? "monitor";

    if (c.tools) {
      for (const [toolName, rule] of Object.entries(c.tools)) {
        this.rules[toolName] = {
          action: (rule.action as ToolRule["action"]) ?? "allow",
          denied_paths: rule.denied_paths,
          allowed_paths: rule.allowed_paths,
          denied_commands: rule.denied_commands?.map((p) => new RegExp(p)),
          allowed_domains: rule.allowed_domains,
          denied_domains: rule.denied_domains,
        };
      }
    }
  }

  async destroy(): Promise<void> {}

  async beforeExecute(ctx: ExecutionContext): Promise<BeforeResult> {
    if (this.mode === "disable") return { action: "allow" };

    const rule = this.rules[ctx.toolName];
    if (!rule) return { action: "allow" };

    if (rule.action === "deny") {
      return this.deny(ctx.toolName, `Tool '${ctx.toolName}' is denied by policy`);
    }

    const violation = this.checkParams(ctx.toolName, ctx.params, rule);
    if (violation) return this.deny(ctx.toolName, violation);

    return { action: "allow" };
  }

  private checkParams(toolName: string, params: Record<string, unknown>, rule: ToolRule): string | null {
    if (toolName === "exec" || toolName === "execute_command") {
      const cmd = String(params.command ?? params.cmd ?? "");
      if (rule.denied_commands) {
        for (const pattern of rule.denied_commands) {
          if (pattern.test(cmd)) {
            return `Command matches denied pattern: ${pattern.source}`;
          }
        }
      }
    }

    if (["read_file", "write_file", "edit_file"].includes(toolName)) {
      const filePath = String(params.path ?? params.file_path ?? "");
      if (rule.denied_paths) {
        for (const pattern of rule.denied_paths) {
          if (pathMatches(filePath, pattern)) {
            return `Path '${filePath}' matches denied pattern: ${pattern}`;
          }
        }
      }
    }

    return null;
  }

  private deny(toolName: string, reason: string): BeforeResult {
    const finding: Finding = {
      pluginId: this.id,
      category: "POLICY_VIOLATION",
      severity: "high",
      message: reason,
    };

    if (this.mode === "monitor") {
      console.error(`[policy-gate] [monitor] ${toolName} -> ${reason}`);
      return { action: "allow", findings: [finding] };
    }

    return {
      action: "deny",
      reason,
      message: `Security policy: ${reason}. Try a different approach.`,
      findings: [finding],
    };
  }
}

function pathMatches(filePath: string, pattern: string): boolean {
  if (pattern.startsWith("**/")) {
    const suffix = pattern.slice(3);
    return filePath.endsWith(suffix) || filePath.includes(`/${suffix}`);
  }
  if (pattern.includes("*")) {
    const regex = new RegExp("^" + pattern.replace(/\*/g, ".*") + "$");
    return regex.test(filePath);
  }
  return filePath === pattern || filePath.endsWith(`/${pattern}`);
}
