import * as fs from "node:fs";
import * as path from "node:path";
import type { SecurityConfig, SecurityPlugin, PluginEntry } from "./types.js";
import { PolicyGatePlugin } from "./plugins/policy-gate.js";

const DEFAULT_CONFIG_PATHS = [
  "/root/.openclaw/config/security-policy.json",
  path.join(process.env.HOME ?? "", ".openclaw/config/security-policy.json"),
];

const BUILTIN_FACTORIES: Record<string, () => SecurityPlugin> = {
  "policy-gate": () => new PolicyGatePlugin(),
};

export function loadSecurityConfig(): SecurityConfig {
  const configPath = process.env.SECURITY_POLICY_PATH
    ?? DEFAULT_CONFIG_PATHS.find((p) => fs.existsSync(p));

  if (!configPath || !fs.existsSync(configPath)) {
    console.error("[SecurityLayer] No security config found, pipeline will have no plugins");
    return { plugins: [] };
  }

  try {
    const raw = fs.readFileSync(configPath, "utf-8");
    const config = JSON.parse(raw) as SecurityConfig;
    console.error(`[SecurityLayer] Loaded config from ${configPath} (${config.plugins.length} plugin entries)`);
    return config;
  } catch (err) {
    console.error("[SecurityLayer] Failed to parse security config:", err);
    return { plugins: [] };
  }
}

export async function createPlugins(config: SecurityConfig): Promise<SecurityPlugin[]> {
  const plugins: SecurityPlugin[] = [];

  for (const entry of config.plugins) {
    if (!entry.enabled) continue;

    const factory = BUILTIN_FACTORIES[entry.id];
    if (!factory) {
      console.error(`[SecurityLayer] Unknown plugin '${entry.id}', skipping`);
      continue;
    }

    try {
      const plugin = factory();
      plugin.priority = entry.priority;
      await plugin.initialize(entry.config ?? {});
      plugins.push(plugin);
      console.error(`[SecurityLayer] Plugin '${entry.id}' initialized (priority=${entry.priority})`);
    } catch (err) {
      console.error(`[SecurityLayer] Failed to initialize plugin '${entry.id}':`, err);
    }
  }

  return plugins;
}
