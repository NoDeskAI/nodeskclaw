import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { getManifestMock, mockAdapter } = vi.hoisted(() => {
  const getManifestMock = vi.fn();
  const mockAdapter = {
    product: 'generic',
    isInstalled: vi.fn().mockResolvedValue(false),
    install: vi.fn().mockResolvedValue({
      success: true,
      slug: 'foo',
      version: '1.0.0',
      files: ['foo.js'],
      needsRestart: false,
      dependencies: [],
    }),
  };
  return { getManifestMock, mockAdapter };
});

const VALID_MANIFEST = {
  slug: 'foo',
  name: 'Foo',
  version: '1.0.0',
  description: 'Test',
  short_description: 'Test',
  category: 'development' as const,
  tags: ['ability'] as const,
  compatibility: [{ product: 'openclaw' as const, min_version: '0.5.0' }],
  skill: { name: 'foo', content: 'test' },
};

vi.mock('@nodeskai/genehub-sdk', () => ({
  GeneHubClient: vi.fn().mockImplementation(() => ({
    getManifest: getManifestMock,
    downloadArchive: vi.fn().mockRejectedValue(new Error('skip')),
    reportInstall: vi.fn().mockResolvedValue(undefined),
  })),
  getAdapter: vi.fn().mockReturnValue(mockAdapter),
  detectAdapter: vi.fn().mockResolvedValue(mockAdapter),
  LearningEngine: vi.fn(),
}));

vi.mock('ora', () => ({
  default: vi.fn().mockReturnValue({
    start: vi.fn().mockReturnThis(),
    succeed: vi.fn(),
    fail: vi.fn(),
    warn: vi.fn(),
  }),
}));

vi.mock('../config.js', () => ({
  loadConfig: vi.fn().mockResolvedValue({ registryUrl: 'https://hub.example.com' }),
}));

describe('parseSlugVersion (via install)', () => {
  beforeEach(() => {
    vi.resetModules();
    getManifestMock.mockReset();
    getManifestMock.mockResolvedValue(VALID_MANIFEST);
  });

  it('slug@version 应正确解析为 slug 和 version', async () => {
    const { program } = await import('../index.js');
    const exitSpy = vi.spyOn(process, 'exit').mockImplementation(() => undefined as never);
    const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

    await program.parseAsync(['node', 'genehub', 'install', 'foo@1.0.0']);

    expect(getManifestMock).toHaveBeenCalledWith('foo', '1.0.0');
    exitSpy.mockRestore();
    consoleSpy.mockRestore();
  });

  it('仅 slug 无 version 时应传 undefined', async () => {
    getManifestMock.mockResolvedValue({ ...VALID_MANIFEST, slug: 'bar', version: '2.0.0' });
    mockAdapter.install.mockResolvedValue({
      success: true,
      slug: 'bar',
      version: '2.0.0',
      files: ['bar.js'],
      needsRestart: false,
      dependencies: [],
    });

    const { program } = await import('../index.js');
    const exitSpy = vi.spyOn(process, 'exit').mockImplementation(() => undefined as never);
    const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

    await program.parseAsync(['node', 'genehub', 'install', 'bar']);

    expect(getManifestMock).toHaveBeenCalledWith('bar', undefined);
    exitSpy.mockRestore();
    consoleSpy.mockRestore();
  });

  it('slug 中含多个 @ 时应以最后一个 @ 分割', async () => {
    getManifestMock.mockResolvedValue({ ...VALID_MANIFEST, slug: 'foo-bar', version: '1.0.0' });
    mockAdapter.install.mockResolvedValue({
      success: true,
      slug: 'foo-bar',
      version: '1.0.0',
      files: ['foo.js'],
      needsRestart: false,
      dependencies: [],
    });

    const { program } = await import('../index.js');
    const exitSpy = vi.spyOn(process, 'exit').mockImplementation(() => undefined as never);
    const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

    await program.parseAsync(['node', 'genehub', 'install', 'foo-bar@1.0.0']);

    expect(getManifestMock).toHaveBeenCalledWith('foo-bar', '1.0.0');
    exitSpy.mockRestore();
    consoleSpy.mockRestore();
  });
});

describe('config module', () => {
  let tempDir: string;

  beforeEach(async () => {
    tempDir = await mkdtemp(join(tmpdir(), 'genehub-commands-test-'));
    vi.resetModules();
    vi.unmock('../config.js');
  });

  afterEach(async () => {
    vi.restoreAllMocks();
    await rm(tempDir, { recursive: true, force: true });
  });

  it('无配置文件时应返回默认 registryUrl', async () => {
    vi.doMock('node:os', async (importOriginal) => {
      const original = await importOriginal<typeof import('node:os')>();
      return { ...original, homedir: () => tempDir };
    });
    const { loadConfig } = await import('../config.js');
    const config = await loadConfig();
    expect(config.registryUrl).toBe('https://genehub.nodeskai.com');
  });

  it('配置文件存在时应读取并合并', async () => {
    const { mkdir, writeFile } = await import('node:fs/promises');
    const { join } = await import('node:path');
    const configDir = join(tempDir, '.genehub');
    await mkdir(configDir, { recursive: true });
    await writeFile(
      join(configDir, 'config.json'),
      JSON.stringify({ registryUrl: 'https://custom.example.com', token: 'secret' }),
    );
    vi.doMock('node:os', async (importOriginal) => {
      const original = await importOriginal<typeof import('node:os')>();
      return { ...original, homedir: () => tempDir };
    });
    const { loadConfig } = await import('../config.js');
    const config = await loadConfig();
    expect(config.registryUrl).toBe('https://custom.example.com');
    expect(config.token).toBe('secret');
  });
});

describe('command registration', () => {
  it('所有命令应正确注册到 program', async () => {
    const { program } = await import('../index.js');
    const names = program.commands.map((c) => c.name());
    const expected = [
      'auth',
      'install',
      'uninstall',
      'search',
      'info',
      'list',
      'publish',
      'init',
      'config',
      'learn',
      'genome',
      'template',
    ];
    for (const name of expected) {
      expect(names).toContain(name);
    }
    expect(names).toHaveLength(expected.length);
  });
});
