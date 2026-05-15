import { and, eq, isNull } from 'drizzle-orm';
import { db, schema } from '../../db/index.js';
import { emitGeneEvent, emitGenomeEvent, emitTemplateEvent } from '../../services/gene-events.js';

const { genes, geneReviews, genomes, agentTemplates } = schema;

async function findGene(slug: string) {
  const result = await db
    .select()
    .from(genes)
    .where(and(eq(genes.slug, slug), isNull(genes.deleted_at)));
  return result[0] ?? null;
}

export async function postReview(args: {
  slug: string;
  score: number;
  verdict: string;
  comments: string[];
  model?: string;
}) {
  const gene = await findGene(args.slug);
  if (!gene) return { error: `基因 ${args.slug} 不存在` };

  const [review] = await db
    .insert(geneReviews)
    .values({
      gene_id: gene.id,
      entity_type: 'gene',
      entity_slug: args.slug,
      reviewer: 'curator-agent',
      score: args.score,
      verdict: args.verdict,
      comments: args.comments,
      model: args.model,
    })
    .returning();

  const normalizedVerdict = args.verdict.replace(/^approve$/, 'approved');
  const isApproved = normalizedVerdict === 'approved';
  const isRejected = normalizedVerdict === 'rejected' || normalizedVerdict === 'needs_improvement';
  const isFlagged = normalizedVerdict === 'flagged';

  const statusUpdate: Record<string, unknown> = {
    ai_score: args.score,
    ai_verdict: normalizedVerdict,
    ai_enriched: true,
    updated_at: new Date(),
  };

  if (isApproved) {
    statusUpdate.review_status = 'approved';
    statusUpdate.is_published = true;
  } else if (isRejected) {
    statusUpdate.review_status = 'rejected';
    statusUpdate.is_published = false;
  } else if (isFlagged) {
    statusUpdate.review_status = 'flagged';
    statusUpdate.is_published = false;
  }

  await db.update(genes).set(statusUpdate).where(eq(genes.id, gene.id));

  await emitGeneEvent('gene.reviewed', args.slug, 'curator-agent', {
    score: args.score,
    verdict: normalizedVerdict,
  });

  return { review_id: review.id, slug: args.slug, score: args.score, verdict: normalizedVerdict };
}

export async function flagForDeletion(args: { slug: string; reason: string; model?: string }) {
  const gene = await findGene(args.slug);
  if (!gene) return { error: `基因 ${args.slug} 不存在` };

  await db
    .update(genes)
    .set({
      review_status: 'flagged',
      is_published: false,
      ai_verdict: 'flagged',
      updated_at: new Date(),
    })
    .where(eq(genes.id, gene.id));

  await emitGeneEvent('gene.flagged', args.slug, 'curator-agent', {
    reason: args.reason,
  });

  return { flagged: args.slug, reason: args.reason };
}

export async function approveGene(args: { slug: string; model?: string }) {
  const gene = await findGene(args.slug);
  if (!gene) return { error: `基因 ${args.slug} 不存在` };

  await db
    .update(genes)
    .set({
      review_status: 'approved',
      is_published: true,
      ai_verdict: 'approved',
      ai_enriched: true,
      updated_at: new Date(),
    })
    .where(eq(genes.id, gene.id));

  return { approved: args.slug };
}

export async function reviewGenome(args: {
  slug: string;
  score: number;
  verdict: string;
  comments: string[];
  model?: string;
}) {
  const result = await db
    .select()
    .from(genomes)
    .where(and(eq(genomes.slug, args.slug), isNull(genomes.deleted_at)));
  if (result.length === 0) return { error: `基因组 ${args.slug} 不存在` };

  const genome = result[0];
  const isApproved = args.verdict === 'approve' || args.verdict === 'approved';

  await db
    .update(genomes)
    .set({
      avg_rating: args.score,
      is_published: isApproved,
      updated_at: new Date(),
    })
    .where(eq(genomes.id, genome.id));

  const [review] = await db
    .insert(geneReviews)
    .values({
      entity_type: 'genome',
      entity_slug: args.slug,
      reviewer: 'curator-agent',
      score: args.score,
      verdict: args.verdict,
      comments: args.comments,
      model: args.model,
    })
    .returning();

  await emitGenomeEvent('genome.updated', args.slug, 'curator-agent', {
    action: 'reviewed',
    score: args.score,
    verdict: args.verdict,
  });

  return { review_id: review.id, slug: args.slug, score: args.score, verdict: args.verdict };
}

export async function reviewTemplate(args: {
  slug: string;
  score: number;
  verdict: string;
  comments: string[];
  model?: string;
}) {
  const result = await db
    .select()
    .from(agentTemplates)
    .where(and(eq(agentTemplates.slug, args.slug), isNull(agentTemplates.deleted_at)));
  if (result.length === 0) return { error: `模板 ${args.slug} 不存在` };

  const template = result[0];
  const isApproved = args.verdict === 'approve' || args.verdict === 'approved';

  await db
    .update(agentTemplates)
    .set({
      avg_rating: args.score,
      is_published: isApproved,
      updated_at: new Date(),
    })
    .where(eq(agentTemplates.id, template.id));

  const [review] = await db
    .insert(geneReviews)
    .values({
      entity_type: 'template',
      entity_slug: args.slug,
      reviewer: 'curator-agent',
      score: args.score,
      verdict: args.verdict,
      comments: args.comments,
      model: args.model,
    })
    .returning();

  await emitTemplateEvent('template.updated', args.slug, 'curator-agent', {
    action: 'reviewed',
    score: args.score,
    verdict: args.verdict,
  });

  return { review_id: review.id, slug: args.slug, score: args.score, verdict: args.verdict };
}
