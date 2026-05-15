import { Hono } from 'hono';
import { success } from '../middleware/response.js';
import { resolve } from '../services/dependency-resolver.js';

export const resolveRouter = new Hono();

resolveRouter.post('/', async (c) => {
  const body = await c.req.json();
  const { slug, version, product } = body as {
    slug: string;
    version?: string;
    product?: string;
  };

  const result = await resolve(slug, version, product);
  return success(c, result);
});
