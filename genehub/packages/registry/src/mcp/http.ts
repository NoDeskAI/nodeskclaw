import { randomUUID } from 'node:crypto';
import { WebStandardStreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js';
import { createMcpServer } from './server.js';

const SESSION_TTL_MS = 10 * 60 * 1000;

type Session = {
  transport: WebStandardStreamableHTTPServerTransport;
  lastActive: number;
};

const sessions = new Map<string, Session>();

setInterval(() => {
  const now = Date.now();
  for (const [id, s] of sessions) {
    if (now - s.lastActive > SESSION_TTL_MS) {
      s.transport.close();
      sessions.delete(id);
    }
  }
}, 60_000);

export async function handleMcpRequest(request: Request): Promise<Response> {
  const sessionId = request.headers.get('mcp-session-id');

  if (sessionId) {
    const session = sessions.get(sessionId);
    if (session) {
      session.lastActive = Date.now();
      return session.transport.handleRequest(request);
    }
    return new Response(
      JSON.stringify({
        jsonrpc: '2.0',
        error: { code: -32000, message: 'Session not found' },
        id: null,
      }),
      { status: 404, headers: { 'Content-Type': 'application/json' } },
    );
  }

  const transport = new WebStandardStreamableHTTPServerTransport({
    sessionIdGenerator: () => randomUUID(),
    onsessioninitialized: (id) => {
      sessions.set(id, { transport, lastActive: Date.now() });
    },
  });

  const server = createMcpServer();
  await server.connect(transport);

  transport.onclose = () => {
    if (transport.sessionId) {
      sessions.delete(transport.sessionId);
    }
  };

  return transport.handleRequest(request);
}
