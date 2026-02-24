import type { OpenClawRuntime } from "openclaw/plugin-sdk";

let _runtime: OpenClawRuntime | null = null;

export function setLearningRuntime(runtime: OpenClawRuntime): void {
  _runtime = runtime;
}

export function getLearningRuntime(): OpenClawRuntime {
  if (!_runtime) {
    throw new Error("Learning runtime not initialized");
  }
  return _runtime;
}
