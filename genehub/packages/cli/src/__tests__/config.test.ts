import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

describe('CLI Config', () => {
  let tempDir: string;

  beforeEach(async () => {
    tempDir = await mkdtemp(join(tmpdir(), 'genehub-cli-test-'));
    vi.resetModules();
  });

  afterEach(async () => {
    vi.restoreAllMocks();
    await rm(tempDir, { recursive: true });
  });

  it('默认 registryUrl 应为 genehub.nodeskai.com（无配置文件时）', async () => {
    vi.doMock('node:os', async (importOriginal) => {
      const original = await importOriginal<typeof import('node:os')>();
      return { ...original, homedir: () => tempDir };
    });
    const { loadConfig } = await import('../config.js');
    const config = await loadConfig();
    expect(config.registryUrl).toBe('https://genehub.nodeskai.com');
  });

  it('配置文件存在时应合并配置', async () => {
    const configDir = join(tempDir, '.genehub');
    const { mkdir } = await import('node:fs/promises');
    await mkdir(configDir, { recursive: true });
    await writeFile(
      join(configDir, 'config.json'),
      JSON.stringify({ registryUrl: 'https://hub.example.com', token: 'test-tok' }),
    );
    vi.doMock('node:os', async (importOriginal) => {
      const original = await importOriginal<typeof import('node:os')>();
      return { ...original, homedir: () => tempDir };
    });
    const { loadConfig } = await import('../config.js');
    const config = await loadConfig();
    expect(config.registryUrl).toBe('https://hub.example.com');
    expect(config.token).toBe('test-tok');
  });
});
