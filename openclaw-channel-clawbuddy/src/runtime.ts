import type { PluginRuntime } from "openclaw/plugin-sdk";

let runtime: PluginRuntime | null = null;

export function setClawBuddyRuntime(next: PluginRuntime) {
  runtime = next;
}

export function getClawBuddyRuntime(): PluginRuntime {
  if (!runtime) {
    throw new Error("ClawBuddy runtime not initialized");
  }
  return runtime;
}
