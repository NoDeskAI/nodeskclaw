import { and, desc, eq, inArray, isNull, sql } from 'drizzle-orm';
import { db, schema } from '../../db/index.js';

const { genomes, genomeVersions, genes, geneRelations } = schema;

export async function listGenomes(args: {
  category?: string;
  q?: string;
  page?: number;
  page_size?: number;
}) {
  const page = Math.max(1, args.page ?? 1);
  const pageSize = Math.min(50, Math.max(1, args.page_size ?? 20));
  const offset = (page - 1) * pageSize;

  const conditions = [isNull(genomes.deleted_at), eq(genomes.is_published, true)];

  if (args.category) conditions.push(eq(genomes.category, args.category));
  if (args.q) {
    const term = `%${args.q}%`;
    conditions.push(
      sql`(${genomes.name} ILIKE ${term} OR ${genomes.slug} ILIKE ${term} OR ${genomes.short_description} ILIKE ${term})`,
    );
  }

  const where = and(...conditions);

  const [items, countResult] = await Promise.all([
    db
      .select({
        slug: genomes.slug,
        name: genomes.name,
        version: genomes.version,
        short_description: genomes.short_description,
        category: genomes.category,
        tags: genomes.tags,
        install_count: genomes.install_count,
        avg_rating: genomes.avg_rating,
        genes: genomes.genes,
      })
      .from(genomes)
      .where(where)
      .orderBy(desc(genomes.install_count))
      .limit(pageSize)
      .offset(offset),
    db.select({ count: sql<number>`count(*)` }).from(genomes).where(where),
  ]);

  return { items, total: Number(countResult[0]?.count ?? 0), page, pageSize };
}

export async function getGenome(args: { slug: string }) {
  const result = await db
    .select()
    .from(genomes)
    .where(and(eq(genomes.slug, args.slug), isNull(genomes.deleted_at)));

  if (result.length === 0) return { error: `基因组 ${args.slug} 不存在` };

  const genome = result[0];
  const versions = await db
    .select({ version: genomeVersions.version, is_latest: genomeVersions.is_latest })
    .from(genomeVersions)
    .where(eq(genomeVersions.genome_id, genome.id))
    .orderBy(desc(genomeVersions.published_at))
    .limit(10);

  return { genome, versions };
}

export async function suggestGenome(args: { needs: string; product?: string }) {
  const term = `%${args.needs}%`;
  const conditions = [
    isNull(genomes.deleted_at),
    eq(genomes.is_published, true),
    sql`(${genomes.name} ILIKE ${term} OR ${genomes.short_description} ILIKE ${term} OR ${genomes.description} ILIKE ${term} OR ${genomes.tags}::text ILIKE ${term})`,
  ];

  const candidates = await db
    .select({
      slug: genomes.slug,
      name: genomes.name,
      version: genomes.version,
      short_description: genomes.short_description,
      category: genomes.category,
      tags: genomes.tags,
      install_count: genomes.install_count,
      avg_rating: genomes.avg_rating,
      genes: genomes.genes,
    })
    .from(genomes)
    .where(and(...conditions))
    .orderBy(desc(genomes.avg_rating), desc(genomes.install_count))
    .limit(5);

  if (candidates.length === 0) {
    return { suggestions: [], hint: '没有找到匹配的基因组，尝试更宽泛的描述' };
  }

  return { suggestions: candidates };
}

export async function validateGenome(args: { gene_slugs: string[] }) {
  const slugs = [...new Set(args.gene_slugs)];
  if (slugs.length === 0) return { valid: false, error: '至少需要一个基因' };

  const existing = await db
    .select({
      slug: genes.slug,
      is_published: genes.is_published,
      deleted_at: genes.deleted_at,
      category: genes.category,
    })
    .from(genes)
    .where(inArray(genes.slug, slugs));

  const geneMap = new Map(existing.map((g) => [g.slug, g]));

  const missing: string[] = [];
  const unpublished: string[] = [];
  const deleted: string[] = [];
  const categories: string[] = [];

  for (const slug of slugs) {
    const gene = geneMap.get(slug);
    if (!gene) {
      missing.push(slug);
    } else if (gene.deleted_at) {
      deleted.push(slug);
    } else if (!gene.is_published) {
      unpublished.push(slug);
    } else {
      categories.push(gene.category ?? 'uncategorized');
    }
  }

  const sourceGenes = db
    .$with('source_genes')
    .as(
      db.select({ id: genes.id, slug: genes.slug }).from(genes).where(inArray(genes.slug, slugs)),
    );
  const targetGenes = db
    .$with('target_genes')
    .as(
      db.select({ id: genes.id, slug: genes.slug }).from(genes).where(inArray(genes.slug, slugs)),
    );

  const conflicts = await db
    .with(sourceGenes, targetGenes)
    .select({
      source: sourceGenes.slug,
      target: targetGenes.slug,
      relation_type: geneRelations.relation_type,
      reason: geneRelations.reason,
    })
    .from(geneRelations)
    .innerJoin(sourceGenes, eq(sourceGenes.id, geneRelations.source_gene_id))
    .innerJoin(targetGenes, eq(targetGenes.id, geneRelations.target_gene_id))
    .where(eq(geneRelations.relation_type, 'conflict'));

  const valid = missing.length === 0 && unpublished.length === 0 && deleted.length === 0;

  return {
    valid,
    gene_count: slugs.length,
    missing,
    unpublished,
    deleted,
    conflicts: conflicts.map((c) => ({
      source: c.source,
      target: c.target,
      reason: c.reason,
    })),
    category_distribution: Object.fromEntries(
      [...new Set(categories)].map((cat) => [cat, categories.filter((c) => c === cat).length]),
    ),
  };
}
