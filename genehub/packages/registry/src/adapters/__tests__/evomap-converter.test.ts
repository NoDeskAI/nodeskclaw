import { describe, expect, it } from 'vitest';
import type { GepCapsule, GepGene, RecommendationItem } from '../evomap/client.js';
import {
  convertGepCapsule,
  convertGepGene,
  convertRecommendation,
  extractEvoMapMetadata,
} from '../evomap/converter.js';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeGene(overrides: Partial<GepGene> = {}): GepGene {
  return {
    type: 'Gene',
    id: 'gene_gep_repair_from_errors',
    category: 'repair',
    signals_match: ['error', 'exception', 'failed'],
    preconditions: ['signals contains error-related indicators'],
    strategy: [
      'Extract structured signals from logs',
      'Select an existing Gene by signals match',
      'Apply smallest reversible patch',
    ],
    constraints: { max_files: 20, forbidden_paths: ['.git', 'node_modules'] },
    validation: ['node -e "console.log(\'ok\')"'],
    ...overrides,
  };
}

function makeCapsule(overrides: Partial<GepCapsule> = {}): GepCapsule {
  return {
    type: 'Capsule',
    id: 'capsule_1770477654236',
    trigger: ['log_error', 'user_missing'],
    gene: 'gene_gep_repair_from_errors',
    summary: 'Repair capsule for error recovery',
    confidence: 0.85,
    blast_radius: { files: 1, lines: 2 },
    outcome: { status: 'success', score: 0.85 },
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// convertGepGene
// ---------------------------------------------------------------------------

describe('convertGepGene', () => {
  it('maps id to normalized slug', () => {
    const result = convertGepGene(makeGene());
    expect(result.slug).toBe('gep-repair-from-errors');
  });

  it('maps id to humanized name', () => {
    const result = convertGepGene(makeGene());
    expect(result.name).toContain('GEP');
    expect(result.name).toContain('Repair');
  });

  it('maps repair category to operations', () => {
    const result = convertGepGene(makeGene({ category: 'repair' }));
    expect(result.category).toBe('operations');
  });

  it('maps optimize category to efficiency', () => {
    const result = convertGepGene(makeGene({ category: 'optimize' }));
    expect(result.category).toBe('efficiency');
  });

  it('maps innovate category to development', () => {
    const result = convertGepGene(makeGene({ category: 'innovate' }));
    expect(result.category).toBe('development');
  });

  it('defaults unknown category to development', () => {
    const result = convertGepGene(makeGene({ category: 'unknown_cat' }));
    expect(result.category).toBe('development');
  });

  it('sets version to 1.0.0', () => {
    const result = convertGepGene(makeGene());
    expect(result.version).toBe('1.0.0');
  });

  it('builds strategy content from strategy array', () => {
    const gene = makeGene({
      strategy: ['Step one', 'Step two'],
    });
    const result = convertGepGene(gene);
    expect(result.skill.content).toContain('1. Step one');
    expect(result.skill.content).toContain('2. Step two');
  });

  it('includes preconditions in skill content', () => {
    const result = convertGepGene(makeGene());
    expect(result.skill.content).toContain('Preconditions');
    expect(result.skill.content).toContain('signals contains error-related indicators');
  });

  it('includes constraints in skill content', () => {
    const result = convertGepGene(makeGene());
    expect(result.skill.content).toContain('Constraints');
    expect(result.skill.content).toContain('Max files: 20');
    expect(result.skill.content).toContain('.git');
  });

  it('sets author to EvoMap Evolver', () => {
    const result = convertGepGene(makeGene());
    expect(result.author?.type).toBe('agent');
    expect(result.author?.name).toBe('EvoMap Evolver');
  });

  it('includes both openclaw and nanobot compatibility', () => {
    const result = convertGepGene(makeGene());
    const products = result.compatibility.map((c) => c.product);
    expect(products).toContain('openclaw');
    expect(products).toContain('nanobot');
  });

  it('infers tool tag from tool-related signals', () => {
    const gene = makeGene({ signals_match: ['shell', 'command', 'exec'] });
    const result = convertGepGene(gene);
    expect(result.tags).toContain('tool');
  });

  it('infers knowledge tag from knowledge-related signals', () => {
    const gene = makeGene({ signals_match: ['knowledge', 'documentation'] });
    const result = convertGepGene(gene);
    expect(result.tags).toContain('knowledge');
  });

  it('defaults to ability tag', () => {
    const gene = makeGene({ signals_match: ['error', 'exception'] });
    const result = convertGepGene(gene);
    expect(result.tags).toContain('ability');
  });

  it('builds description from gene metadata', () => {
    const result = convertGepGene(makeGene());
    expect(result.description).toContain('repair gene');
    expect(result.description).toContain('error');
  });

  it('handles gene without constraints', () => {
    const gene = makeGene({ constraints: undefined });
    const result = convertGepGene(gene);
    expect(result.skill.content).not.toContain('Constraints');
  });

  it('handles gene without preconditions', () => {
    const gene = makeGene({ preconditions: [] });
    const result = convertGepGene(gene);
    expect(result.skill.content).not.toContain('Preconditions');
  });
});

// ---------------------------------------------------------------------------
// convertGepCapsule
// ---------------------------------------------------------------------------

describe('convertGepCapsule', () => {
  it('maps capsule id to normalized slug', () => {
    const result = convertGepCapsule(makeCapsule());
    expect(result.slug).toBe('1770477654236');
  });

  it('creates a humanized name', () => {
    const result = convertGepCapsule(makeCapsule());
    expect(result.name).toContain('Capsule');
  });

  it('uses capsule summary as description', () => {
    const result = convertGepCapsule(makeCapsule());
    expect(result.description).toBe('Repair capsule for error recovery');
  });

  it('sets category to operations', () => {
    const result = convertGepCapsule(makeCapsule());
    expect(result.category).toBe('operations');
  });

  it('adds parent gene as dependency', () => {
    const result = convertGepCapsule(makeCapsule());
    expect(result.dependencies).toHaveLength(1);
    expect(result.dependencies[0].slug).toBe('gep-repair-from-errors');
  });

  it('handles capsule without gene reference', () => {
    const capsule = makeCapsule({ gene: '' });
    const result = convertGepCapsule(capsule);
    expect(result.dependencies).toHaveLength(0);
  });

  it('includes triggers in skill content', () => {
    const result = convertGepCapsule(makeCapsule());
    expect(result.skill.content).toContain('log_error');
    expect(result.skill.content).toContain('user_missing');
  });

  it('includes confidence in skill content', () => {
    const result = convertGepCapsule(makeCapsule());
    expect(result.skill.content).toContain('Confidence: 0.85');
  });

  it('includes blast radius in skill content', () => {
    const result = convertGepCapsule(makeCapsule());
    expect(result.skill.content).toContain('1 files');
    expect(result.skill.content).toContain('2 lines');
  });

  it('handles capsule with named id', () => {
    const capsule = makeCapsule({ id: 'capsule_repair_workflow' });
    const result = convertGepCapsule(capsule);
    expect(result.slug).toBe('repair-workflow');
    expect(result.name).toContain('Repair');
  });
});

// ---------------------------------------------------------------------------
// convertRecommendation
// ---------------------------------------------------------------------------

describe('convertRecommendation', () => {
  it('dispatches gene type to convertGepGene', () => {
    const item: RecommendationItem = {
      type: 'gene',
      id: 'gene_gep_repair_from_errors',
      score: 0.9,
      reason: 'signals match',
      data: makeGene(),
    };
    const result = convertRecommendation(item);
    expect(result.slug).toBe('gep-repair-from-errors');
    expect(result.author?.name).toBe('EvoMap Evolver');
  });

  it('dispatches capsule type to convertGepCapsule', () => {
    const item: RecommendationItem = {
      type: 'capsule',
      id: 'capsule_1770477654236',
      score: 0.8,
      reason: 'trigger match',
      data: makeCapsule(),
    };
    const result = convertRecommendation(item);
    expect(result.slug).toBe('1770477654236');
    expect(result.dependencies).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// extractEvoMapMetadata
// ---------------------------------------------------------------------------

describe('extractEvoMapMetadata', () => {
  it('returns evomap as source', () => {
    const item: RecommendationItem = {
      type: 'gene',
      id: 'gene_test',
      score: 0.75,
      reason: 'test',
      data: makeGene(),
    };
    const meta = extractEvoMapMetadata(item);
    expect(meta.source).toBe('evomap');
  });

  it('builds source_ref from item id', () => {
    const item: RecommendationItem = {
      type: 'gene',
      id: 'gene_test',
      score: 0.75,
      reason: 'test',
      data: makeGene(),
    };
    const meta = extractEvoMapMetadata(item);
    expect(meta.source_ref).toBe('https://evomap.ai/genes/gene_test');
  });

  it('uses recommendation score as effectiveness_score', () => {
    const item: RecommendationItem = {
      type: 'gene',
      id: 'gene_test',
      score: 0.92,
      reason: 'test',
      data: makeGene(),
    };
    const meta = extractEvoMapMetadata(item);
    expect(meta.effectiveness_score).toBe(0.92);
  });

  it('sets review_status to approved', () => {
    const item: RecommendationItem = {
      type: 'capsule',
      id: 'capsule_test',
      score: 0.5,
      reason: 'test',
      data: makeCapsule(),
    };
    const meta = extractEvoMapMetadata(item);
    expect(meta.review_status).toBe('pending');
    expect(meta.is_published).toBe(false);
  });
});
