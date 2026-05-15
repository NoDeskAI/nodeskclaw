import { createHash, randomBytes } from 'node:crypto';
import { and, eq } from 'drizzle-orm';
import { Hono } from 'hono';
import { db, schema } from '../db/index.js';
import { requireAuth } from '../middleware/auth.js';
import { AppError } from '../middleware/error-handler.js';
import { success } from '../middleware/response.js';

const { apiKeys } = schema;

export const keysRouter = new Hono();

keysRouter.use('*', requireAuth('publisher'));

keysRouter.post('/', async (c) => {
  const publisherId = c.get('publisherId') as string;
  const body = await c.req.json().catch(() => ({}));
  const name = (body as { name?: string }).name || 'Default';

  const token = `ghb_${randomBytes(24).toString('base64url')}`;
  const tokenHash = createHash('sha256').update(token).digest('hex');
  const tokenPrefix = token.slice(0, 12);

  const [key] = await db
    .insert(apiKeys)
    .values({ publisher_id: publisherId, token_prefix: tokenPrefix, token_hash: tokenHash, name })
    .returning();

  return success(c, {
    id: key.id,
    name: key.name,
    token_prefix: key.token_prefix,
    token,
    created_at: key.created_at,
  });
});

keysRouter.get('/', async (c) => {
  const publisherId = c.get('publisherId') as string;

  const keys = await db
    .select({
      id: apiKeys.id,
      name: apiKeys.name,
      token_prefix: apiKeys.token_prefix,
      last_used_at: apiKeys.last_used_at,
      created_at: apiKeys.created_at,
      revoked_at: apiKeys.revoked_at,
    })
    .from(apiKeys)
    .where(eq(apiKeys.publisher_id, publisherId));

  return success(c, keys);
});

keysRouter.delete('/:id', async (c) => {
  const publisherId = c.get('publisherId') as string;
  const keyId = c.req.param('id');

  const existing = await db
    .select()
    .from(apiKeys)
    .where(and(eq(apiKeys.id, keyId), eq(apiKeys.publisher_id, publisherId)));

  if (existing.length === 0) throw AppError.internal('Key 不存在');

  if (existing[0].revoked_at) return success(c, { message: '已撤销' });

  await db.update(apiKeys).set({ revoked_at: new Date() }).where(eq(apiKeys.id, keyId));

  return success(c, { message: 'ok' });
});
