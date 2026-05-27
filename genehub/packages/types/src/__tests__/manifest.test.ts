import { describe, expect, it } from 'vitest';
import { GeneManifestSchema } from '../manifest.js';

const VALID_MANIFEST = {
  slug: 'code-review',
  name: '代码审查专家',
  version: '1.0.0',
  description: '帮助 Agent 进行深度代码审查',
  short_description: '深度代码审查',
  category: 'development',
  tags: ['ability'],
  compatibility: [{ product: 'openclaw', min_version: '0.5.0' }],
  skill: {
    name: 'code-review',
    content: '你是一位代码审查专家',
  },
};

describe('GeneManifestSchema', () => {
  it('应接受合法的 manifest', () => {
    const result = GeneManifestSchema.safeParse(VALID_MANIFEST);
    expect(result.success).toBe(true);
  });

  it('应接受包含全部字段的 manifest', () => {
    const full = {
      ...VALID_MANIFEST,
      icon: 'search-code',
      author: { type: 'human', name: 'NoDeskAI' },
      dependencies: [{ slug: 'analytical-thinking', version: '>=1.0.0' }],
      synergies: ['clean-code'],
      rules: [{ name: 'style', content: '使用中文输出' }],
      config: {
        openclaw: { tool_allow: ['file_read'] },
        nanobot: { capabilities: [], requires: { bins: ['gh'] } },
      },
      mcp_servers: [{ name: 'github', command: 'npx', args: ['-y', '@mcp/github'] }],
      learning: {
        force_deep_learn: false,
        objectives: ['掌握审查维度'],
        scenarios: [{ title: '审查路由', context: 'SQL 注入', expected_focus: 'security' }],
      },
    };

    const result = GeneManifestSchema.safeParse(full);
    expect(result.success).toBe(true);
  });

  it('应拒绝缺少 slug 的 manifest', () => {
    const { slug: _, ...noSlug } = VALID_MANIFEST;
    const result = GeneManifestSchema.safeParse(noSlug);
    expect(result.success).toBe(false);
  });

  it('应拒绝非法 slug 格式', () => {
    const result = GeneManifestSchema.safeParse({ ...VALID_MANIFEST, slug: 'BAD SLUG!' });
    expect(result.success).toBe(false);
  });

  it('应拒绝非法版本号', () => {
    const result = GeneManifestSchema.safeParse({ ...VALID_MANIFEST, version: 'abc' });
    expect(result.success).toBe(false);
  });

  it('应拒绝缺少 compatibility 的 manifest', () => {
    const result = GeneManifestSchema.safeParse({ ...VALID_MANIFEST, compatibility: [] });
    expect(result.success).toBe(false);
  });

  it('应拒绝非法 category', () => {
    const result = GeneManifestSchema.safeParse({ ...VALID_MANIFEST, category: 'unknown' });
    expect(result.success).toBe(false);
  });

  it('应拒绝非法 tags', () => {
    const result = GeneManifestSchema.safeParse({ ...VALID_MANIFEST, tags: ['invalid'] });
    expect(result.success).toBe(false);
  });

  it('应为可选字段设置默认值', () => {
    const result = GeneManifestSchema.parse(VALID_MANIFEST);
    expect(result.dependencies).toEqual([]);
    expect(result.synergies).toEqual([]);
    expect(result.rules).toEqual([]);
    expect(result.mcp_servers).toEqual([]);
  });
});
