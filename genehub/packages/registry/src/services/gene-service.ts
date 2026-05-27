import { GeneManifestSchema } from '@nodeskai/genehub-types';
import { and, desc, eq, inArray, isNull, sql } from 'drizzle-orm';
import semver from 'semver';
import { db, schema } from '../db/index.js';
import { AppError } from '../middleware/error-handler.js';
import { emitGeneEvent } from './gene-events.js';
import * as gitea from './gitea-service.js';

const { genes, geneVersions } = schema;

export type GeneListQuery = {
  q?: string;
  category?: string;
  tags?: string;
  compatibility?: string;
  sort?: string;
  page?: number;
  page_size?: number;
  review_status?: string;
  include_unpublished?: boolean;
};

export async function listGenes(query: GeneListQuery) {
  const page = Math.max(1, query.page ?? 1);
  const pageSize = Math.min(100, Math.max(1, query.page_size ?? 20));
  const offset = (page - 1) * pageSize;

  const conditions = [isNull(genes.deleted_at)];
  if (!query.include_unpublished) {
    conditions.push(eq(genes.is_published, true));
  }
  if (query.review_status) {
    conditions.push(eq(genes.review_status, query.review_status));
  }

  if (query.category) {
    conditions.push(eq(genes.category, query.category));
  }

  if (query.compatibility) {
    conditions.push(sql`${genes.compatibility} @> ${JSON.stringify([query.compatibility])}`);
  }

  if (query.tags) {
    const tagList = query.tags.split(',');
    conditions.push(
      sql`${genes.tags} ?| array[${sql.join(
        tagList.map((t) => sql`${t}`),
        sql`, `,
      )}]`,
    );
  }

  if (query.q) {
    const searchTerm = `%${query.q}%`;
    conditions.push(
      sql`(${genes.name} ILIKE ${searchTerm} OR ${genes.slug} ILIKE ${searchTerm} OR ${genes.short_description} ILIKE ${searchTerm})`,
    );
  }

  const where = and(...conditions);

  let orderBy: ReturnType<typeof desc> = desc(genes.created_at);
  switch (query.sort) {
    case 'popular':
      orderBy = desc(genes.install_count);
      break;
    case 'rating':
      orderBy = desc(genes.avg_rating);
      break;
    default:
  }

  const [items, countResult] = await Promise.all([
    db.select().from(genes).where(where).orderBy(orderBy).limit(pageSize).offset(offset),
    db.select({ count: sql<number>`count(*)` }).from(genes).where(where),
  ]);

  const total = Number(countResult[0]?.count ?? 0);

  return { items, total, page, pageSize };
}

export async function getGeneTags() {
  const result = await db
    .select({ tags: genes.tags })
    .from(genes)
    .where(and(isNull(genes.deleted_at), eq(genes.is_published, true)));

  const counts = new Map<string, number>();
  for (const row of result) {
    const tagList = row.tags ?? [];
    for (const tag of tagList) {
      counts.set(tag, (counts.get(tag) ?? 0) + 1);
    }
  }

  return Array.from(counts.entries())
    .map(([tag, count]) => ({ tag, count }))
    .sort((a, b) => b.count - a.count);
}

export async function getFeaturedGenes(limit = 10) {
  return db
    .select()
    .from(genes)
    .where(and(isNull(genes.deleted_at), eq(genes.is_published, true)))
    .orderBy(desc(genes.install_count), desc(genes.avg_rating))
    .limit(Math.min(limit, 50));
}

export async function getGeneSynergies(slug: string) {
  const gene = await getGeneBySlug(slug);
  const synergySlugs = (gene.synergies ?? []) as string[];
  if (synergySlugs.length === 0) return [];

  return db
    .select()
    .from(genes)
    .where(
      and(
        inArray(genes.slug, synergySlugs),
        isNull(genes.deleted_at),
        eq(genes.is_published, true),
      ),
    );
}

export async function getGeneBySlug(slug: string) {
  const result = await db
    .select()
    .from(genes)
    .where(and(eq(genes.slug, slug), isNull(genes.deleted_at)));

  if (result.length === 0) {
    throw AppError.geneNotFound(slug);
  }

  return result[0];
}

export async function getGeneManifest(slug: string, version?: string) {
  const gene = await getGeneBySlug(slug);

  if (!version) {
    return gene.manifest;
  }

  const ver = await db
    .select()
    .from(geneVersions)
    .where(and(eq(geneVersions.gene_id, gene.id), eq(geneVersions.version, version)));

  if (ver.length === 0) {
    throw AppError.versionNotFound(slug, version);
  }

  return ver[0].manifest;
}

export async function getGeneVersions(slug: string) {
  const gene = await getGeneBySlug(slug);

  return db
    .select()
    .from(geneVersions)
    .where(eq(geneVersions.gene_id, gene.id))
    .orderBy(desc(geneVersions.published_at));
}

export async function getGeneVersion(slug: string, version: string) {
  const gene = await getGeneBySlug(slug);

  const result = await db
    .select()
    .from(geneVersions)
    .where(and(eq(geneVersions.gene_id, gene.id), eq(geneVersions.version, version)));

  if (result.length === 0) {
    throw AppError.versionNotFound(slug, version);
  }

  return result[0];
}

export type PublisherContext = {
  publisherId?: string;
  githubLogin?: string;
  isAdmin?: boolean;
};

export async function createGene(
  manifestRaw: unknown,
  publisherCtx?: PublisherContext,
  files?: Record<string, string>,
) {
  const parsed = GeneManifestSchema.safeParse(manifestRaw);
  if (!parsed.success) {
    const detail = parsed.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`).join('; ');
    throw AppError.manifestInvalid(detail);
  }

  const manifest = parsed.data;

  if (!semver.valid(manifest.version)) {
    throw AppError.manifestInvalid(`无效的版本号: ${manifest.version}`);
  }

  const existing = await db
    .select({ id: genes.id })
    .from(genes)
    .where(and(eq(genes.slug, manifest.slug), isNull(genes.deleted_at)));
  if (existing.length > 0) {
    throw AppError.slugExists(manifest.slug);
  }

  const compatibility = manifest.compatibility.map((c) => c.product);

  const isGithubPublisher = publisherCtx?.publisherId && publisherCtx.githubLogin;
  const source = isGithubPublisher ? 'github' : 'official';
  const sourceRef = isGithubPublisher ? publisherCtx.githubLogin : null;
  const author = isGithubPublisher
    ? { type: 'human' as const, name: publisherCtx.githubLogin ?? '' }
    : (manifest.author ?? { type: 'human' as const, name: '' });

  let repositoryUrl: string | null = null;
  let commitSha: string | null = null;
  let gitTag: string | null = null;
  let fileList: { path: string; size: number; sha: string }[] | null = null;
  let fileCount = 0;

  if (files && Object.keys(files).length > 0) {
    const isGiteaReady = await gitea.isGiteaAvailable();
    if (!isGiteaReady) throw AppError.giteaUnavailable();

    try {
      const hasRepo = await gitea.repoExists(manifest.slug);
      if (!hasRepo) {
        await gitea.createRepo(manifest.slug, manifest.short_description || manifest.description);
      }
      const tag = `v${manifest.version}`;
      const result = await gitea.uploadFiles(manifest.slug, files, `feat: ${tag} initial publish`);
      await gitea.createTag(manifest.slug, tag, result.sha);
      repositoryUrl = gitea.getRepoUrl(manifest.slug);
      commitSha = result.sha;
      gitTag = tag;
      fileList = Object.entries(files).map(([path, content]) => ({
        path,
        size: Buffer.byteLength(content, 'utf-8'),
        sha: '',
      }));
      fileCount = fileList.length;
    } catch (err) {
      throw AppError.giteaRepoError(err instanceof Error ? err.message : String(err));
    }
  }

  const [gene] = await db
    .insert(genes)
    .values({
      name: manifest.name,
      slug: manifest.slug,
      version: manifest.version,
      description: manifest.description,
      short_description: manifest.short_description,
      category: manifest.category,
      tags: manifest.tags,
      icon: manifest.icon ?? null,
      source,
      source_ref: sourceRef,
      repository_url: repositoryUrl,
      file_count: fileCount,
      publisher_id: publisherCtx?.publisherId ?? null,
      manifest,
      compatibility,
      dependencies: manifest.dependencies,
      synergies: manifest.synergies,
      author,
      review_status: 'pending',
      is_published: false,
    })
    .returning();

  await db.insert(geneVersions).values({
    gene_id: gene.id,
    version: manifest.version,
    manifest,
    commit_sha: commitSha,
    git_tag: gitTag,
    files: fileList,
    changelog: '初始版本',
    is_latest: true,
  });

  await emitGeneEvent('gene.created', manifest.slug, gene.source);

  return gene;
}

export async function publishVersion(
  slug: string,
  manifestRaw: unknown,
  changelog?: string,
  files?: Record<string, string>,
) {
  const parsed = GeneManifestSchema.safeParse(manifestRaw);
  if (!parsed.success) {
    const detail = parsed.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`).join('; ');
    throw AppError.manifestInvalid(detail);
  }

  const manifest = parsed.data;

  if (!semver.valid(manifest.version)) {
    throw AppError.manifestInvalid(`无效的版本号: ${manifest.version}`);
  }

  const gene = await getGeneBySlug(slug);

  if (manifest.slug !== slug) {
    throw AppError.manifestInvalid(`manifest.slug (${manifest.slug}) 与 URL slug (${slug}) 不匹配`);
  }

  const existingVersion = await db
    .select()
    .from(geneVersions)
    .where(and(eq(geneVersions.gene_id, gene.id), eq(geneVersions.version, manifest.version)));

  if (existingVersion.length > 0) {
    throw AppError.versionConflict(slug, manifest.version);
  }

  if (!semver.gt(manifest.version, gene.version)) {
    throw AppError.manifestInvalid(`新版本 ${manifest.version} 必须大于当前版本 ${gene.version}`);
  }

  let commitSha: string | null = null;
  let gitTag: string | null = null;
  let fileList: { path: string; size: number; sha: string }[] | null = null;
  let fileCount = gene.file_count;

  if (files && Object.keys(files).length > 0) {
    const isGiteaReady = await gitea.isGiteaAvailable();
    if (!isGiteaReady) throw AppError.giteaUnavailable();

    try {
      const hasRepo = await gitea.repoExists(slug);
      if (!hasRepo) {
        await gitea.createRepo(slug, manifest.short_description || manifest.description);
      }
      const tag = `v${manifest.version}`;
      const result = await gitea.uploadFiles(slug, files, `feat: ${tag}`);
      await gitea.createTag(slug, tag, result.sha);
      commitSha = result.sha;
      gitTag = tag;
      fileList = Object.entries(files).map(([path, content]) => ({
        path,
        size: Buffer.byteLength(content, 'utf-8'),
        sha: '',
      }));
      fileCount = fileList.length;
    } catch (err) {
      throw AppError.giteaRepoError(err instanceof Error ? err.message : String(err));
    }
  }

  await db
    .update(geneVersions)
    .set({ is_latest: false })
    .where(and(eq(geneVersions.gene_id, gene.id), eq(geneVersions.is_latest, true)));

  await db.insert(geneVersions).values({
    gene_id: gene.id,
    version: manifest.version,
    manifest,
    commit_sha: commitSha,
    git_tag: gitTag,
    files: fileList,
    changelog: changelog ?? '',
    is_latest: true,
  });

  const compatibility = manifest.compatibility.map((c) => c.product);

  const updateValues: Record<string, unknown> = {
    version: manifest.version,
    name: manifest.name,
    description: manifest.description,
    short_description: manifest.short_description,
    category: manifest.category,
    tags: manifest.tags,
    icon: manifest.icon ?? null,
    manifest,
    compatibility,
    dependencies: manifest.dependencies,
    synergies: manifest.synergies,
    file_count: fileCount,
    updated_at: new Date(),
  };
  if (!gene.repository_url && commitSha) {
    updateValues.repository_url = gitea.getRepoUrl(slug);
  }

  const [updated] = await db
    .update(genes)
    .set(updateValues)
    .where(eq(genes.id, gene.id))
    .returning();

  await emitGeneEvent('gene.updated', slug, updated.source, {
    version: manifest.version,
  });

  return updated;
}

export async function updateGene(slug: string, updates: Record<string, unknown>) {
  const gene = await getGeneBySlug(slug);

  const allowedFields: Record<string, string> = {
    review_status: 'review_status',
    is_published: 'is_published',
    source: 'source',
    source_ref: 'source_ref',
  };

  const setValues: Record<string, unknown> = { updated_at: new Date() };
  for (const [key, col] of Object.entries(allowedFields)) {
    if (key in updates) {
      setValues[col] = updates[key];
    }
  }

  const [updated] = await db.update(genes).set(setValues).where(eq(genes.id, gene.id)).returning();

  await emitGeneEvent('gene.updated', slug, updated.source, {
    changed_fields: Object.keys(setValues).filter((k) => k !== 'updated_at'),
  });

  return updated;
}

export async function deleteGene(slug: string) {
  const gene = await getGeneBySlug(slug);

  if (gene.repository_url) {
    try {
      await gitea.deleteRepo(slug);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes('404')) {
        // 仓库已被删或不存在，继续删 DB
      } else {
        throw err;
      }
    }
  }
  const [deleted] = await db.delete(genes).where(eq(genes.id, gene.id)).returning();
  return deleted;
}

export async function incrementInstallCount(slug: string) {
  const gene = await getGeneBySlug(slug);

  await db
    .update(genes)
    .set({ install_count: sql`${genes.install_count} + 1`, updated_at: new Date() })
    .where(eq(genes.id, gene.id));
}

export async function getGeneFiles(slug: string, version?: string) {
  const gene = await getGeneBySlug(slug);
  if (!gene.repository_url) {
    const manifest = gene.manifest as Record<string, unknown>;
    const skillContent = (manifest as { skill?: { content?: string } }).skill?.content;
    const fakeFiles = [{ path: 'gene.yaml', size: 0, sha: '', type: 'file' as const }];
    if (skillContent) {
      fakeFiles.push({ path: 'SKILL.md', size: skillContent.length, sha: '', type: 'file' });
    }
    return fakeFiles;
  }

  let ref = 'main';
  if (version) {
    const ver = await db
      .select()
      .from(geneVersions)
      .where(and(eq(geneVersions.gene_id, gene.id), eq(geneVersions.version, version)));
    if (ver.length > 0 && ver[0].git_tag) {
      ref = ver[0].git_tag;
    }
  }

  return gitea.getFileTree(slug, ref);
}

export async function getGeneFileContent(slug: string, filePath: string, version?: string) {
  const gene = await getGeneBySlug(slug);
  if (!gene.repository_url) {
    if (filePath === 'SKILL.md') {
      const manifest = gene.manifest as { skill?: { content?: string } };
      return manifest.skill?.content ?? '';
    }
    throw AppError.geneNotFound(`${slug}/${filePath}`);
  }

  let ref = 'main';
  if (version) {
    const ver = await db
      .select()
      .from(geneVersions)
      .where(and(eq(geneVersions.gene_id, gene.id), eq(geneVersions.version, version)));
    if (ver.length > 0 && ver[0].git_tag) {
      ref = ver[0].git_tag;
    }
  }

  return gitea.getFileContent(slug, filePath, ref);
}

export async function getGeneArchiveStream(slug: string, version?: string) {
  const gene = await getGeneBySlug(slug);
  if (!gene.repository_url) {
    throw AppError.giteaRepoError(`基因 ${slug} 无文件仓库，请使用 manifest API`);
  }

  let ref = 'main';
  if (version) {
    const ver = await db
      .select()
      .from(geneVersions)
      .where(and(eq(geneVersions.gene_id, gene.id), eq(geneVersions.version, version)));
    if (ver.length > 0 && ver[0].git_tag) {
      ref = ver[0].git_tag;
    }
  }

  return gitea.getArchiveStream(slug, ref);
}

export async function reportEffectiveness(
  slug: string,
  report: { metric_type: string; value: number },
) {
  const gene = await getGeneBySlug(slug);

  const currentScore = gene.effectiveness_score ?? 0;
  const currentRating = gene.avg_rating ?? 0;

  // effectiveness_score: EMA (exponential moving average), alpha = 0.3
  const alpha = 0.3;
  const newEffectiveness =
    currentScore === 0 ? report.value : currentScore * (1 - alpha) + report.value * alpha;

  // avg_rating: only updated by positive signals (user_positive / task_success)
  const isPositive =
    report.metric_type === 'user_positive' || report.metric_type === 'task_success';
  const newRating = isPositive ? Math.max(currentRating, newEffectiveness) : currentRating;

  await db
    .update(genes)
    .set({
      effectiveness_score: Math.round(newEffectiveness * 100) / 100,
      avg_rating: Math.round(newRating * 100) / 100,
      updated_at: new Date(),
    })
    .where(eq(genes.id, gene.id));
}
