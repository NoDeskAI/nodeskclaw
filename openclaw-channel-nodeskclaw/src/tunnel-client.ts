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

export function startTunnelClient(cfg: OpenClawConfig): TunnelClient {
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

  if (!tunnelUrl || !instanceId || !token) {
    console.warn(
      "[tunnel] Missing config — tunnelUrl=%s instanceId=%s token=%s",
      tunnelUrl ? "set" : "MISSING",
      instanceId ? "set" : "MISSING",
      token ? "set" : "MISSING",
    );
    _instance = new TunnelClient(tunnelUrl, instanceId, token);
    return _instance;
  }

  if (!explicitUrl) {
    console.log("[tunnel] Derived tunnelUrl from apiUrl: %s", tunnelUrl);
  }

  _instance = new TunnelClient(tunnelUrl, instanceId, token);
  _instance.connect();
  return _instance;
}

export class TunnelClient {
  private ws: WebSocket | null = null;
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private lastPong = Date.now();
  private pingCheckTimer: ReturnType<typeof setInterval> | null = null;
  private closed = false;
  private _protocolDowngraded = false;
  private learningHandler: LearningWebhookHandler | null = null;

  get downgraded(): boolean {
    return this._protocolDowngraded;
  }

  constructor(
    private backendUrl: string,
    private instanceId: string,
    private token: string,
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

    this.ws.addEventListener("open", () => {
      console.log("[tunnel] Connected, sending auth...");
      this.send({
        id: crypto.randomUUID(),
        type: "auth",
        payload: { instance_id: this.instanceId, token: this.token },
        ts: Date.now(),
      });
    });

    this.ws.addEventListener("message", (event) => {
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

    this.ws.addEventListener("close", (event) => {
      console.warn(
        "[tunnel] Connection closed: code=%d reason=%s",
        event.code,
        event.reason,
      );
      this.cleanup();
      if (!this.closed) this.scheduleReconnect();
    });

    this.ws.addEventListener("error", (err) => {
      console.error("[tunnel] WebSocket error:", err);
      const failedWs = this.ws;
      setTimeout(() => {
        if (this.ws === failedWs && !this.closed) {
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
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn("[tunnel] Cannot send — not connected");
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
        break;

      case "auth.error":
        console.error(
          "[tunnel] Auth failed:",
          msg.payload?.reason ?? "unknown",
        );
        this.closed = true;
        this.ws?.close();
        break;

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
          model: "gpt-4",
          messages,
          stream: true,
        }),
      });

      if (!resp.ok || !resp.body) {
        this.send({
          id: crypto.randomUUID(),
          type: "chat.response.error",
          replyTo: msg.id,
          traceId: msg.traceId,
          payload: {
            error: `Local OpenClaw API returned ${resp.status}`,
          },
          ts: Date.now(),
        });
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let dataAccum = "";

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
              const chunk = JSON.parse(dataAccum);
              const content =
                chunk?.choices?.[0]?.delta?.content ?? "";
              if (content) {
                this.send({
                  id: crypto.randomUUID(),
                  type: "chat.response.chunk",
                  replyTo: msg.id,
                  traceId: msg.traceId,
                  payload: { content },
                  ts: Date.now(),
                });
              }
            } catch {}
            dataAccum = "";
          }
        }
      }

      if (dataAccum && dataAccum !== "[DONE]") {
        try {
          const chunk = JSON.parse(dataAccum);
          const content = chunk?.choices?.[0]?.delta?.content ?? "";
          if (content) {
            this.send({
              id: crypto.randomUUID(),
              type: "chat.response.chunk",
              replyTo: msg.id,
              traceId: msg.traceId,
              payload: { content },
              ts: Date.now(),
            });
          }
        } catch {}
      }

      this.send({
        id: crypto.randomUUID(),
        type: "chat.response.done",
        replyTo: msg.id,
        traceId: msg.traceId,
        payload: {},
        ts: Date.now(),
      });
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

    if (!this._protocolDowngraded && this.backendUrl.startsWith("wss://")) {
      this.backendUrl = this.backendUrl.replace(/^wss:\/\//, "ws://");
      this._protocolDowngraded = true;
      this.reconnectAttempt = 0;
      console.log("[tunnel] Downgrading protocol wss->ws: %s", this.backendUrl);
      this.reconnectTimer = setTimeout(() => this.connect(), 500);
      return;
    }

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
