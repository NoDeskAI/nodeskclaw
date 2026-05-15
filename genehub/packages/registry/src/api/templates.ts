import { and, desc, eq, sql } from 'drizzle-orm';
import { Hono } from 'hono';
import { db, schema } from '../db/index.js';
import { optionalAuth, requireAuth } from '../middleware/auth.js';
import { paginated, success } from '../middleware/response.js';
import { emitTemplateEvent } from '../services/gene-events.js';
import * as templateService from '../services/template-service.js';

export const templatesRouter = new Hono();

templatesRouter.get('/', optionalAuth(), async (c) => {
  const isAdmin = c.get('authRole') === 'admin';
  const query: templateService.TemplateListQuery = {
    q: c.req.query('q'),
    category: c.req.query('category'),
    role: c.req.query('role'),
    sort: c.req.query('sort'),
    page: Number(c.req.query('page')) || 1,
    page_size: Number(c.req.query('page_size')) || 20,
    ...(isAdmin && c.req.query('include_unpublished') === 'true' && { include_unpublished: true }),
  };

  const result = await templateService.listTemplates(query);
  return paginated(c, result.items, result.total, result.page, result.pageSize);
});

templatesRouter.get('/featured', async (c) => {
  const limit = Number(c.req.query('limit')) || 10;
  const templates = await templateService.getFeaturedTemplates(limit);
  return success(c, templates);
});

templatesRouter.get('/:slug', async (c) => {
  const slug = c.req.param('slug');
  const template = await templateService.getTemplateBySlug(slug);
  return success(c, template);
});

templatesRouter.get('/:slug/versions', async (c) => {
  const slug = c.req.param('slug');
  const versions = await templateService.getTemplateVersions(slug);
  return success(c, versions);
});

templatesRouter.get('/:slug/versions/:version', async (c) => {
  const slug = c.req.param('slug');
  const version = c.req.param('version');
  const ver = await templateService.getTemplateVersion(slug, version);
  return success(c, ver);
});

templatesRouter.get('/:slug/files', async (c) => {
  const slug = c.req.param('slug');
  const version = c.req.query('version');
  const files = await templateService.getTemplateFiles(slug, version);
  return success(c, files);
});

templatesRouter.get('/:slug/files/*', async (c) => {
  const slug = c.req.param('slug');
  const filePath = c.req.path.replace(`/api/v1/templates/${slug}/files/`, '');
  const version = c.req.query('version');
  const content = await templateService.getTemplateFileContent(slug, filePath, version);
  return success(c, { path: filePath, content });
});

templatesRouter.get('/:slug/archive', async (c) => {
  const slug = c.req.param('slug');
  const version = c.req.query('version');
  const stream = await templateService.getTemplateArchiveStream(slug, version);
  return new Response(stream, {
    headers: {
      'Content-Type': 'application/gzip',
      'Content-Disposition': `attachment; filename="${slug}.tar.gz"`,
    },
  });
});

templatesRouter.get('/:slug/reviews', async (c) => {
  const slug = c.req.param('slug');
  await templateService.getTemplateBySlug(slug);

  const page = Number(c.req.query('page')) || 1;
  const pageSize = Math.min(50, Number(c.req.query('page_size')) || 20);
  const offset = (page - 1) * pageSize;
  const { geneReviews } = schema;

  const where = and(eq(geneReviews.entity_type, 'template'), eq(geneReviews.entity_slug, slug));

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

templatesRouter.post('/:slug/reviews', requireAuth('admin'), async (c) => {
  const slug = c.req.param('slug');
  const body = await c.req.json();
  const template = await templateService.getTemplateBySlug(slug);

  const reviewer = (c.get('publisherId') as string) ?? 'admin';
  const isApproved = body.verdict === 'approved';
  const { geneReviews, agentTemplates } = schema;

  const [review] = await db
    .insert(geneReviews)
    .values({
      entity_type: 'template',
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

    await db.update(agentTemplates).set(updateFields).where(eq(agentTemplates.id, template.id));
  }

  await emitTemplateEvent('template.updated', slug, reviewer, {
    action: 'reviewed',
    score: body.score,
    verdict: body.verdict,
  });

  return success(c, review);
});

templatesRouter.post('/', requireAuth('publisher'), async (c) => {
  const body = await c.req.json();
  const template = await templateService.createTemplate(body);
  return success(c, template);
});

templatesRouter.post('/:slug/versions', requireAuth('publisher'), async (c) => {
  const slug = c.req.param('slug');
  const body = await c.req.json();
  const template = await templateService.publishVersion(slug, body);
  return success(c, template);
});

templatesRouter.put('/:slug', requireAuth('publisher'), async (c) => {
  const slug = c.req.param('slug');
  const body = await c.req.json();
  const template = await templateService.updateTemplate(slug, body);
  return success(c, template);
});

templatesRouter.delete('/:slug', requireAuth('admin'), async (c) => {
  const slug = c.req.param('slug');
  const template = await templateService.deleteTemplate(slug);
  return success(c, template);
});

templatesRouter.post('/:slug/installed', async (c) => {
  const slug = c.req.param('slug');
  await templateService.incrementInstallCount(slug);
  return success(c, { slug, recorded: true });
});
