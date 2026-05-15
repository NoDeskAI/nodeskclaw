import { and, desc, eq, isNull, sql } from 'drizzle-orm';
import { Hono } from 'hono';
import { db, schema } from '../db/index.js';
import { requireAuth } from '../middleware/auth.js';
import { AppError } from '../middleware/error-handler.js';
import { paginated, success } from '../middleware/response.js';
import { emitGeneEvent } from '../services/gene-events.js';

const { genes, geneReviews } = schema;

export const reviewsRouter = new Hono();

reviewsRouter.get('/:slug/reviews', async (c) => {
  const slug = c.req.param('slug');

  const geneResult = await db
    .select({ id: genes.id })
    .from(genes)
    .where(and(eq(genes.slug, slug), isNull(genes.deleted_at)));

  if (geneResult.length === 0) throw AppError.geneNotFound(slug);

  const page = Number(c.req.query('page')) || 1;
  const pageSize = Math.min(50, Number(c.req.query('page_size')) || 20);
  const offset = (page - 1) * pageSize;
  const geneId = geneResult[0].id;

  const [items, countResult] = await Promise.all([
    db
      .select()
      .from(geneReviews)
      .where(eq(geneReviews.gene_id, geneId))
      .orderBy(desc(geneReviews.created_at))
      .limit(pageSize)
      .offset(offset),
    db
      .select({ count: sql<number>`count(*)` })
      .from(geneReviews)
      .where(eq(geneReviews.gene_id, geneId)),
  ]);

  const total = Number(countResult[0]?.count ?? 0);
  return paginated(c, items, total, page, pageSize);
});

reviewsRouter.post('/:slug/reviews', requireAuth('admin'), async (c) => {
  const slug = c.req.param('slug');
  const body = await c.req.json();

  const geneResult = await db
    .select({ id: genes.id })
    .from(genes)
    .where(and(eq(genes.slug, slug), isNull(genes.deleted_at)));

  if (geneResult.length === 0) throw AppError.geneNotFound(slug);

  const gene = geneResult[0];
  const reviewer = (c.get('publisherId') as string) ?? 'admin';
  const isApproved = body.verdict === 'approved';

  const [review] = await db
    .insert(geneReviews)
    .values({
      gene_id: gene.id,
      entity_type: 'gene',
      entity_slug: slug,
      reviewer,
      score: body.score ?? null,
      verdict: body.verdict,
      comments: body.comments ?? [],
    })
    .returning();

  if (body.verdict) {
    const updateFields: Record<string, unknown> = {
      review_status: body.verdict,
      updated_at: new Date(),
    };
    if (isApproved) updateFields.is_published = true;
    if (body.verdict === 'rejected' || body.verdict === 'flagged')
      updateFields.is_published = false;

    await db.update(genes).set(updateFields).where(eq(genes.id, gene.id));
  }

  await emitGeneEvent('gene.reviewed', slug, reviewer, {
    score: body.score,
    verdict: body.verdict,
  });

  return success(c, review);
});

reviewsRouter.post('/:slug/reviews/:reviewId/feedback', requireAuth('admin'), async (c) => {
  const slug = c.req.param('slug');
  const reviewId = c.req.param('reviewId');
  const body = await c.req.json();

  const geneResult = await db
    .select({ id: genes.id })
    .from(genes)
    .where(and(eq(genes.slug, slug), isNull(genes.deleted_at)));

  if (geneResult.length === 0) throw AppError.geneNotFound(slug);

  const reviewResult = await db.select().from(geneReviews).where(eq(geneReviews.id, reviewId));

  if (reviewResult.length === 0) {
    throw new AppError(404, 'review_not_found', `Review ${reviewId} 不存在`, 404);
  }

  const [updated] = await db
    .update(geneReviews)
    .set({ feedback: body.feedback })
    .where(eq(geneReviews.id, reviewId))
    .returning();

  return success(c, updated);
});
