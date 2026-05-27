import { createHmac } from 'node:crypto';
import { describe, expect, it } from 'vitest';
import { app } from '../../app.js';

function _sign(body: string, secret: string): string {
  return `sha256=${createHmac('sha256', secret).update(body).digest('hex')}`;
}

describe('Webhooks API', () => {
  it('POST /api/v1/webhooks/nodeskclaw/gene-created should reject missing slug', async () => {
    const body = JSON.stringify({ manifest: {} });
    const res = await app.request('/api/v1/webhooks/nodeskclaw/gene-created', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
    });
    expect(res.status).toBe(422);
  });

  it('POST /api/v1/webhooks/nodeskclaw/gene-learned should reject missing slug', async () => {
    const body = JSON.stringify({});
    const res = await app.request('/api/v1/webhooks/nodeskclaw/gene-learned', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
    });
    expect(res.status).toBe(422);
  });

  it('POST /api/v1/webhooks/nodeskclaw/effectiveness should reject non-array', async () => {
    const body = JSON.stringify({ reports: 'not-array' });
    const res = await app.request('/api/v1/webhooks/nodeskclaw/effectiveness', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
    });
    expect(res.status).toBe(422);
  });

  it('POST /api/v1/webhooks/nodeskclaw/effectiveness should accept empty array', async () => {
    const body = JSON.stringify({ reports: [] });
    const res = await app.request('/api/v1/webhooks/nodeskclaw/effectiveness', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
    });
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.data.processed).toBe(0);
  });
});

describe('Sync API', () => {
  it('POST /api/v1/sync/nodeskclaw should require admin auth', async () => {
    const res = await app.request('/api/v1/sync/nodeskclaw', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    expect(res.status).toBe(401);
  });

  it('GET /api/v1/sync/status should return current state', async () => {
    const res = await app.request('/api/v1/sync/status');
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json.data).toHaveProperty('in_progress');
    expect(json.data).toHaveProperty('sources');
    expect(json.data.sources).toHaveProperty('nodeskclaw');
    expect(json.data.sources).toHaveProperty('clawhub');
    expect(json.data.sources).toHaveProperty('evomap');
  });
});
