import { describe, expect, it } from 'vitest';
import { app } from '../app.js';

const hasDB = !!process.env.DATABASE_URL;

describe('Reviews API', () => {
  it.skipIf(!hasDB)('GET /api/v1/genes/:slug/reviews 不存在的基因应返回 404', async () => {
    const res = await app.request('/api/v1/genes/nonexistent-gene/reviews');
    expect(res.status).toBe(404);
    const json = await res.json();
    expect(json.error_code).toBe('gene_not_found');
  });

  it('POST /api/v1/genes/:slug/reviews 无 token 应返回 401', async () => {
    const res = await app.request('/api/v1/genes/some-gene/reviews', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ verdict: 'approved', score: 8 }),
    });
    expect(res.status).toBe(401);
    const json = await res.json();
    expect(json.error_code).toBe('token_invalid');
  });

  it('POST /api/v1/genes/:slug/reviews 普通 publisher token 应返回 401 或 403', async () => {
    const res = await app.request('/api/v1/genes/some-gene/reviews', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer ghb_publisher_test',
      },
      body: JSON.stringify({ verdict: 'approved', score: 8 }),
    });
    expect([401, 403]).toContain(res.status);
    const json = await res.json();
    expect(['token_invalid', 'permission_denied']).toContain(json.error_code);
  });

  it.skipIf(!hasDB)('GET /api/v1/genomes/:slug/reviews 不存在的基因组应返回 404', async () => {
    const res = await app.request('/api/v1/genomes/nonexistent-genome/reviews');
    expect(res.status).toBe(404);
    const json = await res.json();
    expect(json.error_code).toBe('genome_not_found');
  });

  it('POST /api/v1/genomes/:slug/reviews 无 token 应返回 401', async () => {
    const res = await app.request('/api/v1/genomes/some-genome/reviews', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ verdict: 'approved', score: 8 }),
    });
    expect(res.status).toBe(401);
    const json = await res.json();
    expect(json.error_code).toBe('token_invalid');
  });

  it.skipIf(!hasDB)('GET /api/v1/templates/:slug/reviews 不存在的模板应返回 404', async () => {
    const res = await app.request('/api/v1/templates/nonexistent-template/reviews');
    expect(res.status).toBe(404);
    const json = await res.json();
    expect(json.error_code).toBe('template_not_found');
  });

  it('POST /api/v1/templates/:slug/reviews 无 token 应返回 401', async () => {
    const res = await app.request('/api/v1/templates/some-template/reviews', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ verdict: 'approved', score: 8 }),
    });
    expect(res.status).toBe(401);
    const json = await res.json();
    expect(json.error_code).toBe('token_invalid');
  });

  it('POST /api/v1/genes/:slug/reviews/:reviewId/feedback 无 token 应返回 401', async () => {
    const res = await app.request('/api/v1/genes/some-gene/reviews/review-123/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ feedback: 'test feedback' }),
    });
    expect(res.status).toBe(401);
    const json = await res.json();
    expect(json.error_code).toBe('token_invalid');
  });
});
