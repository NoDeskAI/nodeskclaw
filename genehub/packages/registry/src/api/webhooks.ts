import { createHmac, timingSafeEqual } from 'node:crypto';
import { Hono } from 'hono';
import { AppError } from '../middleware/error-handler.js';
import { success } from '../middleware/response.js';
import * as geneService from '../services/gene-service.js';

const WEBHOOK_SECRET = process.env.GENEHUB_WEBHOOK_SECRET ?? '';

export const webhooksRouter = new Hono();

function verifySignature(payload: string, signature: string | undefined): boolean {
  if (!WEBHOOK_SECRET) return true;
  if (!signature) return false;
  const expected = createHmac('sha256', WEBHOOK_SECRET).update(payload).digest('hex');
  const sig = signature.replace('sha256=', '');
  try {
    return timingSafeEqual(Buffer.from(sig, 'hex'), Buffer.from(expected, 'hex'));
  } catch {
    return false;
  }
}

webhooksRouter.use('*', async (c, next) => {
  if (!WEBHOOK_SECRET) {
    await next();
    return;
  }
  const body = await c.req.text();
  const sig = c.req.header('X-GeneHub-Signature');
  if (!verifySignature(body, sig)) {
    throw new AppError(40100, 'webhook_signature_invalid', 'Webhook 签名验证失败', 401);
  }
  c.set('rawBody', body);
  await next();
});

type GeneCreatedPayload = {
  slug: string;
  name: string;
  version: string;
  manifest: Record<string, unknown>;
  source?: string;
  source_ref?: string;
  author?: { type: string; name: string; ref?: string };
};

webhooksRouter.post('/nodeskclaw/gene-created', async (c) => {
  const payload: GeneCreatedPayload = await c.req.json();

  if (!payload.slug || !payload.manifest) {
    throw AppError.manifestInvalid('slug and manifest are required');
  }

  try {
    const gene = await geneService.createGene(payload.manifest);

    if (payload.source) {
      await geneService.updateGene(gene.slug, {
        source: payload.source,
        source_ref: payload.source_ref,
      });
    }

    return success(c, { slug: gene.slug, version: gene.version, action: 'created' });
  } catch (err) {
    if (err instanceof AppError && err.errorCode === 'gene_slug_exists') {
      const gene = await geneService.publishVersion(
        payload.slug,
        payload.manifest,
        'Created via NoDeskClaw webhook',
      );
      return success(c, { slug: gene.slug, version: gene.version, action: 'version_published' });
    }
    throw err;
  }
});

type GenLearnedPayload = {
  slug: string;
  version: string;
  manifest: Record<string, unknown>;
  learning_output?: string;
  agent_self_eval?: number;
};

webhooksRouter.post('/nodeskclaw/gene-learned', async (c) => {
  const payload: GenLearnedPayload = await c.req.json();

  if (!payload.slug || !payload.manifest) {
    throw AppError.manifestInvalid('slug and manifest are required');
  }

  const gene = await geneService.publishVersion(
    payload.slug,
    payload.manifest,
    `Learned variant via NoDeskClaw (eval: ${payload.agent_self_eval ?? 'N/A'})`,
  );

  return success(c, { slug: gene.slug, version: gene.version, action: 'learned' });
});

type EffectivenessPayload = {
  reports: Array<{
    slug: string;
    metric_type: string;
    value: number;
  }>;
};

webhooksRouter.post('/nodeskclaw/effectiveness', async (c) => {
  const payload: EffectivenessPayload = await c.req.json();

  if (!payload.reports || !Array.isArray(payload.reports)) {
    throw AppError.manifestInvalid('reports array is required');
  }

  const results: Array<{ slug: string; status: string }> = [];

  for (const report of payload.reports) {
    try {
      await geneService.reportEffectiveness(report.slug, {
        metric_type: report.metric_type,
        value: report.value,
      });
      results.push({ slug: report.slug, status: 'ok' });
    } catch {
      results.push({ slug: report.slug, status: 'failed' });
    }
  }

  return success(c, { processed: results.length, results });
});
