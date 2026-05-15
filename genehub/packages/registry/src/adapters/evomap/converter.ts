import type { GeneManifest } from '@nodeskai/genehub-types';
import type { GepCapsule, GepGene, RecommendationItem } from './client.js';

// ---------------------------------------------------------------------------
// GEP category → GeneHub category mapping
// ---------------------------------------------------------------------------

const CATEGORY_MAP: Record<string, GeneManifest['category']> = {
  repair: 'operations',
  optimize: 'efficiency',
  innovate: 'development',
  security: 'security',
  data: 'data',
  network: 'network',
  creative: 'creative',
  communication: 'communication',
};

// ---------------------------------------------------------------------------
// Converter: GEP Gene → GeneManifest
// ---------------------------------------------------------------------------

export function convertGepGene(gene: GepGene): GeneManifest {
  const slug = normalizeGepId(gene.id);
  const name = humanizeGeneId(gene.id);
  const category = CATEGORY_MAP[gene.category] ?? 'development';

  const strategyContent = gene.strategy.map((s, i) => `${i + 1}. ${s}`).join('\n');
  const preconditionContent =
    gene.preconditions.length > 0
      ? `## Preconditions\n\n${gene.preconditions.map((p) => `- ${p}`).join('\n')}\n\n`
      : '';
  const constraintContent = gene.constraints
    ? `## Constraints\n\n- Max files: ${gene.constraints.max_files ?? 'unlimited'}\n- Forbidden paths: ${(gene.constraints.forbidden_paths ?? []).join(', ') || 'none'}\n`
    : '';

  const content = [
    `# ${name}`,
    '',
    preconditionContent,
    '## Strategy',
    '',
    strategyContent,
    '',
    constraintContent,
  ]
    .join('\n')
    .trim();

  return {
    slug,
    name,
    version: '1.0.0',
    description: buildGeneDescription(gene),
    short_description: truncate(buildGeneDescription(gene), 256),
    category,
    tags: inferGeneTags(gene),
    icon: undefined,

    author: {
      type: 'agent',
      name: 'EvoMap Evolver',
      ref: 'https://evomap.ai',
    },

    compatibility: [
      { product: 'openclaw', min_version: '0.0.0' },
      { product: 'nanobot', min_version: '0.0.0' },
    ],

    dependencies: [],
    synergies: [],

    skill: {
      name,
      always: false,
      content,
    },

    rules: [],
    config: undefined,
    mcp_servers: [],
    learning: undefined,
  };
}

// ---------------------------------------------------------------------------
// Converter: GEP Capsule → GeneManifest
// ---------------------------------------------------------------------------

export function convertGepCapsule(capsule: GepCapsule): GeneManifest {
  const slug = normalizeGepId(capsule.id);
  const name = humanizeCapsuleId(capsule.id);

  const triggerList = capsule.trigger.map((t) => `- ${t}`).join('\n');
  const content = [
    `# ${name}`,
    '',
    capsule.summary,
    '',
    '## Triggers',
    '',
    triggerList,
    '',
    `Confidence: ${capsule.confidence}`,
    capsule.blast_radius
      ? `Blast radius: ${capsule.blast_radius.files} files, ${capsule.blast_radius.lines} lines`
      : '',
  ]
    .filter(Boolean)
    .join('\n')
    .trim();

  return {
    slug,
    name,
    version: '1.0.0',
    description: capsule.summary,
    short_description: truncate(capsule.summary, 256),
    category: 'operations',
    tags: ['ability'],
    icon: undefined,

    author: {
      type: 'agent',
      name: 'EvoMap Evolver',
      ref: 'https://evomap.ai',
    },

    compatibility: [
      { product: 'openclaw', min_version: '0.0.0' },
      { product: 'nanobot', min_version: '0.0.0' },
    ],

    dependencies: capsule.gene
      ? [{ slug: normalizeGepId(capsule.gene), version: '*', optional: false }]
      : [],
    synergies: [],

    skill: {
      name,
      always: false,
      content,
    },

    rules: [],
    config: undefined,
    mcp_servers: [],
    learning: undefined,
  };
}

// ---------------------------------------------------------------------------
// Unified converter — dispatches based on recommendation type
// ---------------------------------------------------------------------------

export function convertRecommendation(item: RecommendationItem): GeneManifest {
  if (item.type === 'capsule') {
    return convertGepCapsule(item.data as GepCapsule);
  }
  return convertGepGene(item.data as GepGene);
}

// ---------------------------------------------------------------------------
// Metadata extractor (for DB record fields outside the manifest)
// ---------------------------------------------------------------------------

export function extractEvoMapMetadata(item: RecommendationItem) {
  return {
    source: 'evomap' as const,
    source_ref: `https://evomap.ai/genes/${item.id}`,
    parent_gene_id: null,
    install_count: 0,
    avg_rating: 0,
    effectiveness_score: item.score,
    review_status: 'pending' as const,
    is_published: false,
  };
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function normalizeGepId(raw: string): string {
  return raw
    .replace(/^(gene_|capsule_)/, '')
    .replace(/_/g, '-')
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 64);
}

function humanizeGeneId(id: string): string {
  return id
    .replace(/^gene_/, '')
    .replace(/_/g, ' ')
    .replace(/gep /i, 'GEP ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function humanizeCapsuleId(id: string): string {
  const ts = id.replace(/^capsule_/, '');
  if (/^\d+$/.test(ts)) {
    return `Capsule ${ts}`;
  }
  return ts.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function truncate(s: string, max: number): string {
  return s.length <= max ? s : `${s.slice(0, max - 1)}…`;
}

function buildGeneDescription(gene: GepGene): string {
  const parts = [
    `GEP ${gene.category} gene.`,
    gene.preconditions.length > 0 ? `Preconditions: ${gene.preconditions.join('; ')}.` : '',
    `Matches signals: ${gene.signals_match.join(', ')}.`,
  ];
  return parts.filter(Boolean).join(' ');
}

function inferGeneTags(gene: GepGene): GeneManifest['tags'] {
  const signals = gene.signals_match.join(' ').toLowerCase();
  if (/tool|exec|command|shell/.test(signals)) return ['tool'];
  if (/knowledge|doc|learn/.test(signals)) return ['knowledge'];
  return ['ability'];
}
