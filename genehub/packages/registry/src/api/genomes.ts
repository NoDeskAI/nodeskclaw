import { and, desc, eq, sql } from 'drizzle-orm';
import { Hono } from 'hono';
import { db, schema } from '../db/index.js';
import { optionalAuth, requireAuth } from '../middleware/auth.js';
import { paginated, success } from '../middleware/response.js';
import { emitGenomeEvent } from '../services/gene-events.js';
import * as genomeService from '../services/genome-service.js';

export const genomesRouter = new Hono();

genomesRouter.get('/', optionalAuth(), async (c) => {
  const isAdmin = c.get('authRole') === 'admin';
  const query: genomeService.GenomeListQuery = {
    q: c.req.query('q'),
    category: c.req.query('category'),
    sort: c.req.query('sort'),
    page: Number(c.req.query('page')) || 1,
    page_size: Number(c.req.query('page_size')) || 20,
    ...(isAdmin && c.req.query('include_unpublished') === 'true' && { include_unpublished: true }),
  };

  const result = await genomeService.listGenomes(query);
  return paginated(c, result.items, result.total, result.page, result.pageSize);
});

genomesRouter.get('/featured', async (c) => {
  const limit = Number(c.req.query('limit')) || 10;
  const genomes = await genomeService.getFeaturedGenomes(limit);
  return success(c, genomes);
});

genomesRouter.get('/:slug', async (c) => {
  const slug = c.req.param('slug');
  const genome = await genomeService.getGenomeBySlug(slug);
  return success(c, genome);
});

genomesRouter.get('/:slug/resolve', async (c) => {
  const slug = c.req.param('slug');
  const version = c.req.query('version');
  const product = c.req.query('product');
  const result = await genomeService.resolveGenome(slug, version, product);
  return success(c, result);
});

genomesRouter.get('/:slug/versions', async (c) => {
  const slug = c.req.param('slug');
  const versions = await genomeService.getGenomeVersions(slug);
  return success(c, versions);
});

genomesRouter.get('/:slug/versions/:version', async (c) => {
  const slug = c.req.param('slug');
  const version = c.req.param('version');
  const ver = await genomeService.getGenomeVersion(slug, version);
  return success(c, ver);
});

genomesRouter.get('/:slug/files', async (c) => {
  const slug = c.req.param('slug');
  const version = c.req.query('version');
  const files = await genomeService.getGenomeFiles(slug, version);
  return success(c, files);
});

genomesRouter.get('/:slug/files/*', async (c) => {
  const slug = c.req.param('slug');
  const filePath = c.req.path.replace(`/api/v1/genomes/${slug}/files/`, '');
  const version = c.req.query('version');
  const content = await genomeService.getGenomeFileContent(slug, filePath, version);
  return success(c, { path: filePath, content });
});

genomesRouter.get('/:slug/archive', async (c) => {
  const slug = c.req.param('slug');
  const version = c.req.query('version');
  const stream = await genomeService.getGenomeArchiveStream(slug, version);
  return new Response(stream, {
    headers: {
      'Content-Type': 'application/gzip',
      'Content-Disposition': `attachment; filename="${slug}.tar.gz"`,
    },
  });
});

genomesRouter.get('/:slug/reviews', async (c) => {
  const slug = c.req.param('slug');
  await genomeService.getGenomeBySlug(slug);

  const page = Number(c.req.query('page')) || 1;
  const pageSize = Math.min(50, Number(c.req.query('page_size')) || 20);
  const offset = (page - 1) * pageSize;
  const { geneReviews } = schema;

  const where = and(eq(geneReviews.entity_type, 'genome'), eq(geneReviews.entity_slug, slug));

  const [items, countResult] = await Promise.all([
    db
      .select()
      .from(geneReviews)
      .where(where)
      .orderBy(desc(geneReviews.created_at))
      .limit(pageSize)
      .offset(offset),
    db.select({ count: sql<number>`count(*)` }).from(geneReviews).where(where),
  ]);

  return paginated(c, items, Number(countResult[0]?.count ?? 0), page, pageSize);
});

genomesRouter.post('/:slug/reviews', requireAuth('admin'), async (c) => {
  const slug = c.req.param('slug');
  const body = await c.req.json();
  const genome = await genomeService.getGenomeBySlug(slug);

  const reviewer = (c.get('publisherId') as string) ?? 'admin';
  const isApproved = body.verdict === 'approved';
  const { geneReviews, genomes } = schema;

  const [review] = await db
    .insert(geneReviews)
    .values({
      entity_type: 'genome',
      entity_slug: slug,
      reviewer,
      score: body.score ?? null,
      verdict: body.verdict,
      comments: body.comments ?? [],
    })
    .returning();

  if (body.verdict) {
    const updateFields: Record<string, unknown> = { updated_at: new Date() };
    if (isApproved) updateFields.is_published = true;
    if (body.verdict === 'rejected' || body.verdict === 'flagged')
      updateFields.is_published = false;

    await db.update(genomes).set(updateFields).where(eq(genomes.id, genome.id));
  }

  await emitGenomeEvent('genome.updated', slug, reviewer, {
    action: 'reviewed',
    score: body.score,
    verdict: body.verdict,
  });

  return success(c, review);
});

genomesRouter.post('/', requireAuth('publisher'), async (c) => {
  const body = await c.req.json();
  const genome = await genomeService.createGenome(body);
  return success(c, genome);
});

genomesRouter.post('/:slug/versions', requireAuth('publisher'), async (c) => {
  const slug = c.req.param('slug');
  const body = await c.req.json();
  const genome = await genomeService.publishVersion(slug, body);
  return success(c, genome);
});

genomesRouter.put('/:slug', requireAuth('publisher'), async (c) => {
  const slug = c.req.param('slug');
  const body = await c.req.json();
  const genome = await genomeService.updateGenome(slug, body);
  return success(c, genome);
});

genomesRouter.delete('/:slug', requireAuth('admin'), async (c) => {
  const slug = c.req.param('slug');
  const genome = await genomeService.deleteGenome(slug);
  return success(c, genome);
});

genomesRouter.post('/:slug/installed', async (c) => {
  const slug = c.req.param('slug');
  await genomeService.incrementInstallCount(slug);
  return success(c, { slug, recorded: true });
});
