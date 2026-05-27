import { and, desc, eq, inArray, isNull, sql } from 'drizzle-orm';
import semver from 'semver';
import { db, schema } from '../db/index.js';
import { AppError } from '../middleware/error-handler.js';
import { emitTemplateEvent } from './gene-events.js';
import * as gitea from './gitea-service.js';

const { agentTemplates, agentTemplateVersions, genomes, genes } = schema;
const GITEA_ORG = gitea.GITEA_TEMPLATES_ORG;

export type TemplateListQuery = {
  q?: string;
  category?: string;
  role?: string;
  sort?: string;
  page?: number;
  page_size?: number;
  include_unpublished?: boolean;
};

type TemplateRef = {
  slug: string;
  version: string;
};

export type CreateTemplateInput = {
  name: string;
  slug: string;
  version: string;
  description?: string;
  short_description?: string;
  role?: string;
  category?: string;
  tags?: string[];
  icon?: string;
  avatar_url?: string;
  genomes: TemplateRef[];
  genes?: TemplateRef[];
  compatibility?: string[];
  author?: { type: string; id?: string; name: string };
  files?: Record<string, string>;
};

export async function listTemplates(query: TemplateListQuery) {
  const page = Math.max(1, query.page ?? 1);
  const pageSize = Math.min(100, Math.max(1, query.page_size ?? 20));
  const offset = (page - 1) * pageSize;

  const conditions = [isNull(agentTemplates.deleted_at)];
  if (!query.include_unpublished) {
    conditions.push(eq(agentTemplates.is_published, true));
  }

  if (query.category) {
    conditions.push(eq(agentTemplates.category, query.category));
  }

  if (query.role) {
    conditions.push(eq(agentTemplates.role, query.role));
  }

  if (query.q) {
    const term = `%${query.q}%`;
    conditions.push(
      sql`(${agentTemplates.name} ILIKE ${term} OR ${agentTemplates.slug} ILIKE ${term} OR ${agentTemplates.short_description} ILIKE ${term} OR ${agentTemplates.role} ILIKE ${term})`,
    );
  }

  const where = and(...conditions);

  let orderBy: ReturnType<typeof desc> = desc(agentTemplates.created_at);
  switch (query.sort) {
    case 'popular':
      orderBy = desc(agentTemplates.install_count);
      break;
    case 'rating':
      orderBy = desc(agentTemplates.avg_rating);
      break;
    default:
  }

  const [items, countResult] = await Promise.all([
    db.select().from(agentTemplates).where(where).orderBy(orderBy).limit(pageSize).offset(offset),
    db.select({ count: sql<number>`count(*)` }).from(agentTemplates).where(where),
  ]);

  return { items, total: Number(countResult[0]?.count ?? 0), page, pageSize };
}

export async function getFeaturedTemplates(limit = 10) {
  return db
    .select()
    .from(agentTemplates)
    .where(and(isNull(agentTemplates.deleted_at), eq(agentTemplates.is_published, true)))
    .orderBy(desc(agentTemplates.install_count), desc(agentTemplates.avg_rating))
    .limit(Math.min(limit, 50));
}

export async function getTemplateBySlug(slug: string) {
  const result = await db
    .select()
    .from(agentTemplates)
    .where(and(eq(agentTemplates.slug, slug), isNull(agentTemplates.deleted_at)));

  if (result.length === 0) {
    throw AppError.templateNotFound(slug);
  }

  return result[0];
}

async function validateGenomeRefs(refs: TemplateRef[]) {
  if (refs.length === 0) return;

  const slugs = [...new Set(refs.map((r) => r.slug))];
  const existing = await db
    .select({ slug: genomes.slug, is_published: genomes.is_published })
    .from(genomes)
    .where(and(inArray(genomes.slug, slugs), isNull(genomes.deleted_at)));

  const existingMap = new Map(existing.map((g) => [g.slug, g]));
  const missing: string[] = [];

  for (const ref of refs) {
    const genome = existingMap.get(ref.slug);
    if (!genome) missing.push(ref.slug);
    else if (!genome.is_published) missing.push(`${ref.slug} (unpublished)`);
  }

  if (missing.length > 0) {
    throw AppError.templateValidationFailed(`引用的基因组不存在或未发布: ${missing.join(', ')}`);
  }
}

async function validateGeneRefs(refs: TemplateRef[]) {
  if (refs.length === 0) return;

  const slugs = [...new Set(refs.map((r) => r.slug))];
  const existing = await db
    .select({ slug: genes.slug, is_published: genes.is_published })
    .from(genes)
    .where(and(inArray(genes.slug, slugs), isNull(genes.deleted_at)));

  const existingMap = new Map(existing.map((g) => [g.slug, g]));
  const missing: string[] = [];

  for (const ref of refs) {
    const gene = existingMap.get(ref.slug);
    if (!gene) missing.push(ref.slug);
    else if (!gene.is_published) missing.push(`${ref.slug} (unpublished)`);
  }

  if (missing.length > 0) {
    throw AppError.templateValidationFailed(`引用的基因不存在或未发布: ${missing.join(', ')}`);
  }
}

async function uploadFilesToGitea(
  slug: string,
  version: string,
  description: string,
  files: Record<string, string>,
  isNew: boolean,
) {
  const isGiteaReady = await gitea.isGiteaAvailable();
  if (!isGiteaReady) throw AppError.giteaUnavailable();

  try {
    const hasRepo = await gitea.repoExists(slug, GITEA_ORG);
    if (!hasRepo) {
      await gitea.createRepo(slug, description, GITEA_ORG);
    }
    const tag = `v${version}`;
    const commitMsg = isNew ? `feat: ${tag} initial publish` : `feat: ${tag}`;
    const result = await gitea.uploadFiles(slug, files, commitMsg, GITEA_ORG);
    await gitea.createTag(slug, tag, result.sha, GITEA_ORG);

    const fileList = Object.entries(files).map(([path, content]) => ({
      path,
      size: Buffer.byteLength(content, 'utf-8'),
      sha: '',
    }));

    return {
      repositoryUrl: gitea.getRepoUrl(slug, GITEA_ORG),
      commitSha: result.sha,
      gitTag: tag,
      fileList,
      fileCount: fileList.length,
    };
  } catch (err) {
    throw AppError.giteaRepoError(err instanceof Error ? err.message : String(err));
  }
}

export async function createTemplate(input: CreateTemplateInput) {
  if (!input.name || !input.slug || !input.version) {
    throw AppError.templateValidationFailed('name, slug, version 为必填字段');
  }

  if (!semver.valid(input.version)) {
    throw AppError.templateValidationFailed(`无效的版本号: ${input.version}`);
  }

  const existing = await db
    .select({ id: agentTemplates.id })
    .from(agentTemplates)
    .where(and(eq(agentTemplates.slug, input.slug), isNull(agentTemplates.deleted_at)));

  if (existing.length > 0) {
    throw AppError.templateSlugExists(input.slug);
  }

  await validateGenomeRefs(input.genomes);
  if (input.genes?.length) {
    await validateGeneRefs(input.genes);
  }

  let repositoryUrl: string | null = null;
  let commitSha: string | null = null;
  let gitTag: string | null = null;
  let fileList: { path: string; size: number; sha: string }[] | null = null;
  let fileCount = 0;

  if (input.files && Object.keys(input.files).length > 0) {
    const giteaResult = await uploadFilesToGitea(
      input.slug,
      input.version,
      input.short_description || input.description || '',
      input.files,
      true,
    );
    repositoryUrl = giteaResult.repositoryUrl;
    commitSha = giteaResult.commitSha;
    gitTag = giteaResult.gitTag;
    fileList = giteaResult.fileList;
    fileCount = giteaResult.fileCount;
  }

  const [template] = await db
    .insert(agentTemplates)
    .values({
      name: input.name,
      slug: input.slug,
      version: input.version,
      description: input.description ?? '',
      short_description: input.short_description ?? '',
      role: input.role ?? null,
      category: input.category ?? 'general',
      tags: input.tags ?? [],
      icon: input.icon ?? null,
      avatar_url: input.avatar_url ?? null,
      genomes: input.genomes,
      genes: input.genes ?? [],
      compatibility: input.compatibility ?? [],
      author: input.author ?? { type: 'human', name: '' },
      repository_url: repositoryUrl,
      file_count: fileCount,
      is_published: true,
    })
    .returning();

  await db.insert(agentTemplateVersions).values({
    template_id: template.id,
    version: input.version,
    genomes: input.genomes,
    genes: input.genes ?? [],
    commit_sha: commitSha,
    git_tag: gitTag,
    files: fileList,
    changelog: '初始版本',
    is_latest: true,
  });

  await emitTemplateEvent('template.created', input.slug, input.author?.name ?? 'unknown');

  return template;
}

export async function publishVersion(
  slug: string,
  input: {
    version: string;
    genomes: TemplateRef[];
    genes?: TemplateRef[];
    changelog?: string;
    files?: Record<string, string>;
  },
) {
  const template = await getTemplateBySlug(slug);

  if (!semver.valid(input.version)) {
    throw AppError.templateValidationFailed(`无效的版本号: ${input.version}`);
  }

  if (!semver.gt(input.version, template.version)) {
    throw AppError.templateValidationFailed(
      `新版本 ${input.version} 必须大于当前版本 ${template.version}`,
    );
  }

  const existingVer = await db
    .select()
    .from(agentTemplateVersions)
    .where(
      and(
        eq(agentTemplateVersions.template_id, template.id),
        eq(agentTemplateVersions.version, input.version),
      ),
    );

  if (existingVer.length > 0) {
    throw AppError.templateVersionConflict(slug, input.version);
  }

  await validateGenomeRefs(input.genomes);
  if (input.genes?.length) {
    await validateGeneRefs(input.genes);
  }

  let commitSha: string | null = null;
  let gitTag: string | null = null;
  let fileList: { path: string; size: number; sha: string }[] | null = null;
  let fileCount = template.file_count;

  if (input.files && Object.keys(input.files).length > 0) {
    const giteaResult = await uploadFilesToGitea(
      slug,
      input.version,
      template.short_description || template.description || '',
      input.files,
      false,
    );
    commitSha = giteaResult.commitSha;
    gitTag = giteaResult.gitTag;
    fileList = giteaResult.fileList;
    fileCount = giteaResult.fileCount;
  }

  await db
    .update(agentTemplateVersions)
    .set({ is_latest: false })
    .where(
      and(
        eq(agentTemplateVersions.template_id, template.id),
        eq(agentTemplateVersions.is_latest, true),
      ),
    );

  await db.insert(agentTemplateVersions).values({
    template_id: template.id,
    version: input.version,
    genomes: input.genomes,
    genes: input.genes ?? [],
    commit_sha: commitSha,
    git_tag: gitTag,
    files: fileList,
    changelog: input.changelog ?? '',
    is_latest: true,
  });

  const updateValues: Record<string, unknown> = {
    version: input.version,
    genomes: input.genomes,
    genes: input.genes ?? [],
    file_count: fileCount,
    updated_at: new Date(),
  };
  if (!template.repository_url && commitSha) {
    updateValues.repository_url = gitea.getRepoUrl(slug, GITEA_ORG);
  }

  const [updated] = await db
    .update(agentTemplates)
    .set(updateValues)
    .where(eq(agentTemplates.id, template.id))
    .returning();

  await emitTemplateEvent(
    'template.updated',
    slug,
    (template.author as { name?: string })?.name ?? 'unknown',
    {
      version: input.version,
    },
  );

  return updated;
}

export async function updateTemplate(slug: string, updates: Record<string, unknown>) {
  const template = await getTemplateBySlug(slug);

  const allowedFields: Record<string, string> = {
    name: 'name',
    description: 'description',
    short_description: 'short_description',
    role: 'role',
    category: 'category',
    tags: 'tags',
    icon: 'icon',
    avatar_url: 'avatar_url',
    compatibility: 'compatibility',
    is_published: 'is_published',
  };

  const setValues: Record<string, unknown> = { updated_at: new Date() };
  for (const [key, col] of Object.entries(allowedFields)) {
    if (key in updates) {
      setValues[col] = updates[key];
    }
  }

  const [updated] = await db
    .update(agentTemplates)
    .set(setValues)
    .where(eq(agentTemplates.id, template.id))
    .returning();

  return updated;
}

export async function deleteTemplate(slug: string) {
  const template = await getTemplateBySlug(slug);

  if (template.repository_url) {
    try {
      await gitea.deleteRepo(slug, GITEA_ORG);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes('404')) {
        // 仓库已被删或不存在，继续删 DB
      } else {
        throw err;
      }
    }
  }
  const [deleted] = await db
    .delete(agentTemplates)
    .where(eq(agentTemplates.id, template.id))
    .returning();
  return deleted;
}

export async function getTemplateVersions(slug: string) {
  const template = await getTemplateBySlug(slug);

  return db
    .select()
    .from(agentTemplateVersions)
    .where(eq(agentTemplateVersions.template_id, template.id))
    .orderBy(desc(agentTemplateVersions.published_at));
}

export async function getTemplateVersion(slug: string, version: string) {
  const template = await getTemplateBySlug(slug);

  const result = await db
    .select()
    .from(agentTemplateVersions)
    .where(
      and(
        eq(agentTemplateVersions.template_id, template.id),
        eq(agentTemplateVersions.version, version),
      ),
    );

  if (result.length === 0) {
    throw AppError.templateVersionNotFound(slug, version);
  }

  return result[0];
}

export async function getTemplateFiles(slug: string, version?: string) {
  const template = await getTemplateBySlug(slug);
  if (!template.repository_url) {
    return [{ path: 'template.yaml', size: 0, sha: '', type: 'file' as const }];
  }

  let ref = 'main';
  if (version) {
    const ver = await db
      .select()
      .from(agentTemplateVersions)
      .where(
        and(
          eq(agentTemplateVersions.template_id, template.id),
          eq(agentTemplateVersions.version, version),
        ),
      );
    if (ver.length > 0 && ver[0].git_tag) {
      ref = ver[0].git_tag;
    }
  }

  return gitea.getFileTree(slug, ref, GITEA_ORG);
}

export async function getTemplateFileContent(slug: string, filePath: string, version?: string) {
  const template = await getTemplateBySlug(slug);
  if (!template.repository_url) {
    throw AppError.giteaRepoError(`模板 ${slug} 无文件仓库`);
  }

  let ref = 'main';
  if (version) {
    const ver = await db
      .select()
      .from(agentTemplateVersions)
      .where(
        and(
          eq(agentTemplateVersions.template_id, template.id),
          eq(agentTemplateVersions.version, version),
        ),
      );
    if (ver.length > 0 && ver[0].git_tag) {
      ref = ver[0].git_tag;
    }
  }

  return gitea.getFileContent(slug, filePath, ref, GITEA_ORG);
}

export async function getTemplateArchiveStream(slug: string, version?: string) {
  const template = await getTemplateBySlug(slug);
  if (!template.repository_url) {
    throw AppError.giteaRepoError(`模板 ${slug} 无文件仓库，无法下载 archive`);
  }

  let ref = 'main';
  if (version) {
    const ver = await db
      .select()
      .from(agentTemplateVersions)
      .where(
        and(
          eq(agentTemplateVersions.template_id, template.id),
          eq(agentTemplateVersions.version, version),
        ),
      );
    if (ver.length > 0 && ver[0].git_tag) {
      ref = ver[0].git_tag;
    }
  }

  return gitea.getArchiveStream(slug, ref, GITEA_ORG);
}

export async function incrementInstallCount(slug: string) {
  const template = await getTemplateBySlug(slug);

  await db
    .update(agentTemplates)
    .set({
      install_count: sql`${agentTemplates.install_count} + 1`,
      updated_at: new Date(),
    })
    .where(eq(agentTemplates.id, template.id));
}
