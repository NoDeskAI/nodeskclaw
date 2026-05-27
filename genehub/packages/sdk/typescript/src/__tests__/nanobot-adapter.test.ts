import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { GeneManifest } from '@nodeskai/genehub-types';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NanobotAdapter } from '../adapters/nanobot.js';

const TEST_MANIFEST: GeneManifest = {
  slug: 'test-gene',
  name: '测试基因',
  version: '1.0.0',
  description: '测试用基因',
  short_description: '测试',
  category: 'development',
  tags: ['ability'],
  compatibility: [{ product: 'nanobot', min_version: '0.1.0' }],
  dependencies: [],
  synergies: [],
  skill: { name: 'test-gene', always: false, content: '你是一个测试基因' },
  rules: [],
  mcp_servers: [],
};

describe('NanobotAdapter', () => {
  let tempDir: string;
  let adapter: NanobotAdapter;

  beforeEach(async () => {
    tempDir = await mkdtemp(join(tmpdir(), 'genehub-nanobot-'));
    const workspace = join(tempDir, 'workspace');
    const configPath = join(tempDir, 'config.json');
    await mkdir(join(workspace, 'skills'), { recursive: true });
    await writeFile(configPath, '{}');

    adapter = new NanobotAdapter({ workspace, configPath });
  });

  afterEach(async () => {
    await rm(tempDir, { recursive: true });
    vi.restoreAllMocks();
  });

  it('detect() 当 config.json 存在时应返回 true', async () => {
    expect(await adapter.detect()).toBe(true);
  });

  it('detect() 当 config.json 不存在时应返回 false', async () => {
    const noConfigAdapter = new NanobotAdapter({
      workspace: join(tempDir, 'workspace'),
      configPath: join(tempDir, 'nonexistent.json'),
    });
    expect(await noConfigAdapter.detect()).toBe(false);
  });

  it('install() 应写入 workspace/skills/<name>/SKILL.md', async () => {
    const result = await adapter.install(TEST_MANIFEST);
    expect(result.success).toBe(true);
    expect(result.slug).toBe('test-gene');
    expect(result.files.length).toBeGreaterThanOrEqual(1);

    const skillPath = join(tempDir, 'workspace', 'skills', 'test-gene', 'SKILL.md');
    const content = await readFile(skillPath, 'utf-8');
    expect(content).toContain('测试基因');
    expect(content).toMatch(/version:\s*1\.0\.0/);
  });

  it('uninstall() 应删除技能目录', async () => {
    await adapter.install(TEST_MANIFEST);
    const result = await adapter.uninstall('test-gene');
    expect(result.success).toBe(true);
    expect(await adapter.isInstalled('test-gene')).toBe(false);
  });

  it('isInstalled() 安装后应返回 true，未安装返回 false', async () => {
    expect(await adapter.isInstalled('test-gene')).toBe(false);
    await adapter.install(TEST_MANIFEST);
    expect(await adapter.isInstalled('test-gene')).toBe(true);
  });

  it('getInstalledVersion() 应从 SKILL.md front matter 解析版本', async () => {
    await adapter.install(TEST_MANIFEST);
    const version = await adapter.getInstalledVersion('test-gene');
    expect(version).toBe('1.0.0');
  });

  it('getInstalledVersion() 未安装时应返回 null', async () => {
    expect(await adapter.getInstalledVersion('test-gene')).toBeNull();
  });

  it('list() 应遍历 skills 目录并返回已安装基因', async () => {
    await adapter.install(TEST_MANIFEST);
    const list = await adapter.list();
    expect(list.length).toBe(1);
    expect(list[0].slug).toBe('test-gene');
    expect(list[0].version).toBe('1.0.0');
  });

  it('list() 无技能时应返回空数组', async () => {
    const list = await adapter.list();
    expect(list).toEqual([]);
  });

  it('mergeNanobotMcpConfig() 应将 MCP 配置合并到 config.json', async () => {
    const manifestWithMcp: GeneManifest = {
      ...TEST_MANIFEST,
      mcp_servers: [
        {
          name: 'test-mcp',
          transport: 'stdio',
          command: 'npx',
          args: ['-y', 'test-server'],
          env: {},
        },
      ],
    };
    await adapter.install(manifestWithMcp);

    const configPath = join(tempDir, 'config.json');
    const raw = await readFile(configPath, 'utf-8');
    const config = JSON.parse(raw);
    expect(config.tools?.mcpServers?.['test-mcp']).toBeDefined();
    expect(config.tools.mcpServers['test-mcp'].command).toBe('npx');
    expect(config.tools.mcpServers['test-mcp'].args).toEqual(['-y', 'test-server']);
  });

  it('mergeNanobotMcpConfig() 当 config.json 不存在时应 console.warn 且不抛错', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const noConfigAdapter = new NanobotAdapter({
      workspace: join(tempDir, 'workspace'),
      configPath: join(tempDir, 'missing.json'),
    });
    const manifestWithMcp: GeneManifest = {
      ...TEST_MANIFEST,
      mcp_servers: [{ name: 'mcp1', transport: 'stdio', command: 'cmd', args: [], env: {} }],
    };

    await noConfigAdapter.install(manifestWithMcp);

    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('[NanobotAdapter]'),
      expect.any(String),
      expect.any(String),
    );
    warnSpy.mockRestore();
  });

  it('mergeNanobotMcpConfig() 当 config.json 内容非对象时应 warn 且不写入', async () => {
    const invalidConfigPath = join(tempDir, 'invalid-object.json');
    await writeFile(invalidConfigPath, 'null', 'utf-8');
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const badAdapter = new NanobotAdapter({
      workspace: join(tempDir, 'ws2'),
      configPath: invalidConfigPath,
    });
    const manifestWithMcp: GeneManifest = {
      ...TEST_MANIFEST,
      mcp_servers: [{ name: 'mcp1', transport: 'stdio', command: 'cmd', args: [], env: {} }],
    };

    await badAdapter.install(manifestWithMcp);

    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('内容不是有效对象'),
      invalidConfigPath,
    );
    const stillRaw = await readFile(invalidConfigPath, 'utf-8');
    expect(stillRaw).toBe('null');
    warnSpy.mockRestore();
  });

  it('mergeNanobotMcpConfig() 当 config.json JSON 格式错误时应 warn 解析失败', async () => {
    const badJsonPath = join(tempDir, 'bad-json.json');
    await writeFile(badJsonPath, '{ invalid }', 'utf-8');
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const badAdapter = new NanobotAdapter({
      workspace: join(tempDir, 'ws3'),
      configPath: badJsonPath,
    });
    const manifestWithMcp: GeneManifest = {
      ...TEST_MANIFEST,
      mcp_servers: [{ name: 'mcp1', transport: 'stdio', command: 'cmd', args: [], env: {} }],
    };

    await badAdapter.install(manifestWithMcp);

    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('解析失败'),
      expect.any(String),
      expect.any(String),
    );
    warnSpy.mockRestore();
  });
});
