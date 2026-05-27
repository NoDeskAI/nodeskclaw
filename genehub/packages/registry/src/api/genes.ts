import { Hono } from 'hono';
import type { AuthVariables } from '../middleware/auth.js';
import { optionalAuth, requireAuth } from '../middleware/auth.js';
import { paginated, success } from '../middleware/response.js';
import { federatedSearch } from '../services/federated-search.js';
import * as geneService from '../services/gene-service.js';

export const genesRouter = new Hono<{ Variables: AuthVariables }>();

genesRouter.get('/search', async (c) => {
  const q = c.req.query('q') ?? '';
  if (!q.trim())
    return success(c, { query: '', total: 0, items: [], sources: { local: 0, clawhub: 0 } });

  const result = await federatedSearch(q, {
    category: c.req.query('category'),
    limit: Number(c.req.query('limit')) || 20,
  });
  return success(c, result);
});

genesRouter.get('/', optionalAuth(), async (c) => {
  const isAdmin = c.get('authRole') === 'admin';
  const query: geneService.GeneListQuery = {
    q: c.req.query('q'),
    category: c.req.query('category'),
    tags: c.req.query('tags'),
    compatibility: c.req.query('compatibility'),
    sort: c.req.query('sort'),
    page: Number(c.req.query('page')) || 1,
    page_size: Number(c.req.query('page_size')) || 20,
    ...(isAdmin && c.req.query('review_status') && { review_status: c.req.query('review_status') }),
    ...(isAdmin && c.req.query('include_unpublished') === 'true' && { include_unpublished: true }),
  };

  const result = await geneService.listGenes(query);
  return paginated(c, result.items, result.total, result.page, result.pageSize);
});

genesRouter.get('/tags', async (c) => {
  const tags = await geneService.getGeneTags();
  return success(c, tags);
});

genesRouter.get('/featured', async (c) => {
  const limit = Number(c.req.query('limit')) || 10;
  const genes = await geneService.getFeaturedGenes(limit);
  return success(c, genes);
});

genesRouter.get('/:slug', async (c) => {
  const slug = c.req.param('slug');
  const gene = await geneService.getGeneBySlug(slug);
  return success(c, gene);
});

genesRouter.get('/:slug/manifest', async (c) => {
  const slug = c.req.param('slug');
  const version = c.req.query('version');
  const manifest = await geneService.getGeneManifest(slug, version);
  return success(c, manifest);
});

genesRouter.get('/:slug/versions', async (c) => {
  const slug = c.req.param('slug');
  const versions = await geneService.getGeneVersions(slug);
  return success(c, versions);
});

genesRouter.get('/:slug/versions/:version', async (c) => {
  const slug = c.req.param('slug');
  const version = c.req.param('version');
  const ver = await geneService.getGeneVersion(slug, version);
  return success(c, ver);
});

genesRouter.get('/:slug/files', async (c) => {
  const slug = c.req.param('slug');
  const version = c.req.query('version');
  const files = await geneService.getGeneFiles(slug, version);
  return success(c, files);
});

genesRouter.get('/:slug/files/*', async (c) => {
  const slug = c.req.param('slug');
  const filePath = c.req.path.replace(`/api/v1/genes/${slug}/files/`, '');
  const version = c.req.query('version');
  const content = await geneService.getGeneFileContent(slug, filePath, version);
  return success(c, { path: filePath, content });
});

genesRouter.get('/:slug/archive', async (c) => {
  const slug = c.req.param('slug');
  const version = c.req.query('version');
  const stream = await geneService.getGeneArchiveStream(slug, version);
  return new Response(stream, {
    headers: {
      'Content-Type': 'application/gzip',
      'Content-Disposition': `attachment; filename="${slug}.tar.gz"`,
    },
  });
});

genesRouter.post('/', requireAuth('publisher'), async (c) => {
  const body = await c.req.json();
  const publisherCtx = {
    publisherId: c.get('publisherId') as string | undefined,
    githubLogin: c.get('githubLogin') as string | undefined,
    isAdmin: (c.get('authRole') as string) === 'admin',
  };
  const gene = await geneService.createGene(body.manifest ?? body, publisherCtx, body.files);
  return success(c, gene);
});

genesRouter.post('/:slug/versions', requireAuth('publisher'), async (c) => {
  const slug = c.req.param('slug');
  const body = await c.req.json();
  const gene = await geneService.publishVersion(
    slug,
    body.manifest ?? body,
    body.changelog,
    body.files,
  );
  return success(c, gene);
});

genesRouter.put('/:slug', requireAuth('publisher'), async (c) => {
  const slug = c.req.param('slug');
  const body = await c.req.json();
  const gene = await geneService.updateGene(slug, body);
  return success(c, gene);
});

genesRouter.delete('/:slug', requireAuth('admin'), async (c) => {
  const slug = c.req.param('slug');
  const gene = await geneService.deleteGene(slug);
  return success(c, gene);
});

genesRouter.get('/:slug/synergies', async (c) => {
  const slug = c.req.param('slug');
  const synergies = await geneService.getGeneSynergies(slug);
  return success(c, synergies);
});

genesRouter.post('/:slug/installed', async (c) => {
  const slug = c.req.param('slug');
  await geneService.incrementInstallCount(slug);
  return success(c, { slug, recorded: true });
});

genesRouter.post('/:slug/effectiveness', async (c) => {
  const slug = c.req.param('slug');
  const body = await c.req.json();
  await geneService.reportEffectiveness(slug, body);
  return success(c, { slug, recorded: true });
});
