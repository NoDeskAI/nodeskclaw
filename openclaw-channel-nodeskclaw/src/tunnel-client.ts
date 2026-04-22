import type { OpenClawConfig } from "openclaw/plugin-sdk";
import type { CollaborationPayload } from "./types.js";

const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;
const PONG_TIMEOUT_MS = 45_000;
const GATEWAY_PORT_DEFAULT = 3000;

interface TunnelMessage {
  id: string;
  type: string;
  replyTo?: string;
  traceId?: string;
  payload: Record<string, unknown>;
  ts: number;
}

type LearningWebhookHandler = (body: unknown) => { ok: boolean };

export interface TunnelCallbacks {
  onAuthOk?: () => void;
  onAuthError?: (reason: string) => void;
  onClose?: (code: number, reason: string) => void;
  onReconnecting?: (attempt: number) => void;
}

let _instance: TunnelClient | null = null;

export function getTunnelClient(): TunnelClient {
  if (!_instance) throw new Error("TunnelClient not started");
  return _instance;
}

export function isProtocolDowngraded(): boolean {
  return _instance?.downgraded ?? false;
}

function deriveTunnelUrl(apiUrl: string): string {
  const wsUrl = apiUrl
    .replace(/^https:\/\//, "wss://")
    .replace(/^http:\/\//, "ws://")
    .replace(/\/+$/, "");
  return `${wsUrl}/tunnel/connect`;
}

const LOCAL_GATEWAY_MODELS = ["openclaw", "openclaw/default", "openclaw/main"];

function deriveDefaultChatModel(cfg: OpenClawConfig): string {
  const agents = (cfg as Record<string, unknown>).agents as Record<string, unknown> | undefined;
  const defaults = agents?.defaults as Record<string, unknown> | undefined;
  const model = defaults?.model;

  let modelName = "";
  if (typeof model === "string" && model.trim()) {
    modelName = model.trim();
  } else if (model && typeof model === "object") {
    const primary = (model as Record<string, unknown>).primary;
    if (typeof primary === "string" && primary.trim()) {
      modelName = primary.trim();
    }
  }

  // If model contains "/" it's provider/model format (e.g. "minimax-anthropic/MiniMax-M2.7")
  // which is not valid for local OpenClaw Gateway - map to openclaw/main
  if (modelName && (!LOCAL_GATEWAY_MODELS.includes(modelName))) {
    console.log("[tunnel] Model '%s' not in local gateway models, using 'openclaw/main'", modelName);
    return "openclaw/main";
  }

  return modelName || process.env.OPENCLAW_DEFAULT_MODEL || "openclaw/main";
}

export function startTunnelClient(cfg: OpenClawConfig, callbacks?: TunnelCallbacks): TunnelClient {
  if (_instance) {
    console.log("[tunnel] Shutting down previous TunnelClient before re-init");
    _instance.disconnect();
    _instance = null;
  }

  const section = (cfg as Record<string, unknown>).channels?.["nodeskclaw"] as
    | Record<string, unknown>
    | undefined;

  const accounts = (section?.accounts ?? {}) as Record<
    string,
    { instanceId?: string; apiToken?: string; apiUrl?: string }
  >;
  const defaultAccount = accounts["default"];

  const explicitUrl = (section?.tunnelUrl as string) ?? "";
  const apiUrl = defaultAccount?.apiUrl ?? "";
  const tunnelUrl = explicitUrl || (apiUrl ? deriveTunnelUrl(apiUrl) : "");

  const instanceId = defaultAccount?.instanceId ?? "";
  const token = defaultAccount?.apiToken ?? "";
  const defaultChatModel = deriveDefaultChatModel(cfg);

  if (!tunnelUrl || !instanceId || !token) {
    console.warn(
      "[tunnel] Missing config — tunnelUrl=%s instanceId=%s token=%s",
      tunnelUrl ? "set" : "MISSING",
      instanceId ? "set" : "MISSING",
      token ? "set" : "MISSING",
    );
    _instance = new TunnelClient(
      tunnelUrl,
      instanceId,
      token,
      defaultChatModel,
      callbacks,
    );
    return _instance;
  }

  if (!explicitUrl) {
    console.log("[tunnel] Derived tunnelUrl from apiUrl: %s", tunnelUrl);
  }

  _instance = new TunnelClient(
    tunnelUrl,
    instanceId,
    token,
    defaultChatModel,
    callbacks,
  );
  _instance.connect();
  return _instance;
}

const SEND_BUFFER_MAX = 64;

export class TunnelClient {
  private ws: WebSocket | null = null;
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private lastPong = Date.now();
  private pingCheckTimer: ReturnType<typeof setInterval> | null = null;
  private closed = false;
  private _protocolDowngraded = false;
  private learningHandler: LearningWebhookHandler | null = null;
  private sendBuffer: TunnelMessage[] = [];

  get downgraded(): boolean {
    return this._protocolDowngraded;
  }

  constructor(
    private backendUrl: string,
    private instanceId: string,
    private token: string,
    private defaultChatModel: string,
    private callbacks?: TunnelCallbacks,
  ) {}

  setLearningHandler(handler: LearningWebhookHandler): void {
    this.learningHandler = handler;
  }

  connect(): void {
    if (this.closed || !this.backendUrl) return;

    try {
      this.ws = new WebSocket(this.backendUrl);
    } catch (err) {
      console.error("[tunnel] WebSocket creation failed:", err);
      this.scheduleReconnect();
      return;
    }

    const ws = this.ws;

    ws.addEventListener("open", () => {
      if (this.ws !== ws) return;
      console.log("[tunnel] Connected, sending auth...");
      this.send({
        id: crypto.randomUUID(),
        type: "auth",
        payload: { instance_id: this.instanceId, token: this.token },
        ts: Date.now(),
      });
    });

    ws.addEventListener("message", (event) => {
      if (this.ws !== ws) return;
      try {
        const msg: TunnelMessage =
          typeof event.data === "string"
            ? JSON.parse(event.data)
            : event.data;
        this.handleMessage(msg);
      } catch (err) {
        console.error("[tunnel] Failed to parse message:", err);
      }
    });

    ws.addEventListener("close", (event) => {
      if (this.ws !== ws) {
        console.debug("[tunnel] Ignoring close on superseded WebSocket");
        return;
      }
      console.warn(
        "[tunnel] Connection closed: code=%d reason=%s",
        event.code,
        event.reason,
      );
      this.callbacks?.onClose?.(event.code, event.reason);
      this.cleanup();
      if (!this.closed) this.scheduleReconnect();
    });

    ws.addEventListener("error", (err) => {
      if (this.ws !== ws) return;
      console.error("[tunnel] WebSocket error:", err);
      setTimeout(() => {
        if (this.ws === ws && !this.closed) {
          console.warn("[tunnel] No close event after error, forcing reconnect");
          this.cleanup();
          this.scheduleReconnect();
        }
      }, 3000);
    });
  }

  disconnect(): void {
    this.closed = true;
    this.cleanup();
    if (this.ws) {
      try {
        this.ws.close(1000, "client_shutdown");
      } catch {}
      this.ws = null;
    }
  }

  send(msg: TunnelMessage): void {
    const current = _instance;
    if (current && current !== this && current.ws?.readyState === WebSocket.OPEN) {
      current.send(msg);
      return;
    }
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      if (msg.type !== "auth" && this.sendBuffer.length < SEND_BUFFER_MAX) {
        this.sendBuffer.push(msg);
        console.debug(
          "[tunnel] Buffered message (type=%s, buffered=%d)",
          msg.type,
          this.sendBuffer.length,
        );
      } else if (this.sendBuffer.length >= SEND_BUFFER_MAX) {
        console.warn("[tunnel] Send buffer full, dropping message type=%s", msg.type);
      }
      return;
    }
    const data: Record<string, unknown> = {
      id: msg.id,
      type: msg.type,
      payload: msg.payload,
      ts: msg.ts,
    };
    if (msg.replyTo) data.replyTo = msg.replyTo;
    if (msg.traceId) data.traceId = msg.traceId;
    this.ws.send(JSON.stringify(data));
  }

  private flushSendBuffer(): void {
    if (this.sendBuffer.length === 0) return;
    console.log("[tunnel] Flushing %d buffered messages", this.sendBuffer.length);
    const pending = this.sendBuffer.splice(0);
    for (const msg of pending) {
      this.send(msg);
    }
  }

  sendCollaboration(payload: CollaborationPayload): void {
    this.send({
      id: crypto.randomUUID(),
      type: "collaboration.message",
      payload: payload as unknown as Record<string, unknown>,
      ts: Date.now(),
    });
  }

  private handleMessage(msg: TunnelMessage): void {
    switch (msg.type) {
      case "auth.ok":
        console.log("[tunnel] Authenticated successfully");
        this.reconnectAttempt = 0;
        this.lastPong = Date.now();
        this.startPingCheck();
        this.flushSendBuffer();
        this.callbacks?.onAuthOk?.();
        break;

      case "auth.error": {
        const reason = String(msg.payload?.reason ?? "unknown");
        console.error("[tunnel] Auth failed:", reason);
        this.closed = true;
        this.ws?.close();
        this.callbacks?.onAuthError?.(reason);
        break;
      }

      case "ping":
        this.send({
          id: crypto.randomUUID(),
          type: "pong",
          payload: {},
          ts: Date.now(),
        });
        this.lastPong = Date.now();
        break;

      case "chat.request":
        this.handleChatRequest(msg);
        break;

      case "chat.cancel":
        console.log("[tunnel] Chat cancel received for:", msg.payload?.id);
        break;

      case "learning.task":
        this.handleLearningTask(msg);
        break;

      case "config.push":
        console.log("[tunnel] Config push received:", msg.payload);
        break;

      default:
        console.warn("[tunnel] Unknown message type:", msg.type);
    }
  }

  private async handleChatRequest(msg: TunnelMessage): Promise<void> {
    const gatewayPort =
      parseInt(process.env.OPENCLAW_GATEWAY_PORT ?? "", 10) ||
      GATEWAY_PORT_DEFAULT;
    const url = `http://localhost:${gatewayPort}/v1/chat/completions`;

    const messages = msg.payload.messages as Array<{
      role: string;
      content: string;
    }>;
    const sessionKey = msg.payload.workspace_id
      ? `workspace:${msg.payload.workspace_id}`
      : undefined;

    if (msg.payload.no_reply === true) {
      fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.token}`,
          ...(sessionKey ? { "X-OpenClaw-Session-Key": sessionKey } : {}),
        },
        body: JSON.stringify({
          model: this.defaultChatModel,
          messages,
          stream: false,
          max_tokens: 1,
        }),
      }).catch((e) => {
        console.debug("[tunnel] no_reply context injection failed:", e);
      });
      this.send({
        id: crypto.randomUUID(),
        type: "chat.response.done",
        replyTo: msg.id,
        traceId: msg.traceId,
        payload: {},
        ts: Date.now(),
      });
      return;
    }

    try {
      const resp = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.token}`,
          ...(sessionKey
            ? { "X-OpenClaw-Session-Key": sessionKey }
            : {}),
        },
        body: JSON.stringify({
          model: this.defaultChatModel,
          messages,
          stream: true,
        }),
      });

      if (!resp.ok || !resp.body) {
        let errorMsg = `OpenClaw API returned ${resp.status}`;
        let rawBody: string | undefined;
        try {
          rawBody = await resp.text();
          const body = JSON.parse(rawBody);
          const detail =
            typeof body?.error === "object"
              ? body.error.message ?? JSON.stringify(body.error)
              : typeof body?.error === "string"
                ? body.error
                : undefined;
          if (detail) errorMsg = `OpenClaw API ${resp.status}: ${detail}`;
        } catch {
          /* body unreadable or not JSON — keep default message */
        }
        const payload: Record<string, string> = {
          error: errorMsg,
          error_type: "llm",
        };
        if (rawBody) payload.error_raw = rawBody;
        this.send({
          id: crypto.randomUUID(),
          type: "chat.response.error",
          replyTo: msg.id,
          traceId: msg.traceId,
          payload,
          ts: Date.now(),
        });
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let dataAccum = "";
      let hasContent = false;
      let lastError: string | undefined;

      const sendDoneOrError = () => {
        if (hasContent) {
          this.send({
            id: crypto.randomUUID(),
            type: "chat.response.done",
            replyTo: msg.id,
            traceId: msg.traceId,
            payload: {},
            ts: Date.now(),
          });
        } else {
          this.send({
            id: crypto.randomUUID(),
            type: "chat.response.error",
            replyTo: msg.id,
            traceId: msg.traceId,
            payload: {
              error: lastError || "empty_response",
              error_type: "llm",
            },
            ts: Date.now(),
          });
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const part = line.slice(6);
            dataAccum = dataAccum ? dataAccum + "\n" + part : part;
            continue;
          }
          if (line.trim() === "" && dataAccum) {
            if (dataAccum === "[DONE]") {
              sendDoneOrError();
              return;
            }
            try {
              const chunk = JSON.parse(dataAccum);
              if (chunk?.error && !lastError) {
                lastError =
                  typeof chunk.error === "object"
                    ? chunk.error.message ?? JSON.stringify(chunk.error)
                    : String(chunk.error);
              }
              const content =
                chunk?.choices?.[0]?.delta?.content ?? "";
              if (content) {
                hasContent = true;
                this.send({
                  id: crypto.randomUUID(),
                  type: "chat.response.chunk",
                  replyTo: msg.id,
                  traceId: msg.traceId,
                  payload: { content },
                  ts: Date.now(),
                });
              }
            } catch (e) {
              console.debug("[tunnel] SSE data parse failed:", e, dataAccum.slice(0, 200));
            }
            dataAccum = "";
          }
        }
      }

      if (dataAccum && dataAccum !== "[DONE]") {
        try {
          const chunk = JSON.parse(dataAccum);
          if (chunk?.error && !lastError) {
            lastError =
              typeof chunk.error === "object"
                ? chunk.error.message ?? JSON.stringify(chunk.error)
                : String(chunk.error);
          }
          const content = chunk?.choices?.[0]?.delta?.content ?? "";
          if (content) {
            hasContent = true;
            this.send({
              id: crypto.randomUUID(),
              type: "chat.response.chunk",
              replyTo: msg.id,
              traceId: msg.traceId,
              payload: { content },
              ts: Date.now(),
            });
          }
        } catch (e) {
          console.debug("[tunnel] SSE trailing data parse failed:", e, dataAccum.slice(0, 200));
        }
      }

      sendDoneOrError();
    } catch (err) {
      console.error("[tunnel] chat.request failed:", err);
      this.send({
        id: crypto.randomUUID(),
        type: "chat.response.error",
        replyTo: msg.id,
        traceId: msg.traceId,
        payload: {
          error: err instanceof Error ? err.message : String(err),
        },
        ts: Date.now(),
      });
    }
  }

  private handleLearningTask(msg: TunnelMessage): void {
    if (this.learningHandler) {
      try {
        this.learningHandler(msg.payload);
        console.log(
          "[tunnel] Learning task processed (mode=%s)",
          (msg.payload as Record<string, unknown>).mode ?? "?",
        );
      } catch (err) {
        console.error("[tunnel] Learning task handler error:", err);
      }
    } else {
      console.warn("[tunnel] No learning handler registered, ignoring task");
    }
  }

  private startPingCheck(): void {
    if (this.pingCheckTimer) clearInterval(this.pingCheckTimer);
    this.pingCheckTimer = setInterval(() => {
      if (Date.now() - this.lastPong > PONG_TIMEOUT_MS) {
        console.warn("[tunnel] Ping timeout, reconnecting...");
        this.ws?.close(4020, "ping_timeout");
      }
    }, 15_000);
  }

  private scheduleReconnect(): void {
    if (this.closed) return;

    const delay = Math.min(
      RECONNECT_BASE_MS * 2 ** this.reconnectAttempt,
      RECONNECT_MAX_MS,
    );
    this.reconnectAttempt++;
    console.log(
      "[tunnel] Reconnecting in %dms (attempt #%d)",
      delay,
      this.reconnectAttempt,
    );
    this.callbacks?.onReconnecting?.(this.reconnectAttempt);
    this.reconnectTimer = setTimeout(() => this.connect(), delay);
  }

  private cleanup(): void {
    if (this.pingCheckTimer) {
      clearInterval(this.pingCheckTimer);
      this.pingCheckTimer = null;
    }
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}
