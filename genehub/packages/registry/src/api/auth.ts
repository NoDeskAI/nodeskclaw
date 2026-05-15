import { createHash, randomBytes } from 'node:crypto';
import { eq } from 'drizzle-orm';
import { Hono } from 'hono';
import { deleteCookie, getCookie, setCookie } from 'hono/cookie';
import { sign, verify } from 'hono/jwt';
import { db, schema } from '../db/index.js';
import { AppError } from '../middleware/error-handler.js';
import { success } from '../middleware/response.js';

const { publishers, apiKeys } = schema;

const GITHUB_CLIENT_ID = process.env.GITHUB_CLIENT_ID ?? '';
const GITHUB_CLIENT_SECRET = process.env.GITHUB_CLIENT_SECRET ?? '';
const JWT_SECRET = process.env.GENEHUB_JWT_SECRET ?? 'genehub-dev-jwt-secret';
const FRONTEND_URL = process.env.GENEHUB_FRONTEND_URL ?? 'http://localhost:5173';
const COOKIE_NAME = 'ghb_session';
const ADMIN_LOGINS = new Set(
  (process.env.GENEHUB_ADMIN_LOGINS ?? '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean),
);

export const authRouter = new Hono();

authRouter.get('/github', (c) => {
  if (!GITHUB_CLIENT_ID) throw AppError.internal('GITHUB_CLIENT_ID 未配置');

  const state = randomBytes(16).toString('hex');
  const callbackUrl = c.req.query('cli_callback');

  setCookie(c, 'oauth_state', state, { httpOnly: true, maxAge: 600, path: '/', sameSite: 'Lax' });
  if (callbackUrl) {
    setCookie(c, 'cli_callback', callbackUrl, {
      httpOnly: true,
      maxAge: 600,
      path: '/',
      sameSite: 'Lax',
    });
  }

  const params = new URLSearchParams({
    client_id: GITHUB_CLIENT_ID,
    scope: 'read:user',
    state,
  });

  return c.redirect(`https://github.com/login/oauth/authorize?${params}`);
});

authRouter.get('/github/callback', async (c) => {
  const code = c.req.query('code');

  // Already logged in (duplicate request / page refresh) — skip OAuth flow
  const existingSession = getCookie(c, COOKIE_NAME);
  if (!code && existingSession) {
    return c.redirect(FRONTEND_URL);
  }

  try {
    if (!code) {
      console.error('[OAuth] callback missing code param');
      return c.redirect(`${FRONTEND_URL}?auth_error=missing_code`);
    }

    const tokenRes = await fetch('https://github.com/login/oauth/access_token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({
        client_id: GITHUB_CLIENT_ID,
        client_secret: GITHUB_CLIENT_SECRET,
        code,
      }),
    });
    const tokenData = (await tokenRes.json()) as {
      access_token?: string;
      error?: string;
      error_description?: string;
    };
    if (!tokenData.access_token) {
      console.error(
        '[OAuth] GitHub token exchange failed:',
        tokenData.error,
        tokenData.error_description,
      );
      return c.redirect(`${FRONTEND_URL}?auth_error=${tokenData.error ?? 'token_exchange_failed'}`);
    }

    const userRes = await fetch('https://api.github.com/user', {
      headers: { Authorization: `Bearer ${tokenData.access_token}`, 'User-Agent': 'GeneHub' },
    });
    const ghUser = (await userRes.json()) as {
      id: number;
      login: string;
      name: string | null;
      avatar_url: string;
      html_url: string;
    };

    const existing = await db.select().from(publishers).where(eq(publishers.github_id, ghUser.id));

    let publisher: (typeof existing)[0];

    if (existing.length > 0) {
      const [updated] = await db
        .update(publishers)
        .set({
          github_login: ghUser.login,
          github_name: ghUser.name ?? ghUser.login,
          github_avatar_url: ghUser.avatar_url,
          github_profile_url: ghUser.html_url,
          last_login_at: new Date(),
        })
        .where(eq(publishers.github_id, ghUser.id))
        .returning();
      publisher = updated;
    } else {
      const [created] = await db
        .insert(publishers)
        .values({
          github_id: ghUser.id,
          github_login: ghUser.login,
          github_name: ghUser.name ?? ghUser.login,
          github_avatar_url: ghUser.avatar_url,
          github_profile_url: ghUser.html_url,
        })
        .returning();
      publisher = created;
    }

    const jwt = await sign(
      {
        sub: publisher.id,
        login: publisher.github_login,
        exp: Math.floor(Date.now() / 1000) + 7 * 24 * 3600,
      },
      JWT_SECRET,
    );

    const cliCallback = getCookie(c, 'cli_callback');
    deleteCookie(c, 'oauth_state');
    deleteCookie(c, 'cli_callback');

    if (cliCallback) {
      const token = generateApiKeyToken();
      const tokenHash = createHash('sha256').update(token).digest('hex');
      const tokenPrefix = token.slice(0, 12);

      await db.insert(apiKeys).values({
        publisher_id: publisher.id,
        token_prefix: tokenPrefix,
        token_hash: tokenHash,
        name: 'CLI (auto)',
      });

      const redirectUrl = new URL(cliCallback);
      redirectUrl.searchParams.set('token', token);
      redirectUrl.searchParams.set('login', publisher.github_login);
      return c.redirect(redirectUrl.toString());
    }

    setCookie(c, COOKIE_NAME, jwt, {
      httpOnly: true,
      maxAge: 7 * 24 * 3600,
      path: '/',
      sameSite: 'Lax',
    });

    return c.redirect(FRONTEND_URL);
  } catch (err) {
    console.error('[OAuth] callback error:', err);
    return c.redirect(`${FRONTEND_URL}?auth_error=internal`);
  }
});

authRouter.post('/logout', (c) => {
  deleteCookie(c, COOKIE_NAME);
  return success(c, { message: 'ok' });
});

authRouter.get('/me', async (c) => {
  const jwt = getCookie(c, COOKIE_NAME);
  if (!jwt) return success(c, null);

  try {
    const payload = await verify(jwt, JWT_SECRET, 'HS256');
    const publisherId = payload.sub as string;

    const result = await db.select().from(publishers).where(eq(publishers.id, publisherId));
    if (result.length === 0) return success(c, null);

    const p = result[0];
    const role = ADMIN_LOGINS.has(p.github_login) ? 'admin' : 'publisher';
    return success(c, {
      id: p.id,
      github_login: p.github_login,
      github_name: p.github_name,
      github_avatar_url: p.github_avatar_url,
      github_profile_url: p.github_profile_url,
      role,
    });
  } catch {
    deleteCookie(c, COOKIE_NAME);
    return success(c, null);
  }
});

function generateApiKeyToken(): string {
  return `ghb_${randomBytes(24).toString('base64url')}`;
}

export { JWT_SECRET, COOKIE_NAME };
