export interface BeforeResult {
  action: "allow" | "deny" | "modify";
  reason?: string;
  message?: string;
  modifiedParams?: Record<string, unknown>;
  findings?: Finding[];
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
