import { createServer } from 'node:http';
import { Command } from 'commander';
import { loadConfig, saveConfig } from '../config.js';
import * as output from '../output.js';

export const authCommand = new Command('auth').description('认证管理');

authCommand
  .command('login')
  .description('通过 GitHub OAuth 登录并自动创建 API Key')
  .action(async () => {
    const config = await loadConfig();
    const registryUrl = config.registryUrl.replace(/\/$/, '');

    const port = await findAvailablePort(9876);
    const callbackUrl = `http://localhost:${port}/callback`;

    const tokenPromise = waitForCallback(port);

    const authUrl = `${registryUrl}/auth/github?cli_callback=${encodeURIComponent(callbackUrl)}`;
    output.info(`Opening browser for GitHub login...`);
    output.info(`  ${authUrl}`);

    const open = await import('open').catch(() => null);
    if (open) {
      await open.default(authUrl);
    } else {
      output.warn('Cannot open browser automatically. Please open the URL above manually.');
    }

    try {
      const { token, login } = await tokenPromise;
      await saveConfig({ token });
      output.ok(`Logged in as @${login}`);
      output.ok(`Token saved to config (${token.slice(0, 12)}****)`);
    } catch (err) {
      output.fail(err instanceof Error ? err.message : 'Login failed');
      process.exit(1);
    }
  });

authCommand
  .command('status')
  .description('查看当前登录状态')
  .action(async () => {
    const config = await loadConfig();

    if (!config.token) {
      output.info('Not logged in');
      output.info('  Run: genehub auth login');
      return;
    }

    output.ok(`Token: ${config.token.slice(0, 12)}****`);
    output.info(`Registry: ${config.registryUrl}`);
  });

authCommand
  .command('logout')
  .description('退出登录（清除本地 token）')
  .action(async () => {
    await saveConfig({ token: undefined });
    output.ok('Logged out. Token removed.');
  });

function findAvailablePort(preferred: number): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.listen(preferred, () => {
      server.close(() => resolve(preferred));
    });
    server.on('error', () => {
      const fallback = createServer();
      fallback.listen(0, () => {
        const addr = fallback.address();
        const port = typeof addr === 'object' && addr ? addr.port : 0;
        fallback.close(() => resolve(port));
      });
      fallback.on('error', reject);
    });
  });
}

function waitForCallback(port: number): Promise<{ token: string; login: string }> {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      server.close();
      reject(new Error('Login timeout (60s)'));
    }, 60_000);

    const server = createServer((req, res) => {
      if (!req.url?.startsWith('/callback')) {
        res.writeHead(404);
        res.end();
        return;
      }

      const url = new URL(req.url, `http://localhost:${port}`);
      const token = url.searchParams.get('token');
      const login = url.searchParams.get('login');

      if (!token) {
        res.writeHead(400, { 'Content-Type': 'text/html; charset=utf-8' });
        res.end('<h2>Login failed</h2><p>No token received.</p>');
        return;
      }

      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(`<h2>Login successful</h2><p>@${login ?? 'unknown'} - you can close this tab.</p>`);

      clearTimeout(timeout);
      server.close();
      resolve({ token, login: login ?? '' });
    });

    server.listen(port);
  });
}
