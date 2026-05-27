import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockSearchSkills, mockDownloadFile, mockLocalRows, mockGitea } = vi.hoisted(() => ({
  mockSearchSkills: vi.fn(),
  mockDownloadFile: vi.fn(),
  mockLocalRows: vi.fn(),
  mockGitea: {
    isGiteaAvailable: vi.fn().mockResolvedValue(true),
    repoExists: vi.fn().mockResolvedValue(false),
    createRepo: vi.fn().mockResolvedValue(undefined),
    uploadFiles: vi.fn().mockResolvedValue({ sha: 'abc123' }),
    createTag: vi.fn().mockResolvedValue(undefined),
    getRepoUrl: vi.fn().mockReturnValue('genes/test-slug'),
  },
}));

vi.mock('../adapters/clawhub/client.js', () => ({
  ClawHubClient: vi.fn().mockImplementation(() => ({
    searchSkills: mockSearchSkills,
    downloadFile: mockDownloadFile,
  })),
}));
vi.mock('../services/gitea-service.js', () => mockGitea);
vi.mock('../db/index.js', () => {
  const createSelectChain = () => {
    const chain = {
      from: vi.fn().mockReturnThis(),
      where: vi.fn().mockImplementation(() => {
        const syncResult: unknown[] = [];
        const limitChain = {
          orderBy: vi.fn().mockReturnValue({
            limit: vi.fn().mockResolvedValue(mockLocalRows()),
          }),
        };
        return Object.assign(Promise.resolve(syncResult), limitChain);
      }),
    };
    return chain;
  };
  return {
    db: {
      select: vi.fn().mockImplementation(() => createSelectChain()),
      insert: vi.fn().mockReturnValue({
        values: vi.fn().mockReturnValue({
          onConflictDoNothing: vi.fn().mockReturnValue({
            returning: vi.fn().mockResolvedValue([{ id: 'gene-1', version: '1.0.0' }]),
          }),
        }),
      }),
      update: vi.fn().mockReturnValue({
        set: vi.fn().mockReturnValue({
          where: vi.fn().mockResolvedValue(undefined),
        }),
      }),
      execute: vi.fn().mockResolvedValue(undefined),
    },
    schema: {
      genes: {
        id: 'id',
        slug: 'slug',
        version: 'version',
        deleted_at: 'deleted_at',
        is_published: 'is_published',
        name: 'name',
        short_description: 'short_description',
        install_count: 'install_count',
        tags: 'tags',
        category: 'category',
        avg_rating: 'avg_rating',
      },
      geneVersions: { gene_id: 'gene_id', is_latest: 'is_latest' },
    },
  };
});

vi.mock('../services/gene-events.js', () => ({
  emitGeneEvent: vi.fn().mockResolvedValue(undefined),
}));

import { federatedSearch } from '../services/federated-search.js';

function makeLocalRow(slug: string, idx: number) {
  return {
    slug,
    name: slug,
    short_description: `${slug} desc`,
    version: '1.0.0',
    category: 'development',
    tags: [],
    install_count: 10 - idx,
    avg_rating: 4.5,
  };
}

function makeClawHubResult(slug: string, score: number) {
  return {
    slug,
    displayName: slug,
    summary: `${slug} summary`,
    version: '1.0.0',
    score,
  };
}

describe('federatedSearch', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLocalRows.mockReturnValue([]);
  });

  it('外部源失败或超时时仅返回本地结果', async () => {
    mockLocalRows.mockReturnValue([makeLocalRow('local-a', 0), makeLocalRow('local-b', 1)]);
    mockSearchSkills.mockRejectedValue(new Error('timeout'));

    const result = await federatedSearch('test', { limit: 20 });

    expect(result.items).toHaveLength(2);
    expect(result.items.every((g) => g.source === 'local')).toBe(true);
    expect(result.sources).toEqual({ local: 2, clawhub: 0 });
    expect(result.query).toBe('test');
    expect(result.total).toBe(2);
  });

  it('合并多个来源的结果并按分数排序', async () => {
    mockLocalRows.mockReturnValue([makeLocalRow('local-a', 0)]);
    mockSearchSkills.mockResolvedValue({
      results: [makeClawHubResult('clawhub-x', 0.9), makeClawHubResult('clawhub-y', 0.5)],
    });

    const result = await federatedSearch('test', { limit: 20 });

    expect(result.items.length).toBeGreaterThanOrEqual(2);
    expect(result.sources.local).toBe(1);
    expect(result.sources.clawhub).toBe(2);
    for (let i = 1; i < result.items.length; i++) {
      expect(result.items[i].score).toBeLessThanOrEqual(result.items[i - 1].score);
    }
  });

  it('相同 slug 时去重，本地结果优先', async () => {
    mockLocalRows.mockReturnValue([makeLocalRow('shared', 0)]);
    mockSearchSkills.mockResolvedValue({
      results: [makeClawHubResult('shared', 1), makeClawHubResult('clawhub-only', 0.8)],
    });

    const result = await federatedSearch('test', { limit: 20 });

    const slugs = result.items.map((g) => g.slug);
    expect(slugs.filter((s) => s === 'shared')).toHaveLength(1);
    const sharedItem = result.items.find((g) => g.slug === 'shared');
    expect(sharedItem?.source).toBe('local');
    expect(result.items.some((g) => g.slug === 'clawhub-only')).toBe(true);
  });

  it('空查询时正常返回不抛错', async () => {
    mockLocalRows.mockReturnValue([]);
    mockSearchSkills.mockResolvedValue({ results: [] });

    const result = await federatedSearch('', { limit: 20 });

    expect(result.query).toBe('');
    expect(result.items).toEqual([]);
    expect(result.total).toBe(0);
    expect(result.sources).toEqual({ local: 0, clawhub: 0 });
  });

  it('ClawHub 分数归一化后最大值不超过 0.85', async () => {
    mockLocalRows.mockReturnValue([]);
    mockSearchSkills.mockResolvedValue({
      results: [
        makeClawHubResult('high', 1),
        makeClawHubResult('mid', 0.5),
        makeClawHubResult('low', 0.25),
      ],
    });

    const result = await federatedSearch('test', { limit: 20 });

    const clawhubItems = result.items.filter((g) => g.source === 'clawhub');
    expect(clawhubItems).toHaveLength(3);
    const maxScore = Math.max(...clawhubItems.map((g) => g.score));
    expect(maxScore).toBeLessThanOrEqual(0.85);
    const highItem = clawhubItems.find((g) => g.slug === 'high');
    expect(highItem?.score).toBeCloseTo(0.85, 5);
    expect(clawhubItems.find((g) => g.slug === 'mid')?.score).toBeCloseTo(0.425, 5);
    expect(clawhubItems.find((g) => g.slug === 'low')?.score).toBeCloseTo(0.2125, 5);
  });

  it('后台同步时从 ClawHub 下载文件并上传到 Gitea', async () => {
    mockLocalRows.mockReturnValue([]);
    mockSearchSkills.mockResolvedValue({
      results: [makeClawHubResult('new-skill', 0.9)],
    });
    mockDownloadFile.mockResolvedValue('# Skill Content\nThis is a test skill.');
    mockGitea.isGiteaAvailable.mockResolvedValue(true);
    mockGitea.repoExists.mockResolvedValue(false);
    mockGitea.uploadFiles.mockResolvedValue({ sha: 'commit-sha-123' });
    mockGitea.getRepoUrl.mockReturnValue('genes/new-skill');

    await federatedSearch('test', { limit: 20 });

    // 等待后台同步完成
    await new Promise((r) => setTimeout(r, 200));

    expect(mockDownloadFile).toHaveBeenCalledWith('new-skill', '1.0.0');
    expect(mockGitea.isGiteaAvailable).toHaveBeenCalled();
    expect(mockGitea.createRepo).toHaveBeenCalledWith('new-skill', expect.any(String));
    expect(mockGitea.uploadFiles).toHaveBeenCalledWith(
      'new-skill',
      expect.objectContaining({
        'gene.yaml': expect.any(String),
        'SKILL.md': '# Skill Content\nThis is a test skill.',
      }),
      expect.stringContaining('v1.0.0'),
    );
    expect(mockGitea.createTag).toHaveBeenCalledWith('new-skill', 'v1.0.0', 'commit-sha-123');
  });

  it('Gitea 不可用时仍然入库但不写文件', async () => {
    mockLocalRows.mockReturnValue([]);
    mockSearchSkills.mockResolvedValue({
      results: [makeClawHubResult('no-gitea', 0.9)],
    });
    mockDownloadFile.mockResolvedValue('# Content');
    mockGitea.isGiteaAvailable.mockResolvedValue(false);

    await federatedSearch('test', { limit: 20 });
    await new Promise((r) => setTimeout(r, 200));

    expect(mockGitea.createRepo).not.toHaveBeenCalled();
    expect(mockGitea.uploadFiles).not.toHaveBeenCalled();
  });

  it('ClawHub 下载失败时降级处理，仍然完成入库', async () => {
    mockLocalRows.mockReturnValue([]);
    mockSearchSkills.mockResolvedValue({
      results: [makeClawHubResult('download-fail', 0.9)],
    });
    mockDownloadFile.mockRejectedValue(new Error('404 not found'));
    mockGitea.isGiteaAvailable.mockResolvedValue(true);
    mockGitea.repoExists.mockResolvedValue(false);
    mockGitea.uploadFiles.mockResolvedValue({ sha: 'fallback-sha' });
    mockGitea.getRepoUrl.mockReturnValue('genes/download-fail');

    await federatedSearch('test', { limit: 20 });
    await new Promise((r) => setTimeout(r, 200));

    // gene.yaml 仍然被上传（不含 SKILL.md）
    expect(mockGitea.uploadFiles).toHaveBeenCalledWith(
      'download-fail',
      expect.not.objectContaining({ 'SKILL.md': expect.any(String) }),
      expect.any(String),
    );
  });
});
