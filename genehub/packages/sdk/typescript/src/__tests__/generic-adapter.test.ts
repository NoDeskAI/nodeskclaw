import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { GeneManifest } from '@nodeskai/genehub-types';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { GenericAdapter } from '../adapters/generic.js';

const TEST_MANIFEST: GeneManifest = {
  slug: 'test-gene',
  name: '测试基因',
  version: '1.0.0',
  description: '测试用基因',
  short_description: '测试',
  category: 'development',
  tags: ['ability'],
  compatibility: [{ product: 'generic', min_version: '0.0.0' }],
  dependencies: [],
  synergies: [],
  skill: { name: 'test-gene', always: false, content: '你是一个测试基因' },
  rules: [],
  mcp_servers: [],
};

describe('GenericAdapter', () => {
  let tempDir: string;
  let adapter: GenericAdapter;

  beforeEach(async () => {
    tempDir = await mkdtemp(join(tmpdir(), 'genehub-test-'));
    adapter = new GenericAdapter({ genesDir: tempDir });
  });

  afterEach(async () => {
    await rm(tempDir, { recursive: true });
  });

  it('detect() 应始终返回 true', async () => {
    expect(await adapter.detect()).toBe(true);
  });

  it('install() 应写入 gene.yaml 和 SKILL.md', async () => {
    const result = await adapter.install(TEST_MANIFEST);
    expect(result.success).toBe(true);
    expect(result.slug).toBe('test-gene');
    expect(result.version).toBe('1.0.0');
    expect(result.files.length).toBe(2);
  });

  it('isInstalled() 安装后应返回 true', async () => {
    expect(await adapter.isInstalled('test-gene')).toBe(false);
    await adapter.install(TEST_MANIFEST);
    expect(await adapter.isInstalled('test-gene')).toBe(true);
  });

  it('list() 应列出已安装的基因', async () => {
    await adapter.install(TEST_MANIFEST);
    const list = await adapter.list();
    expect(list.length).toBe(1);
    expect(list[0].slug).toBe('test-gene');
  });

  it('uninstall() 应移除基因', async () => {
    await adapter.install(TEST_MANIFEST);
    const result = await adapter.uninstall('test-gene');
    expect(result.success).toBe(true);
    expect(await adapter.isInstalled('test-gene')).toBe(false);
  });

  it('getInstalledVersion() 应返回已安装版本', async () => {
    await adapter.install(TEST_MANIFEST);
    const version = await adapter.getInstalledVersion('test-gene');
    expect(version).toBe('1.0.0');
  });
});
