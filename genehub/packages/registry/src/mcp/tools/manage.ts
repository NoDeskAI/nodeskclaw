import { and, eq, isNull, sql } from 'drizzle-orm';
import { db, schema } from '../../db/index.js';

const { genes, geneRelations } = schema;

async function findGene(slug: string) {
  const result = await db
    .select()
    .from(genes)
    .where(and(eq(genes.slug, slug), isNull(genes.deleted_at)));
  return result[0] ?? null;
}

export async function updateGeneCategory(args: {
  slug: string;
  category: string;
  tags?: string[];
  reason: string;
}) {
  const gene = await findGene(args.slug);
  if (!gene) return { error: `基因 ${args.slug} 不存在` };

  const setValues: Record<string, unknown> = {
    category: args.category,
    updated_at: new Date(),
  };
  if (args.tags) setValues.tags = args.tags;

  const [updated] = await db
    .update(genes)
    .set(setValues)
    .where(eq(genes.id, gene.id))
    .returning({ slug: genes.slug, category: genes.category, tags: genes.tags });

  return { updated, reason: args.reason };
}

export async function updateGeneDescription(args: {
  slug: string;
  description?: string;
  short_description?: string;
}) {
  const gene = await findGene(args.slug);
  if (!gene) return { error: `基因 ${args.slug} 不存在` };

  const setValues: Record<string, unknown> = { updated_at: new Date() };
  if (args.description) setValues.description = args.description;
  if (args.short_description) setValues.short_description = args.short_description;

  const [updated] = await db
    .update(genes)
    .set(setValues)
    .where(eq(genes.id, gene.id))
    .returning({ slug: genes.slug, description: genes.description });

  return { updated };
}

export async function updateGeneSynergies(args: {
  slug: string;
  target_slug: string;
  relation_type: string;
  strength?: number;
  reason?: string;
}) {
  const source = await findGene(args.slug);
  if (!source) return { error: `基因 ${args.slug} 不存在` };

  const target = await findGene(args.target_slug);
  if (!target) return { error: `基因 ${args.target_slug} 不存在` };

  const existing = await db
    .select()
    .from(geneRelations)
    .where(
      and(
        eq(geneRelations.source_gene_id, source.id),
        eq(geneRelations.target_gene_id, target.id),
        eq(geneRelations.relation_type, args.relation_type),
      ),
    );

  if (existing.length > 0) {
    const [updated] = await db
      .update(geneRelations)
      .set({
        strength: args.strength ?? existing[0].strength,
        reason: args.reason ?? existing[0].reason,
      })
      .where(eq(geneRelations.id, existing[0].id))
      .returning();
    return { action: 'updated', relation: updated };
  }

  const [created] = await db
    .insert(geneRelations)
    .values({
      source_gene_id: source.id,
      target_gene_id: target.id,
      relation_type: args.relation_type,
      strength: args.strength ?? 0.5,
      reason: args.reason,
      created_by: 'curator-agent',
    })
    .returning();

  return { action: 'created', relation: created };
}

export async function mergeGenes(args: {
  source_slug: string;
  target_slug: string;
  reason: string;
}) {
  const source = await findGene(args.source_slug);
  if (!source) return { error: `基因 ${args.source_slug} 不存在` };

  const target = await findGene(args.target_slug);
  if (!target) return { error: `基因 ${args.target_slug} 不存在` };

  const [merged] = await db
    .update(genes)
    .set({
      deleted_at: new Date(),
      is_published: false,
      parent_gene_id: target.id,
      updated_at: new Date(),
    })
    .where(eq(genes.id, source.id))
    .returning({ slug: genes.slug });

  await db.insert(geneRelations).values({
    source_gene_id: source.id,
    target_gene_id: target.id,
    relation_type: 'replaces',
    strength: 1.0,
    reason: args.reason,
    created_by: 'curator-agent',
  });

  const sourceSynergies = (source.synergies as string[]) ?? [];
  const targetSynergies = (target.synergies as string[]) ?? [];
  const mergedSynergies = [...new Set([...targetSynergies, ...sourceSynergies])].filter(
    (s) => s !== args.source_slug && s !== args.target_slug,
  );

  await db
    .update(genes)
    .set({
      synergies: mergedSynergies,
      install_count: sql`${genes.install_count} + ${source.install_count}`,
      updated_at: new Date(),
    })
    .where(eq(genes.id, target.id));

  return {
    merged: merged.slug,
    into: args.target_slug,
    reason: args.reason,
  };
}
