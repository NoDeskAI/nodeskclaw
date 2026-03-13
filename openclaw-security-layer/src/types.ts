export interface SecurityPlugin {
  id: string;
  priority: number;
  initialize(config: Record<string, unknown>): Promise<void>;
  destroy(): Promise<void>;
  beforeExecute?(ctx: ExecutionContext): Promise<BeforeResult>;
  afterExecute?(ctx: ExecutionContext, result: ExecutionResult): Promise<AfterResult>;
}

export interface ExecutionContext {
  toolName: string;
  params: Record<string, unknown>;
  sessionId?: string;
  runId?: string;
  toolCallId?: string;
  timestamp: number;
  metadata: Record<string, unknown>;
}

export interface BeforeResult {
  action: "allow" | "deny" | "modify";
  reason?: string;
  message?: string;
  modifiedParams?: Record<string, unknown>;
  findings?: Finding[];
}

export interface ExecutionResult {
  result?: unknown;
  error?: string;
  durationMs?: number;
}

export interface AfterResult {
  action: "pass" | "redact" | "flag";
  reason?: string;
  message?: string;
  modifiedResult?: string;
  findings?: Finding[];
}

export interface Finding {
  pluginId: string;
  category: string;
  severity: "critical" | "high" | "medium" | "low";
  message: string;
  detail?: Record<string, unknown>;
}

export interface SecurityConfig {
  plugins: PluginEntry[];
}

export interface PluginEntry {
  id: string;
  enabled: boolean;
  priority: number;
  config?: Record<string, unknown>;
}
