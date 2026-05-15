import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ClawHubSkillListItem } from '../clawhub/client.js';

/**
 * The sync module imports db + drizzle which requires a real PG connection.
 * We test the convert() passthrough and verify processSkill orchestration
 * via mocking the client and db modules.
 */

// Mock db and schema before importing sync
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

import { convertClawHubSkill } from '../clawhub/converter.js';
// After mocking, import the module under test
import { ClawHubAdapter } from '../clawhub/sync.js';

describe('ClawHubAdapter', () => {
  it('has source "clawhub" and displayName "ClawHub"', () => {
    const adapter = new ClawHubAdapter({ baseUrl: 'http://localhost' });
    expect(adapter.source).toBe('clawhub');
    expect(adapter.displayName).toBe('ClawHub');
  });

  it('convert() delegates to convertClawHubSkill', () => {
    const adapter = new ClawHubAdapter({ baseUrl: 'http://localhost' });
    const payload = {
      detail: {
        skill: {
          slug: 'test',
          displayName: 'Test',
          summary: 'desc',
          tags: {},
          stats: {},
          createdAt: 0,
          updatedAt: 0,
        },
        latestVersion: { version: '1.0.0', createdAt: 0, changelog: '' },
        owner: null,
      },
      version: null,
      instructionsContent: 'hello',
    };

    const direct = convertClawHubSkill(payload);
    const viaAdapter = adapter.convert(payload);

    expect(viaAdapter.slug).toBe(direct.slug);
    expect(viaAdapter.name).toBe(direct.name);
    expect(viaAdapter.version).toBe(direct.version);
    expect(viaAdapter.skill.content).toBe(direct.skill.content);
  });
});

describe('ClawHubAdapter.sync', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
  });

  function jsonResponse(data: unknown, status = 200) {
    return Promise.resolve(new Response(JSON.stringify(data), { status }));
  }

  function textResponse(text: string, status = 200) {
    return Promise.resolve(new Response(text, { status }));
  }

  function makeSkillListItem(slug: string, updatedAt = Date.now()): ClawHubSkillListItem {
    return {
      slug,
      displayName: slug,
      summary: `${slug} description`,
      tags: {},
      stats: {},
      createdAt: updatedAt - 1000,
      updatedAt,
      latestVersion: { version: '1.0.0', createdAt: updatedAt, changelog: '' },
    };
  }

  it('yields created events for new skills', async () => {
    const listPage = {
      items: [makeSkillListItem('alpha')],
      nextCursor: null,
    };

    const detail = {
      skill: {
        slug: 'alpha',
        displayName: 'Alpha',
        summary: 'Alpha skill',
        tags: {},
        stats: {},
        createdAt: 0,
        updatedAt: 0,
      },
      latestVersion: { version: '1.0.0', createdAt: 0, changelog: '' },
      owner: null,
    };

    const versionInfo = {
      version: { version: '1.0.0', createdAt: 0, changelog: '' },
      skill: { slug: 'alpha', displayName: 'Alpha' },
    };

    fetchSpy
      .mockReturnValueOnce(jsonResponse(listPage))
      .mockReturnValueOnce(jsonResponse(detail))
      .mockReturnValueOnce(jsonResponse(versionInfo))
      .mockReturnValueOnce(textResponse('# Alpha\nInstructions here'));

    const adapter = new ClawHubAdapter({ baseUrl: 'http://localhost' });
    const events = [];
    for await (const e of adapter.sync({ limit: 1 })) {
      events.push(e);
    }

    expect(events).toHaveLength(1);
    expect(events[0].kind).toBe('created');
    expect(events[0].slug).toBe('alpha');
  });

  it('skips malicious skills', async () => {
    const listPage = {
      items: [makeSkillListItem('evil-skill')],
      nextCursor: null,
    };

    const detail = {
      skill: {
        slug: 'evil-skill',
        displayName: 'Evil',
        summary: 'Bad stuff',
        tags: {},
        stats: {},
        createdAt: 0,
        updatedAt: 0,
      },
      latestVersion: { version: '1.0.0', createdAt: 0, changelog: '' },
      owner: null,
    };

    const versionInfo = {
      version: {
        version: '1.0.0',
        createdAt: 0,
        changelog: '',
        security: { status: 'malicious', hasWarnings: true, checkedAt: 0, model: null },
      },
      skill: { slug: 'evil-skill', displayName: 'Evil' },
    };

    fetchSpy
      .mockReturnValueOnce(jsonResponse(listPage))
      .mockReturnValueOnce(jsonResponse(detail))
      .mockReturnValueOnce(jsonResponse(versionInfo));

    const adapter = new ClawHubAdapter({ baseUrl: 'http://localhost' });
    const events = [];
    for await (const e of adapter.sync()) {
      events.push(e);
    }

    expect(events).toHaveLength(1);
    expect(events[0].kind).toBe('skipped');
    expect(events[0].message).toContain('malicious');
  });

  it('respects limit option', async () => {
    const listPage = {
      items: [makeSkillListItem('a'), makeSkillListItem('b'), makeSkillListItem('c')],
      nextCursor: null,
    };

    // Detail / version / download for first skill only (limit=1)
    fetchSpy
      .mockReturnValueOnce(jsonResponse(listPage))
      .mockReturnValueOnce(
        jsonResponse({
          skill: {
            slug: 'a',
            displayName: 'A',
            summary: '',
            tags: {},
            stats: {},
            createdAt: 0,
            updatedAt: 0,
          },
          latestVersion: { version: '1.0.0', createdAt: 0, changelog: '' },
          owner: null,
        }),
      )
      .mockReturnValueOnce(
        jsonResponse({
          version: { version: '1.0.0', createdAt: 0, changelog: '' },
          skill: { slug: 'a', displayName: 'A' },
        }),
      )
      .mockReturnValueOnce(textResponse('content'));

    const adapter = new ClawHubAdapter({ baseUrl: 'http://localhost' });
    const events = [];
    for await (const e of adapter.sync({ limit: 1 })) {
      events.push(e);
    }

    expect(events).toHaveLength(1);
  });

  it('yields failed event on API error', async () => {
    const listPage = {
      items: [makeSkillListItem('broken')],
      nextCursor: null,
    };

    fetchSpy.mockReturnValueOnce(jsonResponse(listPage)).mockReturnValueOnce(jsonResponse({}, 500));

    const adapter = new ClawHubAdapter({ baseUrl: 'http://localhost' });
    const events = [];
    for await (const e of adapter.sync()) {
      events.push(e);
    }

    expect(events).toHaveLength(1);
    expect(events[0].kind).toBe('failed');
    expect(events[0].slug).toBe('broken');
  });
});
