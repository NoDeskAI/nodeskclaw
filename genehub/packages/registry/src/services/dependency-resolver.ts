import { and, eq, isNull } from 'drizzle-orm';
import semver from 'semver';
import { db, schema } from '../db/index.js';
import { AppError } from '../middleware/error-handler.js';

const { genes, geneVersions } = schema;

export type InstallPlanItem = {
  slug: string;
  version: string;
  manifest: unknown;
  optional: boolean;
};

export type ResolveResult = {
  plan: InstallPlanItem[];
  warnings: string[];
};

export async function resolve(
  slug: string,
  versionRange?: string,
  product?: string,
): Promise<ResolveResult> {
  const visited = new Set<string>();
  const resolving = new Set<string>();
  const plan: InstallPlanItem[] = [];
  const warnings: string[] = [];

  await resolveRecursive(
    slug,
    versionRange ?? '*',
    false,
    visited,
    resolving,
    plan,
    warnings,
    product,
  );

  return { plan, warnings };
}

async function resolveRecursive(
  slug: string,
  versionRange: string,
  optional: boolean,
  visited: Set<string>,
  resolving: Set<string>,
  plan: InstallPlanItem[],
  warnings: string[],
  product?: string,
): Promise<void> {
  if (visited.has(slug)) return;

  if (resolving.has(slug)) {
    throw AppError.dependencyResolveFailed(`循环依赖: ${slug}`);
  }

  resolving.add(slug);

  const geneRows = await db
    .select()
    .from(genes)
    .where(and(eq(genes.slug, slug), isNull(genes.deleted_at)));

  if (geneRows.length === 0) {
    if (optional) {
      warnings.push(`可选依赖 ${slug} 不存在，已跳过`);
      resolving.delete(slug);
      return;
    }
    throw AppError.dependencyResolveFailed(`基因 ${slug} 不存在`);
  }

  const gene = geneRows[0];

  if (product) {
    const compat = (gene.compatibility as string[]) ?? [];
    if (!compat.includes(product)) {
      warnings.push(`${slug} 不兼容 ${product}，已跳过`);
      resolving.delete(slug);
      return;
    }
  }

  const versions = await db.select().from(geneVersions).where(eq(geneVersions.gene_id, gene.id));

  const matchedVersion = findMatchingVersion(
    versions.map((v) => v.version),
    versionRange,
  );

  if (!matchedVersion) {
    if (optional) {
      warnings.push(`${slug} 没有满足 ${versionRange} 的版本，已跳过`);
      resolving.delete(slug);
      return;
    }
    throw AppError.dependencyResolveFailed(`${slug} 没有满足 ${versionRange} 的版本`);
  }

  const versionRow = versions.find((v) => v.version === matchedVersion);
  if (!versionRow) {
    throw AppError.dependencyResolveFailed(`${slug}@${matchedVersion} 版本数据异常`);
  }

  const manifest = versionRow.manifest as Record<string, unknown>;
  const deps = (manifest.dependencies ?? []) as Array<{
    slug: string;
    version: string;
    optional?: boolean;
  }>;

  for (const dep of deps) {
    await resolveRecursive(
      dep.slug,
      dep.version ?? '*',
      dep.optional ?? false,
      visited,
      resolving,
      plan,
      warnings,
      product,
    );
  }

  plan.push({
    slug,
    version: matchedVersion,
    manifest: versionRow.manifest,
    optional,
  });

  resolving.delete(slug);
  visited.add(slug);
}

function findMatchingVersion(available: string[], range: string): string | null {
  if (range === '*' || range === 'latest') {
    const sorted = available.filter((v) => semver.valid(v)).sort((a, b) => semver.compare(b, a));
    return sorted[0] ?? null;
  }

  if (semver.valid(range)) {
    return available.includes(range) ? range : null;
  }

  const validRange = semver.validRange(range);
  if (!validRange) {
    return available.includes(range) ? range : null;
  }

  const matched = semver.maxSatisfying(available, range);
  return matched;
}
