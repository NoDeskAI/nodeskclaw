import { and, desc, eq, isNull, sql } from 'drizzle-orm';
import { db, schema } from '../../db/index.js';

const { genes, geneReviews, geneRelations } = schema;

export async function listGenes(args: {
  category?: string;
  source?: string;
  review_status?: string;
  ai_enriched?: boolean;
  page?: number;
  page_size?: number;
}) {
  const page = Math.max(1, args.page ?? 1);
  const pageSize = Math.min(50, Math.max(1, args.page_size ?? 20));
  const offset = (page - 1) * pageSize;

  const conditions = [isNull(genes.deleted_at)];

  if (args.category) conditions.push(eq(genes.category, args.category));
  if (args.source) conditions.push(eq(genes.source, args.source));
  if (args.review_status) conditions.push(eq(genes.review_status, args.review_status));
  if (args.ai_enriched !== undefined) conditions.push(eq(genes.ai_enriched, args.ai_enriched));

  const items = await db
    .select({
      slug: genes.slug,
      name: genes.name,
      category: genes.category,
      source: genes.source,
      review_status: genes.review_status,
      ai_score: genes.ai_score,
      ai_verdict: genes.ai_verdict,
      ai_enriched: genes.ai_enriched,
      version: genes.version,
      install_count: genes.install_count,
      created_at: genes.created_at,
    })
    .from(genes)
    .where(and(...conditions))
    .orderBy(desc(genes.created_at))
    .limit(pageSize)
    .offset(offset);

  const [{ count }] = await db
    .select({ count: sql<number>`count(*)` })
    .from(genes)
    .where(and(...conditions));

  return { items, total: Number(count), page, page_size: pageSize };
}

export async function getGene(args: { slug: string }) {
  const result = await db
    .select()
    .from(genes)
    .where(and(eq(genes.slug, args.slug), isNull(genes.deleted_at)));

  if (result.length === 0) return { error: `基因 ${args.slug} 不存在` };

  const gene = result[0];

  const reviews = await db
    .select()
    .from(geneReviews)
    .where(eq(geneReviews.gene_id, gene.id))
    .orderBy(desc(geneReviews.created_at))
    .limit(10);

  const relations = await db
    .select()
    .from(geneRelations)
    .where(eq(geneRelations.source_gene_id, gene.id));

  return { gene, reviews, relations };
}

export async function searchGenes(args: { query: string; limit?: number }) {
  const limit = Math.min(20, args.limit ?? 10);
  const term = `%${args.query}%`;

  return db
    .select({
      slug: genes.slug,
      name: genes.name,
      short_description: genes.short_description,
      category: genes.category,
      tags: genes.tags,
      source: genes.source,
      ai_score: genes.ai_score,
    })
    .from(genes)
    .where(
      and(
        isNull(genes.deleted_at),
        sql`(${genes.name} ILIKE ${term} OR ${genes.slug} ILIKE ${term} OR ${genes.description} ILIKE ${term} OR ${genes.short_description} ILIKE ${term})`,
      ),
    )
    .orderBy(desc(genes.install_count))
    .limit(limit);
}

export async function findSimilar(args: { slug: string }) {
  const result = await db
    .select()
    .from(genes)
    .where(and(eq(genes.slug, args.slug), isNull(genes.deleted_at)));

  if (result.length === 0) return { error: `基因 ${args.slug} 不存在` };

  const gene = result[0];
  const category = gene.category;
  const tags = gene.tags as string[];

  const candidates = await db
    .select({
      slug: genes.slug,
      name: genes.name,
      short_description: genes.short_description,
      category: genes.category,
      tags: genes.tags,
      source: genes.source,
    })
    .from(genes)
    .where(
      and(
        isNull(genes.deleted_at),
        eq(genes.category, category),
        sql`${genes.slug} != ${args.slug}`,
      ),
    )
    .limit(20);

  return candidates.map((c) => {
    const cTags = c.tags as string[];
    const overlap = tags.filter((t) => cTags.includes(t)).length;
    return { ...c, tag_overlap: overlap };
  });
}

export async function getLibraryStats() {
  const [totalResult] = await db
    .select({ count: sql<number>`count(*)` })
    .from(genes)
    .where(isNull(genes.deleted_at));

  const categoryStats = await db
    .select({
      category: genes.category,
      count: sql<number>`count(*)`,
    })
    .from(genes)
    .where(isNull(genes.deleted_at))
    .groupBy(genes.category);

  const sourceStats = await db
    .select({
      source: genes.source,
      count: sql<number>`count(*)`,
    })
    .from(genes)
    .where(isNull(genes.deleted_at))
    .groupBy(genes.source);

  const reviewStats = await db
    .select({
      review_status: genes.review_status,
      count: sql<number>`count(*)`,
    })
    .from(genes)
    .where(isNull(genes.deleted_at))
    .groupBy(genes.review_status);

  const [enrichedResult] = await db
    .select({ count: sql<number>`count(*)` })
    .from(genes)
    .where(and(isNull(genes.deleted_at), eq(genes.ai_enriched, true)));

  return {
    total: Number(totalResult.count),
    ai_enriched: Number(enrichedResult.count),
    by_category: categoryStats.map((r) => ({ category: r.category, count: Number(r.count) })),
    by_source: sourceStats.map((r) => ({ source: r.source, count: Number(r.count) })),
    by_review_status: reviewStats.map((r) => ({
      status: r.review_status,
      count: Number(r.count),
    })),
  };
}

export async function evaluateInContext(args: { slug: string }) {
  const result = await db
    .select()
    .from(genes)
    .where(and(eq(genes.slug, args.slug), isNull(genes.deleted_at)));

  if (result.length === 0) return { error: `基因 ${args.slug} 不存在` };

  const gene = result[0];

  const sameCategoryGenes = await db
    .select({
      slug: genes.slug,
      name: genes.name,
      short_description: genes.short_description,
      tags: genes.tags,
      ai_score: genes.ai_score,
      install_count: genes.install_count,
    })
    .from(genes)
    .where(
      and(
        isNull(genes.deleted_at),
        eq(genes.category, gene.category),
        sql`${genes.slug} != ${args.slug}`,
      ),
    )
    .orderBy(desc(genes.install_count))
    .limit(10);

  const reviews = await db
    .select()
    .from(geneReviews)
    .where(eq(geneReviews.gene_id, gene.id))
    .orderBy(desc(geneReviews.created_at))
    .limit(5);

  const overriddenReviews = reviews.filter((r) => r.feedback != null);

  return {
    gene,
    context: {
      same_category_count: sameCategoryGenes.length,
      same_category_genes: sameCategoryGenes,
      existing_reviews: reviews,
      overridden_decisions: overriddenReviews,
    },
  };
}
