import { and, desc, eq, inArray, isNull, sql } from 'drizzle-orm';
import { stringify } from 'yaml';
import { ClawHubClient, type ClawHubSearchResult } from '../adapters/clawhub/client.js';
import { db, schema } from '../db/index.js';
import { emitGeneEvent } from './gene-events.js';
import * as gitea from './gitea-service.js';

const { genes, geneVersions } = schema;

export type FederatedSource = 'local' | 'clawhub';

export type FederatedGeneItem = {
  slug: string;
  name: string;
  description: string | null;
  version: string | null;
  category: string | null;
  tags: string[];
  source: FederatedSource;
  score: number;
  install_count: number | null;
  avg_rating: number | null;
  /** ClawHub display name (when source is clawhub) */
  clawhub_display_name?: string;
};

export type FederatedSearchResult = {
  query: string;
  total: number;
  items: FederatedGeneItem[];
  sources: { local: number; clawhub: number };
};

const clawhubClient = new ClawHubClient({
  baseUrl: process.env.CLAWHUB_BASE_URL,
  token: process.env.CLAWHUB_TOKEN,
  timeoutMs: 8_000,
});

async function searchLocal(
  query: string,
  opts: { category?: string; limit: number },
): Promise<FederatedGeneItem[]> {
  const term = `%${query}%`;

  const conditions = [
    isNull(genes.deleted_at),
    eq(genes.is_published, true),
    sql`(${genes.name} ILIKE ${term} OR ${genes.slug} ILIKE ${term} OR ${genes.short_description} ILIKE ${term})`,
  ];

  if (opts.category) {
    conditions.push(eq(genes.category, opts.category));
  }

  const rows = await db
    .select({
      slug: genes.slug,
      name: genes.name,
      short_description: genes.short_description,
      version: genes.version,
      category: genes.category,
      tags: genes.tags,
      install_count: genes.install_count,
      avg_rating: genes.avg_rating,
    })
    .from(genes)
    .where(and(...conditions))
    .orderBy(desc(genes.install_count))
    .limit(opts.limit);

  return rows.map((row, idx) => ({
    slug: row.slug,
    name: row.name,
    description: row.short_description,
    version: row.version,
    category: row.category,
    tags: (row.tags ?? []) as string[],
    source: 'local' as const,
    score: 1 - idx * 0.02,
    install_count: row.install_count,
    avg_rating: row.avg_rating,
  }));
}

function normalizeClawHubScores(items: ClawHubSearchResult[]): FederatedGeneItem[] {
  if (items.length === 0) return [];
  const maxScore = Math.max(...items.map((i) => i.score), 1);

  return items.map((item) => ({
    slug: item.slug,
    name: item.displayName ?? item.slug,
    description: item.summary,
    version: item.version,
    category: null,
    tags: [],
    source: 'clawhub' as const,
    score: (item.score / maxScore) * 0.85,
    install_count: null,
    avg_rating: null,
    clawhub_display_name: item.displayName,
  }));
}

async function searchClawHub(query: string): Promise<FederatedGeneItem[]> {
  try {
    const response = await clawhubClient.searchSkills(query);
    return normalizeClawHubScores(response.results);
  } catch {
    return [];
  }
}

function deduplicateAndMerge(
  local: FederatedGeneItem[],
  external: FederatedGeneItem[],
): FederatedGeneItem[] {
  const localSlugs = new Set(local.map((g) => g.slug));
  const unique = external.filter((g) => !localSlugs.has(g.slug));
  const merged = [...local, ...unique];
  merged.sort((a, b) => b.score - a.score);
  return merged;
}

export async function federatedSearch(
  query: string,
  opts: { category?: string; limit?: number } = {},
): Promise<FederatedSearchResult> {
  const limit = Math.min(50, Math.max(1, opts.limit ?? 20));

  const [localResults, clawhubResults] = await Promise.all([
    searchLocal(query, { category: opts.category, limit }),
    searchClawHub(query),
  ]);

  const merged = deduplicateAndMerge(localResults, clawhubResults).slice(0, limit);

  const localCount = merged.filter((g) => g.source === 'local').length;
  const clawhubCount = merged.filter((g) => g.source === 'clawhub').length;

  const externalItems = merged.filter((g) => g.source === 'clawhub');
  if (externalItems.length > 0) {
    syncExternalResults(externalItems).catch((err) => {
      console.error('[federated-search] background sync failed:', err);
    });
  }

  return {
    query,
    total: merged.length,
    items: merged,
    sources: { local: localCount, clawhub: clawhubCount },
  };
}

// ---------------------------------------------------------------------------
// Background sync: insert ClawHub results as pending genes for AI review
// ---------------------------------------------------------------------------

async function syncExternalResults(items: FederatedGeneItem[]) {
  const slugs = items.map((i) => i.slug);

  const existing = await db
    .select({ id: genes.id, slug: genes.slug, version: genes.version })
    .from(genes)
    .where(inArray(genes.slug, slugs));

  const existingMap = new Map(existing.map((r) => [r.slug, r]));

  for (const item of items) {
    try {
      const current = existingMap.get(item.slug);
      const itemVersion = item.version ?? '0.0.0';

      if (!current) {
        await insertNewGene(item);
      } else if (current.version !== itemVersion) {
        await updateExistingGene(current.id, item);
      }
    } catch (err) {
      console.error(`[federated-search] Failed to sync ${item.slug}:`, err);
    }
  }
}

async function insertNewGene(item: FederatedGeneItem) {
  const version = item.version ?? '0.0.0';
  const manifest = buildMinimalManifest(item);

  let skillContent: string | null = null;
  try {
    skillContent = await clawhubClient.downloadFile(item.slug, version);
    manifest.skill.content = skillContent;
  } catch (err) {
    console.warn(`[federated-search] download ${item.slug}@${version} from ClawHub failed:`, err);
  }

  const giteaFiles = buildGiteaFiles(manifest, skillContent);
  const giteaMeta = await uploadToGitea(item.slug, version, giteaFiles, item.description ?? '');

  const [gene] = await db
    .insert(genes)
    .values({
      name: item.name,
      slug: item.slug,
      version,
      description: item.description ?? '',
      short_description: (item.description ?? '').slice(0, 256),
      category: item.category ?? 'development',
      tags: item.tags.length > 0 ? item.tags : ['ability'],
      manifest,
      compatibility: [],
      dependencies: [],
      synergies: [],
      author: { type: 'human', name: item.clawhub_display_name ?? item.name },
      source: 'clawhub',
      source_ref: `https://clawhub.ai/skills/${item.slug}`,
      install_count: item.install_count ?? 0,
      avg_rating: item.avg_rating ?? 0,
      review_status: 'pending',
      is_published: false,
      repository_url: giteaMeta.repositoryUrl,
      file_count: giteaMeta.fileCount,
    })
    .onConflictDoNothing({ target: genes.slug })
    .returning();

  if (gene) {
    await db.insert(geneVersions).values({
      gene_id: gene.id,
      version: gene.version,
      manifest,
      commit_sha: giteaMeta.commitSha,
      git_tag: giteaMeta.gitTag,
      files: giteaMeta.fileList,
      changelog: 'Auto-imported from ClawHub federated search',
      is_latest: true,
    });
    await emitGeneEvent('gene.created', item.slug, 'clawhub');
  }
}

async function updateExistingGene(geneId: string, item: FederatedGeneItem) {
  const version = item.version ?? '0.0.0';
  const manifest = buildMinimalManifest(item);

  let skillContent: string | null = null;
  try {
    skillContent = await clawhubClient.downloadFile(item.slug, version);
    manifest.skill.content = skillContent;
  } catch (err) {
    console.warn(`[federated-search] download ${item.slug}@${version} from ClawHub failed:`, err);
  }

  const giteaFiles = buildGiteaFiles(manifest, skillContent);
  const giteaMeta = await uploadToGitea(item.slug, version, giteaFiles, item.description ?? '');

  await db.update(geneVersions).set({ is_latest: false }).where(eq(geneVersions.gene_id, geneId));

  await db.insert(geneVersions).values({
    gene_id: geneId,
    version,
    manifest,
    commit_sha: giteaMeta.commitSha,
    git_tag: giteaMeta.gitTag,
    files: giteaMeta.fileList,
    changelog: `Version ${version} updated from ClawHub`,
    is_latest: true,
  });

  const geneUpdates: Record<string, unknown> = {
    version,
    name: item.name,
    description: item.description ?? '',
    short_description: (item.description ?? '').slice(0, 256),
    manifest,
    install_count: item.install_count ?? 0,
    avg_rating: item.avg_rating ?? 0,
    review_status: 'pending',
    is_published: false,
    updated_at: new Date(),
  };
  if (giteaMeta.repositoryUrl) {
    geneUpdates.repository_url = giteaMeta.repositoryUrl;
    geneUpdates.file_count = giteaMeta.fileCount;
  }

  await db.update(genes).set(geneUpdates).where(eq(genes.id, geneId));

  await emitGeneEvent('gene.updated', item.slug, 'clawhub');
}

// ---------------------------------------------------------------------------
// Gitea integration helpers
// ---------------------------------------------------------------------------

type GiteaUploadMeta = {
  repositoryUrl: string | null;
  commitSha: string | null;
  gitTag: string | null;
  fileList: { path: string; size: number; sha: string }[] | null;
  fileCount: number;
};

const EMPTY_GITEA_META: GiteaUploadMeta = {
  repositoryUrl: null,
  commitSha: null,
  gitTag: null,
  fileList: null,
  fileCount: 0,
};

function buildGiteaFiles(
  manifest: ReturnType<typeof buildMinimalManifest>,
  skillContent: string | null,
): Record<string, string> {
  const files: Record<string, string> = {};

  const yamlManifest = { ...manifest } as Record<string, unknown>;
  if (yamlManifest.skill && typeof yamlManifest.skill === 'object') {
    const s = { ...(yamlManifest.skill as Record<string, unknown>) };
    delete s.content;
    yamlManifest.skill = s;
  }
  files['gene.yaml'] = stringify(yamlManifest);

  if (skillContent) {
    files['SKILL.md'] = skillContent;
  }

  return files;
}

async function uploadToGitea(
  slug: string,
  version: string,
  files: Record<string, string>,
  description: string,
): Promise<GiteaUploadMeta> {
  const isGiteaReady = await gitea.isGiteaAvailable();
  if (!isGiteaReady) {
    console.warn(`[federated-search] Gitea unavailable, skipping file upload for ${slug}`);
    return EMPTY_GITEA_META;
  }

  try {
    const hasRepo = await gitea.repoExists(slug);
    if (!hasRepo) {
      await gitea.createRepo(slug, description.slice(0, 256));
    }

    const tag = `v${version}`;
    const result = await gitea.uploadFiles(slug, files, `feat: import ${tag} from ClawHub`);

    try {
      await gitea.createTag(slug, tag, result.sha);
    } catch {
      // tag may already exist for this version
    }

    const fileList = Object.entries(files).map(([path, content]) => ({
      path,
      size: Buffer.byteLength(content, 'utf-8'),
      sha: '',
    }));

    return {
      repositoryUrl: gitea.getRepoUrl(slug),
      commitSha: result.sha,
      gitTag: tag,
      fileList,
      fileCount: fileList.length,
    };
  } catch (err) {
    console.error(`[federated-search] Gitea upload failed for ${slug}:`, err);
    return EMPTY_GITEA_META;
  }
}

function buildMinimalManifest(item: FederatedGeneItem) {
  return {
    slug: item.slug,
    name: item.name,
    version: item.version ?? '0.0.0',
    description: item.description ?? '',
    short_description: (item.description ?? '').slice(0, 256),
    category: item.category ?? 'development',
    tags: item.tags.length > 0 ? item.tags : ['ability'],
    compatibility: [],
    dependencies: [],
    synergies: [],
    skill: {
      name: item.name,
      always: false,
      content: item.description ?? '',
    },
    rules: [],
    mcp_servers: [],
  };
}
