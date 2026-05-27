import { describe, expect, it } from 'vitest';
import {
  convertNoDeskClawGene,
  extractGeneMetadata,
  type NoDeskClawGeneRow,
} from '../nodeskclaw/converter.js';

function makeRow(overrides: Partial<NoDeskClawGeneRow> = {}): NoDeskClawGeneRow {
  return {
    id: 'cb-uuid-1',
    name: 'Code Review',
    slug: 'code-review',
    version: '1.2.0',
    description: 'Helps agents review code',
    short_description: 'Code review skill',
    category: 'development',
    tags: JSON.stringify(['ability', 'tool']),
    icon: 'magnifying-glass',
    source: 'official',
    source_ref: null,
    manifest: JSON.stringify({
      skill: { name: 'code-review', content: '# Code Review\nReview code.', always: false },
      learning: {
        objectives: ['understand PR diffs'],
        scenarios: [{ title: 'PR review', context: 'a pull request', expected_focus: 'bugs' }],
      },
      openclaw_config: { model: 'gpt-4' },
      tool_allow: ['read_file', 'write_file'],
      mcp_servers: [{ name: 'github', transport: 'stdio', command: 'gh-mcp', args: [] }],
    }),
    dependencies: JSON.stringify([{ slug: 'memory', version: '>=1.0.0' }]),
    synergies: JSON.stringify(['git-workflow']),
    parent_gene_id: null,
    install_count: 42,
    avg_rating: 4.5,
    effectiveness_score: 4.2,
    review_status: 'approved',
    is_published: true,
    created_by: 'user-abc',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-02-01T00:00:00Z',
    ...overrides,
  };
}

describe('convertNoDeskClawGene', () => {
  it('should map core fields directly', () => {
    const result = convertNoDeskClawGene(makeRow());
    expect(result.slug).toBe('code-review');
    expect(result.name).toBe('Code Review');
    expect(result.version).toBe('1.2.0');
    expect(result.description).toBe('Helps agents review code');
    expect(result.short_description).toBe('Code review skill');
    expect(result.category).toBe('development');
    expect(result.icon).toBe('magnifying-glass');
  });

  it('should parse JSON string tags into array', () => {
    const result = convertNoDeskClawGene(makeRow());
    expect(result.tags).toEqual(['ability', 'tool']);
  });

  it('should filter out invalid tags and fallback to ["ability"]', () => {
    const result = convertNoDeskClawGene(
      makeRow({ tags: JSON.stringify(['invalid', 'nonsense']) }),
    );
    expect(result.tags).toEqual(['ability']);
  });

  it('should handle null tags gracefully', () => {
    const result = convertNoDeskClawGene(makeRow({ tags: null }));
    expect(result.tags).toEqual(['ability']);
  });

  it('should handle malformed JSON tags gracefully', () => {
    const result = convertNoDeskClawGene(makeRow({ tags: '{broken json' }));
    expect(result.tags).toEqual(['ability']);
  });

  it('should map created_by to author.ref', () => {
    const result = convertNoDeskClawGene(makeRow());
    expect(result.author).toEqual({ type: 'human', name: '', ref: 'user-abc' });
  });

  it('should set default compatibility to openclaw', () => {
    const result = convertNoDeskClawGene(makeRow());
    expect(result.compatibility).toEqual([{ product: 'openclaw', min_version: '0.0.0' }]);
  });

  it('should map manifest.skill correctly', () => {
    const result = convertNoDeskClawGene(makeRow());
    expect(result.skill.name).toBe('code-review');
    expect(result.skill.content).toContain('Code Review');
    expect(result.skill.always).toBe(false);
  });

  it('should map manifest.openclaw_config + tool_allow into config.openclaw', () => {
    const result = convertNoDeskClawGene(makeRow());
    expect(result.config?.openclaw?.openclaw_config).toEqual({ model: 'gpt-4' });
    expect(result.config?.openclaw?.tool_allow).toEqual(['read_file', 'write_file']);
  });

  it('should map manifest.mcp_servers', () => {
    const result = convertNoDeskClawGene(makeRow());
    expect(result.mcp_servers).toHaveLength(1);
    expect(result.mcp_servers[0].name).toBe('github');
    expect(result.mcp_servers[0].command).toBe('gh-mcp');
  });

  it('should map manifest.learning', () => {
    const result = convertNoDeskClawGene(makeRow());
    expect(result.learning?.objectives).toEqual(['understand PR diffs']);
    expect(result.learning?.scenarios).toHaveLength(1);
  });

  it('should parse JSON string dependencies', () => {
    const result = convertNoDeskClawGene(makeRow());
    expect(result.dependencies).toEqual([{ slug: 'memory', version: '>=1.0.0' }]);
  });

  it('should handle null manifest gracefully', () => {
    const result = convertNoDeskClawGene(makeRow({ manifest: null }));
    expect(result.skill.name).toBe('code-review');
    expect(result.skill.content).toBe('');
  });

  it('should default version to 1.0.0 when empty', () => {
    const result = convertNoDeskClawGene(makeRow({ version: '' }));
    expect(result.version).toBe('1.0.0');
  });

  it('should normalize unknown category to development', () => {
    const result = convertNoDeskClawGene(makeRow({ category: 'unknown-cat' }));
    expect(result.category).toBe('development');
  });

  it('should normalize null category to development', () => {
    const result = convertNoDeskClawGene(makeRow({ category: null }));
    expect(result.category).toBe('development');
  });
});

describe('extractGeneMetadata', () => {
  it('should extract non-manifest metadata', () => {
    const meta = extractGeneMetadata(makeRow());
    expect(meta.source).toBe('official');
    expect(meta.install_count).toBe(42);
    expect(meta.avg_rating).toBe(4.5);
    expect(meta.effectiveness_score).toBe(4.2);
    expect(meta.review_status).toBe('approved');
    expect(meta.is_published).toBe(true);
  });

  it('should handle null source gracefully', () => {
    const meta = extractGeneMetadata(makeRow({ source: '' }));
    expect(meta.source).toBe('official');
  });
});
