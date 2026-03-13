import type { BeforeResult, AfterResult } from "./types.js";

type PendingResolve = (result: BeforeResult | AfterResult) => void;

let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let requestCounter = 0;
const pending = new Map<string, PendingResolve>();

const RECONNECT_DELAY_MS = 3000;

function getEndpoint(): string {
  const base = process.env.SECURITY_WS_ENDPOINT
    ?? process.env.NODESKCLAW_BACKEND_URL
    ?? "ws://localhost:8000";
  const url = base.replace(/^http/, "ws");
  const token = process.env.NODESKCLAW_API_TOKEN ?? "";
  return `${url}/api/v1/security/ws?token=${encodeURIComponent(token)}`;
}

export function connect(): void {
  if (ws) return;

  const endpoint = getEndpoint();
  console.error(`[SecurityLayer] Connecting to ${endpoint.split("?")[0]}`);

  try {
    ws = new WebSocket(endpoint);
  } catch {
    scheduleReconnect();
    return;
  }

  ws.onopen = () => {
    console.error("[SecurityLayer] WebSocket connected");
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(String(event.data)) as {
        type: string;
        id: string;
        result?: BeforeResult | AfterResult;
        decision_id?: string;
      };

      if (msg.type === "result" && msg.id && msg.result) {
        const resolve = pending.get(msg.id);
        if (resolve) {
          pending.delete(msg.id);
          resolve(msg.result);
        }
      }
    } catch {
      console.error("[SecurityLayer] Failed to parse WS message");
    }
  };

  ws.onclose = () => {
    ws = null;
    rejectAllPending("WebSocket disconnected");
    scheduleReconnect();
  };

  ws.onerror = () => {
    ws?.close();
  };
}

function scheduleReconnect(): void {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, RECONNECT_DELAY_MS);
}

function rejectAllPending(reason: string): void {
  for (const [id, resolve] of pending) {
    resolve({ action: "allow" } as BeforeResult);
  }
  pending.clear();
}

function nextId(): string {
  return `r-${++requestCounter}`;
}

export function evaluateBefore(ctx: {
  toolName: string;
  params: Record<string, unknown>;
  runId?: string;
  toolCallId?: string;
}): Promise<BeforeResult> {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    return Promise.resolve({ action: "allow" });
  }

  const id = nextId();

  return new Promise<BeforeResult>((resolve) => {
    pending.set(id, resolve as PendingResolve);

    ws!.send(JSON.stringify({
      type: "evaluate_before",
      id,
      ctx: {
        tool_name: ctx.toolName,
        params: ctx.params,
        agent_instance_id: process.env.AGENT_INSTANCE_ID ?? "",
        workspace_id: process.env.WORKSPACE_ID ?? "",
        timestamp: Date.now() / 1000,
      },
    }));
  });
}

export function evaluateAfter(ctx: {
  toolName: string;
  params: Record<string, unknown>;
  runId?: string;
  toolCallId?: string;
}, execResult: {
  result?: unknown;
  error?: string;
  durationMs?: number;
}): Promise<AfterResult> {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    return Promise.resolve({ action: "pass" });
  }

  const id = nextId();

  return new Promise<AfterResult>((resolve) => {
    pending.set(id, resolve as PendingResolve);

    ws!.send(JSON.stringify({
      type: "evaluate_after",
      id,
      ctx: {
        tool_name: ctx.toolName,
        params: ctx.params,
        agent_instance_id: process.env.AGENT_INSTANCE_ID ?? "",
        workspace_id: process.env.WORKSPACE_ID ?? "",
        timestamp: Date.now() / 1000,
      },
      exec_result: {
        result: typeof execResult.result === "string" ? execResult.result : JSON.stringify(execResult.result),
        error: execResult.error ?? null,
        duration_ms: execResult.durationMs ?? null,
      },
    }));
  });
}

export function disconnect(): void {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (ws) {
    ws.close();
    ws = null;
  }
  rejectAllPending("Shutting down");
}
