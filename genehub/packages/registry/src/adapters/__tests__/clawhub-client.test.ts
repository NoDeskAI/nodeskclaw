import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ClawHubApiError, ClawHubClient } from '../clawhub/client.js';

const MOCK_BASE = 'https://test-clawhub.local';

function makeClient(opts: { token?: string } = {}) {
  return new ClawHubClient({ baseUrl: MOCK_BASE, timeoutMs: 5000, token: opts.token });
}

describe('ClawHubClient', () => {
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

  function textResponse(text: string, status = 200) {
    return Promise.resolve(new Response(text, { status }));
  }

  // -----------------------------------------------------------------------
  // listSkills
  // -----------------------------------------------------------------------

  describe('listSkills', () => {
    it('calls correct URL without cursor', async () => {
      fetchSpy.mockReturnValueOnce(jsonResponse({ items: [], nextCursor: null }));
      const client = makeClient();
      const result = await client.listSkills();
      expect(result.items).toEqual([]);
      expect(result.nextCursor).toBeNull();
      const url = fetchSpy.mock.calls[0][0] as string;
      expect(url).toBe(`${MOCK_BASE}/api/v1/skills?`);
    });

    it('passes cursor as query param', async () => {
      fetchSpy.mockReturnValueOnce(jsonResponse({ items: [], nextCursor: null }));
      const client = makeClient();
      await client.listSkills('abc123');
      const url = fetchSpy.mock.calls[0][0] as string;
      expect(url).toContain('cursor=abc123');
    });
  });

  // -----------------------------------------------------------------------
  // listAllSkills (paginated generator)
  // -----------------------------------------------------------------------

  describe('listAllSkills', () => {
    it('iterates through multiple pages', async () => {
      const page1 = { items: [{ slug: 'a' }], nextCursor: 'p2' };
      const page2 = { items: [{ slug: 'b' }], nextCursor: null };
      fetchSpy.mockReturnValueOnce(jsonResponse(page1)).mockReturnValueOnce(jsonResponse(page2));

      const client = makeClient();
      const pages: unknown[][] = [];
      for await (const page of client.listAllSkills()) {
        pages.push(page);
      }
      expect(pages).toHaveLength(2);
      expect(fetchSpy).toHaveBeenCalledTimes(2);
    });

    it('yields nothing for empty first page', async () => {
      fetchSpy.mockReturnValueOnce(jsonResponse({ items: [], nextCursor: null }));
      const client = makeClient();
      const pages: unknown[][] = [];
      for await (const page of client.listAllSkills()) {
        pages.push(page);
      }
      expect(pages).toHaveLength(0);
    });
  });

  // -----------------------------------------------------------------------
  // getSkill
  // -----------------------------------------------------------------------

  describe('getSkill', () => {
    it('calls correct URL', async () => {
      fetchSpy.mockReturnValueOnce(
        jsonResponse({ skill: { slug: 'foo' }, latestVersion: null, owner: null }),
      );
      const client = makeClient();
      const result = await client.getSkill('foo');
      expect(result.skill?.slug).toBe('foo');
      const url = fetchSpy.mock.calls[0][0] as string;
      expect(url).toBe(`${MOCK_BASE}/api/v1/skills/foo`);
    });

    it('encodes slug with special characters', async () => {
      fetchSpy.mockReturnValueOnce(jsonResponse({ skill: null, latestVersion: null, owner: null }));
      const client = makeClient();
      await client.getSkill('foo/bar');
      const url = fetchSpy.mock.calls[0][0] as string;
      expect(url).toContain('foo%2Fbar');
    });
  });

  // -----------------------------------------------------------------------
  // getSkillVersion
  // -----------------------------------------------------------------------

  describe('getSkillVersion', () => {
    it('calls correct URL', async () => {
      fetchSpy.mockReturnValueOnce(jsonResponse({ version: null, skill: null }));
      const client = makeClient();
      await client.getSkillVersion('my-skill', '1.2.3');
      const url = fetchSpy.mock.calls[0][0] as string;
      expect(url).toBe(`${MOCK_BASE}/api/v1/skills/my-skill/versions/1.2.3`);
    });
  });

  // -----------------------------------------------------------------------
  // searchSkills
  // -----------------------------------------------------------------------

  describe('searchSkills', () => {
    it('sends query as q param', async () => {
      fetchSpy.mockReturnValueOnce(jsonResponse({ results: [] }));
      const client = makeClient();
      const result = await client.searchSkills('code review');
      expect(result.results).toEqual([]);
      const url = fetchSpy.mock.calls[0][0] as string;
      expect(url).toContain('q=code+review');
    });
  });

  // -----------------------------------------------------------------------
  // downloadFile
  // -----------------------------------------------------------------------

  describe('downloadFile', () => {
    it('returns text content', async () => {
      fetchSpy.mockReturnValueOnce(textResponse('# Instructions\nDo stuff.'));
      const client = makeClient();
      const text = await client.downloadFile('my-skill', '1.0.0');
      expect(text).toContain('Instructions');
    });

    it('throws ClawHubApiError on 404', async () => {
      fetchSpy.mockReturnValueOnce(textResponse('', 404));
      const client = makeClient();
      await expect(client.downloadFile('missing', '1.0.0')).rejects.toThrow(ClawHubApiError);
    });
  });

  // -----------------------------------------------------------------------
  // Error handling
  // -----------------------------------------------------------------------

  describe('error handling', () => {
    it('throws ClawHubApiError on non-200 response', async () => {
      fetchSpy.mockReturnValueOnce(jsonResponse({ error: 'nope' }, 500));
      const client = makeClient();
      await expect(client.listSkills()).rejects.toThrow(ClawHubApiError);
    });

    it('includes status code in error', async () => {
      fetchSpy.mockReturnValueOnce(jsonResponse({}, 403));
      const client = makeClient();
      try {
        await client.getSkill('x');
      } catch (e) {
        expect(e).toBeInstanceOf(ClawHubApiError);
        expect((e as ClawHubApiError).status).toBe(403);
      }
    });
  });

  // -----------------------------------------------------------------------
  // Auth headers
  // -----------------------------------------------------------------------

  describe('authentication', () => {
    it('sends Authorization header when token is set', async () => {
      fetchSpy.mockReturnValueOnce(jsonResponse({ items: [], nextCursor: null }));
      const client = makeClient({ token: 'my-secret' });
      await client.listSkills();
      const opts = fetchSpy.mock.calls[0][1] as RequestInit;
      expect((opts.headers as Record<string, string>).Authorization).toBe('Bearer my-secret');
    });

    it('omits Authorization header when no token', async () => {
      fetchSpy.mockReturnValueOnce(jsonResponse({ items: [], nextCursor: null }));
      const client = makeClient();
      await client.listSkills();
      const opts = fetchSpy.mock.calls[0][1] as RequestInit;
      expect((opts.headers as Record<string, string>).Authorization).toBeUndefined();
    });
  });
});
