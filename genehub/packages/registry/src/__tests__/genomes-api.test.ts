import { describe, expect, it } from 'vitest';
import { app } from '../app.js';

const hasDB = !!process.env.DATABASE_URL;

describe('Genomes API', () => {
  it.skipIf(!hasDB)('GET /api/v1/genomes 应返回分页列表', async () => {
    const res = await app.request('/api/v1/genomes');
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.code).toBe(0);
    expect(json.data).toHaveProperty('items');
    expect(json.data).toHaveProperty('total');
    expect(json.data).toHaveProperty('page');
    expect(json.data).toHaveProperty('page_size');
  });

  it.skipIf(!hasDB)('GET /api/v1/genomes/:slug 不存在时应返回 404', async () => {
    const res = await app.request('/api/v1/genomes/nonexistent-genome');
    expect(res.status).toBe(404);
    const json = await res.json();
    expect(json.error_code).toBe('genome_not_found');
  });

  it.skipIf(!hasDB)('GET /api/v1/genomes/:slug/resolve 不存在时应返回 404', async () => {
    const res = await app.request('/api/v1/genomes/nonexistent-genome/resolve');
    expect(res.status).toBe(404);
    const json = await res.json();
    expect(json.error_code).toBe('genome_not_found');
  });

  it.skipIf(!hasDB)('GET /api/v1/genomes/:slug/versions 不存在时应返回 404', async () => {
    const res = await app.request('/api/v1/genomes/nonexistent-genome/versions');
    expect(res.status).toBe(404);
    const json = await res.json();
    expect(json.error_code).toBe('genome_not_found');
  });

  it('POST /api/v1/genomes 无 token 应返回 401', async () => {
    const res = await app.request('/api/v1/genomes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'test', slug: 'test', version: '1.0.0', genes: [] }),
    });
    expect(res.status).toBe(401);
    const json = await res.json();
    expect(json.error_code).toBe('token_invalid');
  });

  it('DELETE /api/v1/genomes/:slug 无效 token 应返回 401', async () => {
    const res = await app.request('/api/v1/genomes/some-genome', {
      method: 'DELETE',
      headers: { Authorization: 'Bearer ghb_publisher_test' },
    });
    expect(res.status).toBe(401);
    const json = await res.json();
    expect(json.error_code).toBe('token_invalid');
  });

  it.skipIf(!hasDB)('POST /api/v1/genomes 空基因列表应返回 422', async () => {
    const res = await app.request('/api/v1/genomes', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer admin-dev-token',
      },
      body: JSON.stringify({
        name: 'Test Genome',
        slug: 'test-empty-genes',
        version: '1.0.0',
        genes: [],
      }),
    });
    expect(res.status).toBe(422);
    const json = await res.json();
    expect(json.error_code).toBe('genome_validation_failed');
  });

  it.skipIf(!hasDB)('POST /api/v1/genomes 引用不存在基因应返回 422', async () => {
    const res = await app.request('/api/v1/genomes', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer admin-dev-token',
      },
      body: JSON.stringify({
        name: 'Test Genome',
        slug: 'test-bad-refs',
        version: '1.0.0',
        genes: [{ slug: 'this-gene-does-not-exist', version: '1.0.0' }],
      }),
    });
    expect(res.status).toBe(422);
    const json = await res.json();
    expect(json.error_code).toBe('genome_validation_failed');
    expect(json.message).toContain('不存在');
  });

  it.skipIf(!hasDB)('POST /api/v1/genomes 无效版本号应返回 422', async () => {
    const res = await app.request('/api/v1/genomes', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer admin-dev-token',
      },
      body: JSON.stringify({
        name: 'Test Genome',
        slug: 'test-bad-version',
        version: 'not-a-version',
        genes: [{ slug: 'some-gene', version: '1.0.0' }],
      }),
    });
    expect(res.status).toBe(422);
    const json = await res.json();
    expect(json.error_code).toBe('genome_validation_failed');
  });

  it.skipIf(!hasDB)('POST /api/v1/genomes 缺少必填字段应返回 422', async () => {
    const res = await app.request('/api/v1/genomes', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer admin-dev-token',
      },
      body: JSON.stringify({ genes: [{ slug: 'x', version: '1.0.0' }] }),
    });
    expect(res.status).toBe(422);
    const json = await res.json();
    expect(json.error_code).toBe('genome_validation_failed');
  });
});
