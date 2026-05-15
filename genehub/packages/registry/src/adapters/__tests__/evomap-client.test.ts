import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { EvoMapApiError, EvoMapClient } from '../evomap/client.js';

const MOCK_BASE = 'https://test-evomap.local';

function makeClient(opts: { apiKey?: string } = {}) {
  return new EvoMapClient({ baseUrl: MOCK_BASE, timeoutMs: 5000, apiKey: opts.apiKey });
}

describe('EvoMapClient', () => {
  const fetchSpy = vi.fn<Parameters<typeof fetch>, ReturnType<typeof fetch>>();

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function jsonResponse(data: unknown, status = 200) {
    return Promise.resolve(new Response(JSON.stringify(data), { status }));
  }

  // -------------------------------------------------------------------------
  // listGenes
  // -------------------------------------------------------------------------

  describe('listGenes', () => {
    it('calls correct URL', async () => {
      fetchSpy.mockReturnValueOnce(jsonResponse({ version: 1, genes: [] }));
      const client = makeClient();
      const result = await client.listGenes();
      expect(result.genes).toEqual([]);
      const url = fetchSpy.mock.calls[0][0] as string;
      expect(url).toBe(`${MOCK_BASE}/api/v1/genes`);
    });

    it('returns gene list', async () => {
      const gene = { type: 'Gene', id: 'gene_test', category: 'repair', signals_match: [] };
      fetchSpy.mockReturnValueOnce(jsonResponse({ version: 1, genes: [gene] }));
      const client = makeClient();
      const result = await client.listGenes();
      expect(result.genes).toHaveLength(1);
      expect(result.genes[0].id).toBe('gene_test');
    });
  });

  // -------------------------------------------------------------------------
  // getGene
  // -------------------------------------------------------------------------

  describe('getGene', () => {
    it('calls correct URL with encoded id', async () => {
      const gene = { type: 'Gene', id: 'gene_repair', category: 'repair', signals_match: [] };
      fetchSpy.mockReturnValueOnce(jsonResponse(gene));
      const client = makeClient();
      await client.getGene('gene_repair');
      const url = fetchSpy.mock.calls[0][0] as string;
      expect(url).toBe(`${MOCK_BASE}/api/v1/genes/gene_repair`);
    });
  });

  // -------------------------------------------------------------------------
  // listCapsules
  // -------------------------------------------------------------------------

  describe('listCapsules', () => {
    it('calls correct URL', async () => {
      fetchSpy.mockReturnValueOnce(jsonResponse({ version: 1, capsules: [] }));
      const client = makeClient();
      const result = await client.listCapsules();
      expect(result.capsules).toEqual([]);
      const url = fetchSpy.mock.calls[0][0] as string;
      expect(url).toBe(`${MOCK_BASE}/api/v1/capsules`);
    });
  });

  // -------------------------------------------------------------------------
  // recommend
  // -------------------------------------------------------------------------

  describe('recommend', () => {
    it('sends POST with profile body', async () => {
      const recommendResp = { request_id: 'req-1', recommendations: [] };
      fetchSpy.mockReturnValueOnce(jsonResponse(recommendResp));
      const client = makeClient();
      const profile = { product: 'genehub', installed_genes: ['gene-a'] };
      const result = await client.recommend(profile);
      expect(result.request_id).toBe('req-1');

      const [url, opts] = fetchSpy.mock.calls[0] as [string, RequestInit];
      expect(url).toBe(`${MOCK_BASE}/api/v1/recommend`);
      expect(opts.method).toBe('POST');
      const body = JSON.parse(opts.body as string);
      expect(body.product).toBe('genehub');
      expect(body.installed_genes).toContain('gene-a');
    });
  });

  // -------------------------------------------------------------------------
  // feedback
  // -------------------------------------------------------------------------

  describe('feedback', () => {
    it('sends POST with feedback payload', async () => {
      fetchSpy.mockReturnValueOnce(jsonResponse({ ok: true }));
      const client = makeClient();
      const result = await client.feedback({
        request_id: 'req-1',
        gene_slug: 'test-gene',
        outcome: 'success',
        score: 0.9,
      });
      expect(result.ok).toBe(true);

      const [url, opts] = fetchSpy.mock.calls[0] as [string, RequestInit];
      expect(url).toBe(`${MOCK_BASE}/api/v1/feedback`);
      expect(opts.method).toBe('POST');
    });
  });

  // -------------------------------------------------------------------------
  // Error handling
  // -------------------------------------------------------------------------

  describe('error handling', () => {
    it('throws EvoMapApiError on non-200 GET', async () => {
      fetchSpy.mockReturnValueOnce(jsonResponse({ error: 'nope' }, 500));
      const client = makeClient();
      await expect(client.listGenes()).rejects.toThrow(EvoMapApiError);
    });

    it('throws EvoMapApiError on non-200 POST', async () => {
      fetchSpy.mockReturnValueOnce(jsonResponse({}, 403));
      const client = makeClient();
      await expect(client.recommend({ product: 'test', installed_genes: [] })).rejects.toThrow(
        EvoMapApiError,
      );
    });

    it('includes status code in error', async () => {
      fetchSpy.mockReturnValueOnce(jsonResponse({}, 429));
      const client = makeClient();
      try {
        await client.listGenes();
      } catch (e) {
        expect(e).toBeInstanceOf(EvoMapApiError);
        expect((e as EvoMapApiError).status).toBe(429);
      }
    });
  });

  // -------------------------------------------------------------------------
  // Auth headers
  // -------------------------------------------------------------------------

  describe('authentication', () => {
    it('sends X-Api-Key header when apiKey is set', async () => {
      fetchSpy.mockReturnValueOnce(jsonResponse({ version: 1, genes: [] }));
      const client = makeClient({ apiKey: 'secret-key' });
      await client.listGenes();
      const opts = fetchSpy.mock.calls[0][1] as RequestInit;
      expect((opts.headers as Record<string, string>)['X-Api-Key']).toBe('secret-key');
    });

    it('omits X-Api-Key header when no apiKey', async () => {
      fetchSpy.mockReturnValueOnce(jsonResponse({ version: 1, genes: [] }));
      const client = makeClient();
      await client.listGenes();
      const opts = fetchSpy.mock.calls[0][1] as RequestInit;
      expect((opts.headers as Record<string, string>)['X-Api-Key']).toBeUndefined();
    });
  });
});
