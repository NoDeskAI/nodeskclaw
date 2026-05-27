import { describe, expect, it } from 'vitest';
import { app } from '../app.js';

describe('Registry API', () => {
  it('GET /api/info 应返回服务信息', async () => {
    const res = await app.request('/api/info');
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.name).toBe('GeneHub Registry');
    expect(json.version).toBe('0.1.0');
  });

  it('GET /api/health 应返回健康状态', async () => {
    const res = await app.request('/api/health');
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.status).toBe('ok');
  });

  it.skipIf(!process.env.DATABASE_URL)(
    'GET /api/v1/genes/:slug 不存在的基因应返回 404',
    async () => {
      const res = await app.request('/api/v1/genes/nonexistent');
      expect(res.status).toBe(404);
      const json = await res.json();
      expect(json.error_code).toBe('gene_not_found');
    },
  );

  it('POST /api/v1/genes 无 token 应返回 401', async () => {
    const res = await app.request('/api/v1/genes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ manifest: { slug: 'BAD' } }),
    });
    expect(res.status).toBe(401);
    const json = await res.json();
    expect(json.error_code).toBe('token_invalid');
  });
});
