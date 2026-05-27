/**
 * HTTP client for the ClawHub public API (clawhub.ai).
 *
 * Uses native `fetch` — no external HTTP dependencies required.
 * All methods are read-only; we never mutate ClawHub state.
 */

import { inflateRawSync } from 'node:zlib';

// ---------------------------------------------------------------------------
// Response types — mirrors clawhub-schema ApiV1* schemas
// ---------------------------------------------------------------------------

export type ClawHubSkillListItem = {
  slug: string;
  displayName: string;
  summary: string | null;
  tags: unknown;
  stats: unknown;
  createdAt: number;
  updatedAt: number;
  latestVersion?: {
    version: string;
    createdAt: number;
    changelog: string;
  };
};

export type ClawHubSkillListResponse = {
  items: ClawHubSkillListItem[];
  nextCursor: string | null;
};

export type ClawHubSkillDetail = {
  skill: {
    slug: string;
    displayName: string;
    summary: string | null;
    tags: unknown;
    stats: unknown;
    createdAt: number;
    updatedAt: number;
  } | null;
  latestVersion: {
    version: string;
    createdAt: number;
    changelog: string;
  } | null;
  owner: {
    handle: string | null;
    displayName: string | null;
    image: string | null;
  } | null;
};

export type SecurityStatus = {
  status: 'clean' | 'suspicious' | 'malicious' | 'pending' | 'error';
  hasWarnings: boolean;
  checkedAt: number | null;
  model: string | null;
};

export type ClawHubSkillVersion = {
  version: {
    version: string;
    createdAt: number;
    changelog: string;
    changelogSource?: 'auto' | 'user' | null;
    files?: unknown;
    security?: SecurityStatus;
  } | null;
  skill: {
    slug: string;
    displayName: string;
  } | null;
};

export type ClawHubSearchResult = {
  slug: string;
  displayName: string;
  summary: string | null;
  version: string | null;
  score: number;
  updatedAt?: number;
};

export type ClawHubSearchResponse = {
  results: ClawHubSearchResult[];
};

// ---------------------------------------------------------------------------
// Client options
// ---------------------------------------------------------------------------

export type ClawHubClientOptions = {
  /** Base URL, defaults to https://clawhub.ai */
  baseUrl?: string;
  /** Optional auth token for higher rate limits */
  token?: string;
  /** Request timeout in ms (default 15 000) */
  timeoutMs?: number;
};

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

export class ClawHubClient {
  private baseUrl: string;
  private headers: Record<string, string>;
  private timeoutMs: number;

  constructor(options: ClawHubClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? 'https://clawhub.ai').replace(/\/$/, '');
    this.timeoutMs = options.timeoutMs ?? 15_000;
    this.headers = {
      Accept: 'application/json',
      'Accept-Encoding': 'identity',
    };
    if (options.token) {
      this.headers.Authorization = `Bearer ${options.token}`;
    }
  }

  // -------------------------------------------------------------------------
  // Skills list (paginated)
  // -------------------------------------------------------------------------

  async listSkills(cursor?: string | null): Promise<ClawHubSkillListResponse> {
    const params = new URLSearchParams();
    if (cursor) params.set('cursor', cursor);
    return this.get<ClawHubSkillListResponse>(`/api/v1/skills?${params}`);
  }

  /**
   * Iterate through ALL pages of skills. Yields one page at a time so
   * callers can process incrementally without loading everything into memory.
   */
  async *listAllSkills(): AsyncGenerator<ClawHubSkillListItem[]> {
    let cursor: string | null = null;
    do {
      const page = await this.listSkills(cursor);
      if (page.items.length > 0) yield page.items;
      cursor = page.nextCursor;
    } while (cursor);
  }

  // -------------------------------------------------------------------------
  // Skill detail
  // -------------------------------------------------------------------------

  async getSkill(slug: string): Promise<ClawHubSkillDetail> {
    return this.get<ClawHubSkillDetail>(`/api/v1/skills/${encodeURIComponent(slug)}`);
  }

  // -------------------------------------------------------------------------
  // Skill version (includes files list + security)
  // -------------------------------------------------------------------------

  async getSkillVersion(slug: string, version: string): Promise<ClawHubSkillVersion> {
    return this.get<ClawHubSkillVersion>(
      `/api/v1/skills/${encodeURIComponent(slug)}/versions/${encodeURIComponent(version)}`,
    );
  }

  // -------------------------------------------------------------------------
  // Search
  // -------------------------------------------------------------------------

  async searchSkills(query: string): Promise<ClawHubSearchResponse> {
    const params = new URLSearchParams({ q: query });
    return this.get<ClawHubSearchResponse>(`/api/v1/search?${params}`);
  }

  // -------------------------------------------------------------------------
  // File download — returns raw text content
  // -------------------------------------------------------------------------

  async downloadFile(slug: string, version: string): Promise<string> {
    const params = new URLSearchParams({ slug, version });
    const url = `${this.baseUrl}/api/v1/download?${params}`;

    const res = await this.fetchWithTimeout(url);
    if (!res.ok) {
      throw new ClawHubApiError(res.status, `download failed for ${slug}@${version}`);
    }

    const buf = Buffer.from(await res.arrayBuffer());

    if (buf[0] === 0x50 && buf[1] === 0x4b) {
      return extractFileFromZip(buf);
    }

    return buf.toString('utf-8');
  }

  // -------------------------------------------------------------------------
  // Internal helpers
  // -------------------------------------------------------------------------

  private async get<T>(path: string): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const res = await this.fetchWithTimeout(url);
    if (!res.ok) {
      throw new ClawHubApiError(res.status, `GET ${path} failed`);
    }
    return (await res.json()) as T;
  }

  private async fetchWithTimeout(url: string): Promise<Response> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      return await fetch(url, {
        headers: this.headers,
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timer);
    }
  }
}

// ---------------------------------------------------------------------------
// Minimal ZIP extraction (no external dependencies)
//
// ZIP format: each file has a local file header starting with PK\x03\x04.
// We scan for SKILL.md (or the first .md file) and inflate its content.
// ---------------------------------------------------------------------------

const LOCAL_FILE_HEADER = 0x04034b50;

function extractFileFromZip(buf: Buffer): string {
  let offset = 0;

  while (offset + 30 <= buf.length) {
    const sig = buf.readUInt32LE(offset);
    if (sig !== LOCAL_FILE_HEADER) break;

    const method = buf.readUInt16LE(offset + 8);
    const compressedSize = buf.readUInt32LE(offset + 18);
    const uncompressedSize = buf.readUInt32LE(offset + 22);
    const nameLen = buf.readUInt16LE(offset + 26);
    const extraLen = buf.readUInt16LE(offset + 28);
    const fileName = buf.toString('utf-8', offset + 30, offset + 30 + nameLen);
    const dataStart = offset + 30 + nameLen + extraLen;

    if (
      /SKILL\.md$/i.test(fileName) ||
      /instructions\.md$/i.test(fileName) ||
      /\.md$/i.test(fileName)
    ) {
      const raw = buf.subarray(dataStart, dataStart + compressedSize);
      if (method === 8) {
        return inflateRawSync(raw, {
          maxOutputLength: uncompressedSize || 10 * 1024 * 1024,
        }).toString('utf-8');
      }
      return raw.toString('utf-8');
    }

    offset = dataStart + compressedSize;
  }

  throw new Error('no markdown file found in ZIP archive');
}

// ---------------------------------------------------------------------------
// Error class
// ---------------------------------------------------------------------------

export class ClawHubApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(`ClawHub API ${status}: ${message}`);
    this.name = 'ClawHubApiError';
  }
}
