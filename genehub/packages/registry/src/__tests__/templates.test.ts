import { describe, expect, it } from 'vitest';
import { app } from '../app.js';

const hasDB = !!process.env.DATABASE_URL;

describe('Agent Template API', () => {
  it.skipIf(!hasDB)('GET /api/v1/templates should return paginated list', async () => {
    const res = await app.request('/api/v1/templates');
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.code).toBe(0);
    expect(json.data).toHaveProperty('items');
    expect(json.data).toHaveProperty('total');
    expect(json.data).toHaveProperty('page');
    expect(json.data).toHaveProperty('page_size');
    expect(json.data).toHaveProperty('total_pages');
    expect(Array.isArray(json.data.items)).toBe(true);
  });

  it.skipIf(!hasDB)('GET /api/v1/templates should support search query', async () => {
    const res = await app.request('/api/v1/templates?q=test&page=1&page_size=5');
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.code).toBe(0);
    expect(json.data.page_size).toBeLessThanOrEqual(5);
  });

  it.skipIf(!hasDB)('GET /api/v1/templates/featured should return featured templates', async () => {
    const res = await app.request('/api/v1/templates/featured?limit=5');
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.code).toBe(0);
    expect(Array.isArray(json.data)).toBe(true);
  });

  it.skipIf(!hasDB)(
    'GET /api/v1/templates/:slug should return 404 for nonexistent template',
    async () => {
      const res = await app.request('/api/v1/templates/nonexistent-template-slug');
      expect(res.status).toBe(404);
      const json = await res.json();
      expect(json.error_code).toBe('template_not_found');
    },
  );

  it.skipIf(!hasDB)(
    'GET /api/v1/templates/:slug/versions should return 404 for nonexistent template',
    async () => {
      const res = await app.request('/api/v1/templates/nonexistent-template-slug/versions');
      expect(res.status).toBe(404);
    },
  );

  it.skipIf(!hasDB)('POST /api/v1/templates should require auth', async () => {
    const res = await app.request('/api/v1/templates', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: 'Test Template',
        slug: 'test-template',
        version: '1.0.0',
        genomes: [],
      }),
    });
    expect(res.status).toBe(401);
  });

  it.skipIf(!hasDB)('DELETE /api/v1/templates/:slug should require admin auth', async () => {
    const res = await app.request('/api/v1/templates/any-slug', {
      method: 'DELETE',
    });
    expect(res.status).toBe(401);
  });

  it.skipIf(!hasDB)(
    'POST /api/v1/templates/:slug/installed should return 404 for nonexistent',
    async () => {
      const res = await app.request('/api/v1/templates/nonexistent-slug/installed', {
        method: 'POST',
      });
      expect(res.status).toBe(404);
    },
  );

  it('GET /api/v1/templates/featured should not conflict with /:slug route', async () => {
    const res = await app.request('/api/v1/templates/featured');
    if (hasDB) {
      expect(res.status).toBe(200);
      const json = await res.json();
      expect(json.code).toBe(0);
      expect(json.data).not.toHaveProperty('slug');
    }
  });
});
