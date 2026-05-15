import type { GeneManifest } from '@nodeskai/genehub-types';
import type { ClawHubSkillDetail, ClawHubSkillVersion, SecurityStatus } from './client.js';

/**
 * Combined payload that the converter expects — assembled by the sync layer
 * from multiple ClawHub API calls.
 */
export type ClawHubSkillPayload = {
  detail: ClawHubSkillDetail;
  version: ClawHubSkillVersion | null;
  /** Raw text content of instructions.md / SKILL.md (may be empty) */
  instructionsContent: string;
};

// ---------------------------------------------------------------------------
// Security filter
// ---------------------------------------------------------------------------

const BLOCKED_STATUSES = new Set<SecurityStatus['status']>(['malicious', 'suspicious']);

export function isSkillSafe(version: ClawHubSkillVersion | null): boolean {
  if (!version?.version) return false;
  const sec = version.version.security;
  if (!sec) return true;
  return !BLOCKED_STATUSES.has(sec.status);
}

// ---------------------------------------------------------------------------
// Converter
// ---------------------------------------------------------------------------

/**
 * Convert a ClawHub skill (detail + version + instructions content) into a
 * GeneHub GeneManifest.
 *
 * This is the isolation boundary between ClawHub's data model and GeneHub's.
 * The mapping is intentionally kept thin — most fields are direct copies or
 * sensible defaults — so that future divergence stays contained here.
 */
export function convertClawHubSkill(payload: ClawHubSkillPayload): GeneManifest {
  const { detail, version, instructionsContent } = payload;
  const skill = detail.skill;
  if (!skill) throw new Error('convertClawHubSkill called with null skill');
  const owner = detail.owner;
  const ver = version?.version ?? detail.latestVersion;
  const meta = parseSkillMetadata(skill.tags);

  const slug = normalizeSlug(skill.slug);

  return {
    slug,
    name: skill.displayName || slug,
    version: ver?.version ?? '1.0.0',
    description: skill.summary ?? '',
    short_description: truncate(skill.summary ?? '', 256),
    category: inferCategory(meta),
    tags: inferTags(meta),
    icon: meta.emoji ?? undefined,

    author: {
      type: 'human',
      name: owner?.displayName ?? owner?.handle ?? '',
      ref: owner?.handle ?? '',
    },

    compatibility: [{ product: 'openclaw', min_version: '0.0.0' }],

    dependencies: convertDependencies(meta),
    synergies: [],

    skill: {
      name: skill.displayName || slug,
      always: meta.always ?? false,
      content: instructionsContent || '',
    },

    rules: [],

    config: buildConfig(meta),

    mcp_servers: [],

    learning: undefined,
  };
}

/**
 * Metadata that lives outside the manifest — stored on the GeneHub gene
 * record separately.
 */
export function extractClawHubMetadata(payload: ClawHubSkillPayload) {
  const skill = payload.detail.skill;
  if (!skill) throw new Error('extractClawHubMetadata called with null skill');
  const stats = (skill.stats ?? {}) as Record<string, unknown>;

  return {
    source: 'clawhub' as const,
    source_ref: `https://clawhub.ai/skills/${skill.slug}`,
    parent_gene_id: null,
    install_count: typeof stats.installs === 'number' ? stats.installs : 0,
    avg_rating: typeof stats.stars === 'number' ? stats.stars : 0,
    effectiveness_score: 0,
    review_status: 'pending' as const,
    is_published: false,
  };
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

type SkillMeta = {
  always?: boolean;
  emoji?: string;
  homepage?: string;
  os?: string[];
  requires?: { bins?: string[]; anyBins?: string[]; env?: string[]; config?: string[] };
  install?: Array<{ id?: string; kind: string; formula?: string; bins?: string[]; label?: string }>;
  dependencies?: Array<{
    name: string;
    type: string;
    version?: string;
    url?: string;
    repository?: string;
  }>;
  envVars?: Array<{ name: string; required?: boolean; description?: string }>;
  author?: string;
  links?: { homepage?: string; repository?: string; documentation?: string };
  [key: string]: unknown;
};

/**
 * ClawHub stores skill metadata in the `tags` field as an opaque `unknown`.
 * In practice it's either a plain array of string tags or a
 * ClawdisSkillMetadata object. We normalise both cases.
 */
function parseSkillMetadata(tags: unknown): SkillMeta {
  if (!tags || typeof tags !== 'object') return {};
  if (Array.isArray(tags)) return {};
  return tags as SkillMeta;
}

function normalizeSlug(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 64);
}

function truncate(s: string, max: number): string {
  return s.length <= max ? s : `${s.slice(0, max - 1)}…`;
}

function inferCategory(meta: SkillMeta): GeneManifest['category'] {
  if (meta.homepage && /secur/i.test(meta.homepage)) return 'security';
  return 'development';
}

function inferTags(meta: SkillMeta): GeneManifest['tags'] {
  if (meta.install && meta.install.length > 0) return ['tool'];
  if (meta.requires?.bins?.length || meta.requires?.anyBins?.length) return ['tool'];
  return ['ability'];
}

function convertDependencies(
  meta: SkillMeta,
): Array<{ slug: string; version: string; optional?: boolean }> {
  if (!meta.dependencies?.length) return [];
  return meta.dependencies
    .filter((d) => d.name)
    .map((d) => ({
      slug: normalizeSlug(d.name),
      version: d.version ?? '*',
      optional: false,
    }));
}

function buildConfig(meta: SkillMeta): GeneManifest['config'] | undefined {
  const requires = meta.requires;
  if (!requires) return undefined;

  return {
    openclaw: {
      openclaw_config: {
        ...(requires.bins?.length ? { requires_bins: requires.bins } : {}),
        ...(requires.env?.length ? { requires_env: requires.env } : {}),
      },
    },
  };
}
