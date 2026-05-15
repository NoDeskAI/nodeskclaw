import { Hono } from 'hono';
import type { InboundAdapter, SyncResult } from '../adapters/base.js';
import { ClawHubAdapter } from '../adapters/clawhub/index.js';
import { EvoMapAdapter } from '../adapters/evomap/index.js';
import { NoDeskClawAdapter } from '../adapters/nodeskclaw/index.js';
import { requireAuth } from '../middleware/auth.js';
import { AppError } from '../middleware/error-handler.js';
import { success } from '../middleware/response.js';

/**
 * @deprecated 同步接口已弃用，改用联邦搜索（GET /api/v1/genes?q=...）。
 * 外部基因源（ClawHub / EvoMap）不再入库，而是作为实时外部知识源查询。
 * 保留 NoDeskClaw 同步用于历史数据批量导入。
 */
export const syncRouter = new Hono();

const syncState: Record<string, { inProgress: boolean; lastResult: SyncResult | null }> = {
  nodeskclaw: { inProgress: false, lastResult: null },
  clawhub: { inProgress: false, lastResult: null },
  evomap: { inProgress: false, lastResult: null },
};

// Legacy aliases
let lastSyncResult: SyncResult | null = null;
let syncInProgress = false;

syncRouter.post('/nodeskclaw', requireAuth('admin'), async (c) => {
  if (syncInProgress) {
    throw new AppError(40900, 'sync_in_progress', '同步正在进行中，请稍后再试', 409);
  }

  const body = await c.req.json().catch(() => ({}));
  const full = body.full === true;
  const since = typeof body.since === 'string' ? body.since : undefined;
  const limit = typeof body.limit === 'number' ? body.limit : undefined;

  const nodeskclawDbUrl = process.env.NODESKCLAW_DATABASE_URL;
  if (!nodeskclawDbUrl) {
    throw new AppError(50001, 'config_missing', 'NODESKCLAW_DATABASE_URL 未配置', 500);
  }

  syncInProgress = true;
  const startedAt = new Date().toISOString();

  const adapter = new NoDeskClawAdapter({ databaseUrl: nodeskclawDbUrl });

  try {
    const events = [];
    let created = 0;
    let updated = 0;
    let skipped = 0;
    let failed = 0;

    for await (const event of adapter.sync({ full, since, limit })) {
      events.push(event);
      switch (event.kind) {
        case 'created':
          created++;
          break;
        case 'updated':
          updated++;
          break;
        case 'skipped':
          skipped++;
          break;
        case 'failed':
          failed++;
          break;
      }
    }

    lastSyncResult = {
      source: adapter.source,
      created,
      updated,
      skipped,
      failed,
      events,
      started_at: startedAt,
      finished_at: new Date().toISOString(),
    };

    return success(c, lastSyncResult);
  } finally {
    await adapter.close();
    syncInProgress = false;
  }
});

// ---------------------------------------------------------------------------
// ClawHub sync
// ---------------------------------------------------------------------------

/** @deprecated 改用联邦搜索 GET /api/v1/genes?q=... */
syncRouter.post('/clawhub', requireAuth('admin'), async (c) => {
  c.header('Deprecation', 'true');
  c.header('Sunset', '2026-06-01');
  c.header('Link', '</api/v1/genes?q={query}>; rel="successor-version"');

  if (syncState.clawhub.inProgress) {
    throw new AppError(40900, 'sync_in_progress', 'ClawHub 同步正在进行中，请稍后再试', 409);
  }

  const body = await c.req.json().catch(() => ({}));
  const full = body.full === true;
  const since = typeof body.since === 'string' ? body.since : undefined;
  const limit = typeof body.limit === 'number' ? body.limit : undefined;

  const clawhubBaseUrl = process.env.CLAWHUB_BASE_URL || 'https://clawhub.ai';
  const clawhubToken = process.env.CLAWHUB_TOKEN;

  const adapter = new ClawHubAdapter({
    baseUrl: clawhubBaseUrl,
    token: clawhubToken,
  });

  const result = await runSync('clawhub', adapter, { full, since, limit });
  return success(c, result);
});

// ---------------------------------------------------------------------------
// EvoMap sync (recommendation-based)
// ---------------------------------------------------------------------------

/** @deprecated 改用联邦搜索 GET /api/v1/genes?q=... */
syncRouter.post('/evomap', requireAuth('admin'), async (c) => {
  c.header('Deprecation', 'true');
  c.header('Sunset', '2026-06-01');
  c.header('Link', '</api/v1/genes?q={query}>; rel="successor-version"');

  if (syncState.evomap.inProgress) {
    throw new AppError(40900, 'sync_in_progress', 'EvoMap 同步正在进行中，请稍后再试', 409);
  }

  const body = await c.req.json().catch(() => ({}));
  const full = body.full === true;
  const limit = typeof body.limit === 'number' ? body.limit : undefined;

  const evomapBaseUrl = process.env.EVOMAP_BASE_URL || 'https://evomap.ai';
  const evomapApiKey = process.env.EVOMAP_API_KEY;

  const profile = body.profile ?? {
    product: 'genehub',
    installed_genes: [],
  };

  const adapter = new EvoMapAdapter({
    baseUrl: evomapBaseUrl,
    apiKey: evomapApiKey,
    profile,
  });

  const result = await runSync('evomap', adapter, { full, limit });
  return success(c, result);
});

// ---------------------------------------------------------------------------
// Shared sync runner
// ---------------------------------------------------------------------------

async function runSync(
  key: string,
  adapter: InboundAdapter,
  options: { full?: boolean; since?: string; limit?: number },
): Promise<SyncResult> {
  const state = syncState[key];
  if (!state) throw new AppError(40000, 'unknown_source', `未知同步源: ${key}`, 400);

  state.inProgress = true;
  const startedAt = new Date().toISOString();

  try {
    const events = [];
    let created = 0;
    let updated = 0;
    let skipped = 0;
    let failed = 0;

    for await (const event of adapter.sync(options)) {
      events.push(event);
      switch (event.kind) {
        case 'created':
          created++;
          break;
        case 'updated':
          updated++;
          break;
        case 'skipped':
          skipped++;
          break;
        case 'failed':
          failed++;
          break;
      }
    }

    const result: SyncResult = {
      source: adapter.source,
      created,
      updated,
      skipped,
      failed,
      events,
      started_at: startedAt,
      finished_at: new Date().toISOString(),
    };

    state.lastResult = result;
    return result;
  } finally {
    state.inProgress = false;
  }
}

// ---------------------------------------------------------------------------
// Status
// ---------------------------------------------------------------------------

syncRouter.get('/status', async (c) => {
  return success(c, {
    in_progress: syncInProgress || syncState.clawhub.inProgress || syncState.evomap.inProgress,
    sources: {
      nodeskclaw: {
        in_progress: syncInProgress,
        last_sync: lastSyncResult,
      },
      clawhub: {
        in_progress: syncState.clawhub.inProgress,
        last_sync: syncState.clawhub.lastResult,
      },
      evomap: {
        in_progress: syncState.evomap.inProgress,
        last_sync: syncState.evomap.lastResult,
      },
    },
  });
});
