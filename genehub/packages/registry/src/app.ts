import { existsSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { serveStatic } from '@hono/node-server/serve-static';
import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { logger } from 'hono/logger';
import { authRouter } from './api/auth.js';
import { genesRouter } from './api/genes.js';
import { genomesRouter } from './api/genomes.js';
import { keysRouter } from './api/keys.js';
import { resolveRouter } from './api/resolve.js';
import { reviewsRouter } from './api/reviews.js';
import { syncRouter } from './api/sync.js';
import { templatesRouter } from './api/templates.js';
import { webhooksRouter } from './api/webhooks.js';
import { handleMcpRequest } from './mcp/http.js';
import type { AuthVariables } from './middleware/auth.js';
import { errorHandler } from './middleware/error-handler.js';

export const app = new Hono<{ Variables: AuthVariables }>();

let healthOkCount = 0;
app.use('*', async (c, next) => {
  if (c.req.path === '/api/health') {
    await next();
    if (c.res.status === 200) {
      healthOkCount++;
      if (healthOkCount % 30 === 0) {
        console.log(`[health] ok ×${healthOkCount}`);
      }
    } else {
      console.error(`[health] FAIL status=${c.res.status}`);
    }
    return;
  }
  return logger()(c, next);
});
app.use('*', cors());

app.onError(errorHandler);

app.get('/api/health', (c) => c.json({ status: 'ok' }));

app.get('/api/info', (c) =>
  c.json({
    name: 'GeneHub Registry',
    version: '0.1.0',
    docs: 'https://github.com/NoDeskAI/genehub',
  }),
);

// MCP Streamable HTTP endpoint — token-gated for Curator / authorized clients
const MCP_TOKEN = process.env.GENEHUB_ADMIN_TOKEN;

app.all('/mcp', async (c) => {
  if (MCP_TOKEN) {
    const auth = c.req.header('Authorization');
    if (auth !== `Bearer ${MCP_TOKEN}`) {
      return c.json({ error: 'unauthorized' }, 401);
    }
  }
  return handleMcpRequest(c.req.raw);
});

app.route('/auth', authRouter);
app.route('/api/v1/genes', genesRouter);
app.route('/api/v1/genes', reviewsRouter);
app.route('/api/v1/genomes', genomesRouter);
app.route('/api/v1/templates', templatesRouter);
app.route('/api/v1/keys', keysRouter);
app.route('/api/v1/resolve', resolveRouter);
app.route('/api/v1/sync', syncRouter);
app.route('/api/v1/webhooks', webhooksRouter);

const PUBLIC_DIR = process.env.PUBLIC_DIR || './public';

if (existsSync(join(process.cwd(), PUBLIC_DIR))) {
  app.use('*', serveStatic({ root: PUBLIC_DIR }));

  app.get('*', async (c) => {
    const html = await readFile(join(process.cwd(), PUBLIC_DIR, 'index.html'), 'utf-8');
    return c.html(html);
  });
}
