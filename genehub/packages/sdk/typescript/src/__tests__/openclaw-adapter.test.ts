import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { GeneManifest } from '@nodeskai/genehub-types';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { OpenClawAdapter } from '../adapters/openclaw.js';

const TEST_MANIFEST: GeneManifest = {
  slug: 'test-gene',
  name: '测试基因',
  version: '1.0.0',
  description: '测试用基因',
  short_description: '测试',
  category: 'development',
  tags: ['ability'],
  compatibility: [{ product: 'openclaw', min_version: '0.5.0' }],
  dependencies: [],
  synergies: [],
  skill: { name: 'test-gene', always: false, content: '你是一个测试基因' },
  rules: [],
  mcp_servers: [],
};

describe('OpenClawAdapter', () => {
  let tempDir: string;
  let adapter: OpenClawAdapter;

  beforeEach(async () => {
    tempDir = await mkdtemp(join(tmpdir(), 'genehub-oc-'));
    const workspaceDir = join(tempDir, 'workspace');
    const skillsDir = join(workspaceDir, 'skills');
    const configPath = join(tempDir, 'openclaw.json');
    await mkdir(skillsDir, { recursive: true });
    await writeFile(configPath, '{}');
    await writeFile(join(workspaceDir, 'AGENTS.md'), '# Agent\n\n## Tools\n\nSome tools here\n');

    adapter = new OpenClawAdapter({
      skillsDir,
      configPath,
      workspaceDir,
    });
  });

  afterEach(async () => {
    await rm(tempDir, { recursive: true });
  });

  it('install() 应写入 SKILL.md', async () => {
    const result = await adapter.install(TEST_MANIFEST);
    expect(result.success).toBe(true);
    expect(result.slug).toBe('test-gene');
    expect(result.files.length).toBeGreaterThanOrEqual(1);
  });

  it('L1: install() 应更新 AGENTS.md', async () => {
    await adapter.install(TEST_MANIFEST);

    const agents = await readFile(join(tempDir, 'workspace', 'AGENTS.md'), 'utf-8');
    expect(agents).toContain('genehub:test-gene');
    expect(agents).toContain('测试基因');
  });

  it('L1: install() 应写入 memory 记录', async () => {
    await adapter.install(TEST_MANIFEST);

    const today = new Date().toISOString().slice(0, 10);
    const memoryPath = join(tempDir, 'workspace', 'memory', `${today}.md`);
    const memory = await readFile(memoryPath, 'utf-8');
    expect(memory).toContain('学习了');
    expect(memory).toContain('测试基因');
  });

  it('getInstalledVersion() 应返回版本号', async () => {
    await adapter.install(TEST_MANIFEST);
    const version = await adapter.getInstalledVersion('test-gene');
    expect(version).toBe('1.0.0');
  });

  it('list() 应列出已安装基因及版本', async () => {
    await adapter.install(TEST_MANIFEST);
    const list = await adapter.list();
    expect(list.length).toBe(1);
    expect(list[0].slug).toBe('test-gene');
    expect(list[0].version).toBe('1.0.0');
  });

  it('uninstall() 应移除基因并更新 AGENTS.md', async () => {
    await adapter.install(TEST_MANIFEST);
    const result = await adapter.uninstall('test-gene');
    expect(result.success).toBe(true);
    expect(await adapter.isInstalled('test-gene')).toBe(false);

    const agents = await readFile(join(tempDir, 'workspace', 'AGENTS.md'), 'utf-8');
    expect(agents).not.toContain('genehub:test-gene');
  });
});
