import type { GeneManifest } from '@nodeskai/genehub-types';

/**
 * Raw gene row shape coming from NoDeskClaw's PostgreSQL `genes` table.
 * Fields use Text columns for JSON (not JSONB), so everything arrives
 * as strings that need `JSON.parse`.
 */
export type NoDeskClawGeneRow = {
  id: string;
  name: string;
  slug: string;
  version: string;
  description: string | null;
  short_description: string | null;
  category: string | null;
  tags: string | null;
  icon: string | null;
  source: string;
  source_ref: string | null;
  manifest: string | null;
  dependencies: string | null;
  synergies: string | null;
  parent_gene_id: string | null;
  install_count: number;
  avg_rating: number;
  effectiveness_score: number;
  review_status: string | null;
  is_published: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};

function safeJsonParse<T>(raw: string | null | undefined, fallback: T): T {
  if (!raw) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

/**
 * Convert a NoDeskClaw gene row into a GeneHub GeneManifest.
 *
 * The two schemas were designed together, so the mapping is mostly a direct
 * copy.  This converter exists as an isolation boundary so that future
 * divergence between NoDeskClaw and GeneHub models stays contained here.
 */
export function convertNoDeskClawGene(row: NoDeskClawGeneRow): GeneManifest {
  const manifest = safeJsonParse<Record<string, unknown>>(row.manifest, {});

  const skill = (manifest.skill as Record<string, unknown>) ?? {};
  const learning = manifest.learning as Record<string, unknown> | undefined;
  const openclawConfig = manifest.openclaw_config as Record<string, unknown> | undefined;
  const toolAllow = manifest.tool_allow as string[] | undefined;
  const mcpServers = (manifest.mcp_servers ?? []) as Array<Record<string, unknown>>;

  const tags = safeJsonParse<string[]>(row.tags, []);
  const validTags = tags.filter((t) => ['ability', 'personality', 'knowledge', 'tool'].includes(t));

  const deps = safeJsonParse<Array<{ slug: string; version: string }>>(row.dependencies, []);
  const syns = safeJsonParse<string[]>(row.synergies, []);

  return {
    slug: row.slug,
    name: row.name,
    version: row.version || '1.0.0',
    description: row.description ?? '',
    short_description: row.short_description ?? '',
    category: normalizeCategory(row.category),
    tags: validTags.length > 0 ? (validTags as GeneManifest['tags']) : ['ability'],
    icon: row.icon ?? undefined,

    author: {
      type: 'human',
      name: '',
      ref: row.created_by ?? '',
    },

    compatibility: [{ product: 'openclaw', min_version: '0.0.0' }],

    dependencies: deps,
    synergies: syns,

    skill: {
      name: (skill.name as string) ?? row.slug,
      always: (skill.always as boolean) ?? false,
      content: (skill.content as string) ?? '',
    },

    config:
      openclawConfig || toolAllow
        ? { openclaw: { openclaw_config: openclawConfig, tool_allow: toolAllow } }
        : undefined,

    mcp_servers: mcpServers.map((s) => ({
      name: (s.name as string) ?? '',
      transport: ((s.transport as string) ?? 'stdio') as 'stdio' | 'http',
      command: s.command as string | undefined,
      args: (s.args as string[]) ?? [],
      env: (s.env as Record<string, string>) ?? {},
      url: s.url as string | undefined,
      headers: s.headers as Record<string, string> | undefined,
    })),

    learning: learning
      ? {
          force_deep_learn: (learning.force_deep_learn as boolean) ?? false,
          objectives: (learning.objectives as string[]) ?? [],
          scenarios:
            (learning.scenarios as GeneManifest['learning'] extends { scenarios: infer S }
              ? S
              : never) ?? [],
        }
      : undefined,
  };
}

const VALID_CATEGORIES = new Set([
  'development',
  'data',
  'operations',
  'network',
  'creative',
  'communication',
  'security',
  'efficiency',
]);

function normalizeCategory(raw: string | null | undefined): GeneManifest['category'] {
  if (raw && VALID_CATEGORIES.has(raw)) return raw as GeneManifest['category'];
  return 'development';
}

/**
 * Metadata that lives outside the manifest and needs to be carried through
 * to the GeneHub gene record separately (not part of GeneManifest).
 */
export function extractGeneMetadata(row: NoDeskClawGeneRow) {
  return {
    source: row.source || 'official',
    source_ref: row.source_ref ?? null,
    parent_gene_id: row.parent_gene_id ?? null,
    install_count: row.install_count ?? 0,
    avg_rating: row.avg_rating ?? 0,
    effectiveness_score: row.effectiveness_score ?? 0,
    review_status: row.review_status ?? 'approved',
    is_published: row.is_published ?? true,
  };
}
