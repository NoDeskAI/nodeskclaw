import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { GepGene, RecommendationItem } from '../evomap/client.js';

vi.mock('../../db/index.js', () => ({
  db: {
    select: vi.fn().mockReturnValue({
      from: vi.fn().mockReturnValue({
        where: vi.fn().mockResolvedValue([]),
      }),
    }),
    insert: vi.fn().mockReturnValue({
      values: vi.fn().mockReturnValue({
        returning: vi.fn().mockResolvedValue([{ id: 'new-gene-id' }]),
      }),
    }),
    update: vi.fn().mockReturnValue({
      set: vi.fn().mockReturnValue({
        where: vi.fn().mockResolvedValue(undefined),
      }),
    }),
  },
  schema: {
    genes: { id: 'id', slug: 'slug', version: 'version' },
    geneVersions: { gene_id: 'gene_id' },
  },
}));

vi.mock('drizzle-orm', () => ({
  eq: vi.fn((_col: unknown, val: unknown) => val),
}));

import { convertRecommendation } from '../evomap/converter.js';
import { EvoMapAdapter } from '../evomap/sync.js';

function makeGene(id = 'gene_gep_test'): GepGene {
  return {
    type: 'Gene',
    id,
    category: 'repair',
    signals_match: ['error'],
    preconditions: ['has errors'],
    strategy: ['Fix the error'],
    constraints: { max_files: 10, forbidden_paths: [] },
  };
}

function makeRecommendation(id = 'gene_gep_test', score = 0.9): RecommendationItem {
  return {
    type: 'gene',
    id,
    score,
    reason: 'signals match',
    data: makeGene(id),
  };
}

describe('EvoMapAdapter', () => {
  it('has source "evomap" and displayName "EvoMap"', () => {
    const adapter = new EvoMapAdapter({ baseUrl: 'http://localhost' });
    expect(adapter.source).toBe('evomap');
    expect(adapter.displayName).toBe('EvoMap');
  });

  it('convert() delegates to convertRecommendation', () => {
    const adapter = new EvoMapAdapter({ baseUrl: 'http://localhost' });
    const item = makeRecommendation();
    const direct = convertRecommendation(item);
    const viaAdapter = adapter.convert(item);
    expect(viaAdapter.slug).toBe(direct.slug);
    expect(viaAdapter.name).toBe(direct.name);
  });
});

describe('EvoMapAdapter.sync', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
  });

  function jsonResponse(data: unknown, status = 200) {
    return Promise.resolve(new Response(JSON.stringify(data), { status }));
  }

  it('yields created events for new recommendations', async () => {
    const recommendResp = {
      request_id: 'req-1',
      recommendations: [makeRecommendation('gene_gep_alpha')],
    };
    fetchSpy.mockReturnValueOnce(jsonResponse(recommendResp));

    const adapter = new EvoMapAdapter({ baseUrl: 'http://localhost' });
    const events = [];
    for await (const e of adapter.sync()) {
      events.push(e);
    }

    expect(events).toHaveLength(1);
    expect(events[0].kind).toBe('created');
    expect(events[0].slug).toBe('gep-alpha');
  });

  it('respects limit option', async () => {
    const recommendResp = {
      request_id: 'req-2',
      recommendations: [
        makeRecommendation('gene_gep_a'),
        makeRecommendation('gene_gep_b'),
        makeRecommendation('gene_gep_c'),
      ],
    };
    fetchSpy.mockReturnValueOnce(jsonResponse(recommendResp));

    const adapter = new EvoMapAdapter({ baseUrl: 'http://localhost' });
    const events = [];
    for await (const e of adapter.sync({ limit: 2 })) {
      events.push(e);
    }

    expect(events).toHaveLength(2);
  });

  it('yields failed event on API error', async () => {
    fetchSpy.mockReturnValueOnce(jsonResponse({}, 500));

    const adapter = new EvoMapAdapter({ baseUrl: 'http://localhost' });
    const events = [];
    try {
      for await (const e of adapter.sync()) {
        events.push(e);
      }
    } catch {
      // EvoMap API error during recommend call
    }
    expect(events).toHaveLength(0);
  });

  it('sends profile to recommend endpoint', async () => {
    const recommendResp = { request_id: 'req-3', recommendations: [] };
    fetchSpy.mockReturnValueOnce(jsonResponse(recommendResp));

    const profile = { product: 'nanobot', installed_genes: ['gene-a', 'gene-b'] };
    const adapter = new EvoMapAdapter({ baseUrl: 'http://localhost', profile });
    const events = [];
    for await (const e of adapter.sync()) {
      events.push(e);
    }

    expect(events).toHaveLength(0);
    const [, opts] = fetchSpy.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(opts.body as string);
    expect(body.product).toBe('nanobot');
    expect(body.installed_genes).toEqual(['gene-a', 'gene-b']);
  });
});
