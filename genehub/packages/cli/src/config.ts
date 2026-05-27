import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { homedir } from 'node:os';
import { join } from 'node:path';

const CONFIG_DIR = join(homedir(), '.genehub');
const CONFIG_PATH = join(CONFIG_DIR, 'config.json');

export type CliConfig = {
  registryUrl: string;
  token?: string;
};

const DEFAULT_CONFIG: CliConfig = {
  registryUrl: 'https://genehub.nodeskai.com',
};

/**
 * Priority: env vars > config file > defaults
 *
 * - GENEHUB_REGISTRY_URL / GENEHUB_REGISTRY
 * - GENEHUB_TOKEN
 */
export async function loadConfig(): Promise<CliConfig> {
  let fileConfig: Partial<CliConfig> = {};
  try {
    const raw = await readFile(CONFIG_PATH, 'utf-8');
    fileConfig = JSON.parse(raw);
  } catch {
    // no config file, use defaults
  }

  const merged = { ...DEFAULT_CONFIG, ...fileConfig };

  const envUrl = process.env.GENEHUB_REGISTRY_URL ?? process.env.GENEHUB_REGISTRY;
  if (envUrl) {
    merged.registryUrl = envUrl;
  }

  const envToken = process.env.GENEHUB_TOKEN;
  if (envToken) {
    merged.token = envToken;
  }

  return merged;
}

export function getConfigSource(key: 'registry' | 'token'): 'env' | 'file' | 'default' {
  if (key === 'registry') {
    if (process.env.GENEHUB_REGISTRY_URL || process.env.GENEHUB_REGISTRY) return 'env';
  }
  if (key === 'token') {
    if (process.env.GENEHUB_TOKEN) return 'env';
  }
  return 'file';
}

export async function saveConfig(config: Partial<CliConfig>): Promise<void> {
  const current = await loadConfig();
  const merged = { ...current, ...config };
  await mkdir(CONFIG_DIR, { recursive: true });
  await writeFile(CONFIG_PATH, JSON.stringify(merged, null, 2), 'utf-8');
}
