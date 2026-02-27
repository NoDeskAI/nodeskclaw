import type { PluginRuntime } from "openclaw/plugin-sdk";

let runtime: PluginRuntime | null = null;

export function setNoDeskClawRuntime(next: PluginRuntime) {
  runtime = next;
}

export function getNoDeskClawRuntime(): PluginRuntime {
  if (!runtime) {
    throw new Error("NoDeskClaw runtime not initialized");
  }
  return runtime;
}
