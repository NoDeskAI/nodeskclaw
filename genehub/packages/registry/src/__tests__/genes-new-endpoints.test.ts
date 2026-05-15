import { describe, expect, it } from 'vitest';
import { app } from '../app.js';

const hasDB = !!process.env.DATABASE_URL;

describe('Gene new API endpoints', () => {
  it.skipIf(!hasDB)('GET /api/v1/genes/tags should return tag statistics', async () => {
    const res = await app.request('/api/v1/genes/tags');
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.code).toBe(0);
    expect(Array.isArray(json.data)).toBe(true);
    if (json.data.length > 0) {
      expect(json.data[0]).toHaveProperty('tag');
      expect(json.data[0]).toHaveProperty('count');
    }
  });

  it.skipIf(!hasDB)('GET /api/v1/genes/featured should return featured genes', async () => {
    const res = await app.request('/api/v1/genes/featured?limit=5');
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.code).toBe(0);
    expect(Array.isArray(json.data)).toBe(true);
  });

  it.skipIf(!hasDB)(
    'GET /api/v1/genes/:slug/synergies should return 404 for nonexistent gene',
    async () => {
      const res = await app.request('/api/v1/genes/nonexistent-gene/synergies');
      expect(res.status).toBe(404);
    },
  );

  it.skipIf(!hasDB)('GET /api/v1/genomes/featured should return featured genomes', async () => {
    const res = await app.request('/api/v1/genomes/featured?limit=5');
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.code).toBe(0);
    expect(Array.isArray(json.data)).toBe(true);
  });

  it('GET /api/v1/genes/tags should not conflict with /:slug route', async () => {
    const res = await app.request('/api/v1/genes/tags');
    if (hasDB) {
      expect(res.status).toBe(200);
      const json = await res.json();
      expect(json.code).toBe(0);
      expect(json.data).not.toHaveProperty('slug');
    }
  });

  it('GET /api/v1/genes/featured should not conflict with /:slug route', async () => {
    const res = await app.request('/api/v1/genes/featured');
    if (hasDB) {
      expect(res.status).toBe(200);
      const json = await res.json();
      expect(json.code).toBe(0);
      expect(json.data).not.toHaveProperty('slug');
    }
  });
});
