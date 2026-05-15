import { Command } from 'commander';
import { getConfigSource, loadConfig, saveConfig } from '../config.js';
import * as output from '../output.js';

export const configCommand = new Command('config').description('管理 GeneHub CLI 配置');

function sourceLabel(source: 'env' | 'file' | 'default'): string {
  if (source === 'env') return ' [env]';
  if (source === 'default') return ' [default]';
  return '';
}

configCommand
  .command('set <key> <value>')
  .description('设置配置项（registry / token）')
  .action(async (key: string, value: string) => {
    const validKeys = ['registry', 'token'] as const;
    if (!validKeys.includes(key as (typeof validKeys)[number])) {
      output.fail(`无效的配置项: ${key}，可选: ${validKeys.join(', ')}`);
      return;
    }

    if (key === 'registry') {
      await saveConfig({ registryUrl: value });
    } else if (key === 'token') {
      await saveConfig({ token: value });
    }

    output.ok(`${key} = ${key === 'token' ? `${value.slice(0, 8)}***` : value}`);
  });

configCommand
  .command('get [key]')
  .description('查看配置（支持 GENEHUB_REGISTRY_URL / GENEHUB_TOKEN 环境变量覆盖）')
  .action(async (key?: string) => {
    const config = await loadConfig();

    if (key) {
      const map: Record<string, string | undefined> = {
        registry: config.registryUrl,
        token: config.token ? `${config.token.slice(0, 8)}***` : undefined,
      };
      const src = sourceLabel(getConfigSource(key as 'registry' | 'token'));
      output.info(`${key} = ${map[key] ?? '(未设置)'}${src}`);
    } else {
      const regSrc = sourceLabel(getConfigSource('registry'));
      const tokSrc = sourceLabel(getConfigSource('token'));
      output.info(`registry = ${config.registryUrl}${regSrc}`);
      output.info(
        `token    = ${config.token ? `${config.token.slice(0, 8)}***` : '(未设置)'}${tokSrc}`,
      );
    }
  });
