import { createServer, type ServerResponse } from "node:http";

const SSE_PORT = 9721;
const HEARTBEAT_INTERVAL_MS = 15_000;

const clients = new Set<ServerResponse>();

export function startSSEServer(): void {
  const server = createServer((req, res) => {
    if (req.method === "GET" && req.url?.startsWith("/sse/events")) {
      res.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      });

      res.write("event: connected\ndata: {}\n\n");
      clients.add(res);

      req.on("close", () => {
        clients.delete(res);
      });
      return;
    }

    if (req.method === "GET" && req.url === "/sse/health") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: true, clients: clients.size }));
      return;
    }

    res.writeHead(404);
    res.end();
  });

  server.listen(SSE_PORT, () => {
    console.log(`[clawbuddy] SSE server listening on port ${SSE_PORT}`);
  });

  setInterval(() => {
    const chunk = `event: heartbeat\ndata: ${JSON.stringify({ t: Date.now() })}\n\n`;
    for (const c of clients) {
      c.write(chunk);
    }
  }, HEARTBEAT_INTERVAL_MS);
}

export function broadcast(data: unknown): void {
  if (clients.size === 0) {
    throw new Error(
      "No ClawBuddy backend connected — collaboration channel unavailable",
    );
  }

  const chunk = `event: message\ndata: ${JSON.stringify(data)}\n\n`;
  for (const c of clients) {
    c.write(chunk);
  }
}

export function hasListeners(): boolean {
  return clients.size > 0;
}
