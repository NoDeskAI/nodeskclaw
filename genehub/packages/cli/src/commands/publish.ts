import { access, readdir, readFile, stat, writeFile } from 'node:fs/promises';
import { basename, dirname, join, relative, resolve } from 'node:path';
import { GeneHubClient } from '@nodeskai/genehub-sdk';
import type { Gene } from '@nodeskai/genehub-types';
import { GeneManifestSchema } from '@nodeskai/genehub-types';
import { Command } from 'commander';
import ora from 'ora';
import { parse, stringify } from 'yaml';
import { loadConfig } from '../config.js';
import * as output from '../output.js';
import { detectSkillFile, getFormatLabel } from '../utils/detect-skill.js';
import {
  buildManifestInteractively,
  confirmPublish,
  confirmSaveManifest,
} from '../utils/interactive-manifest.js';

const IGNORED_PATTERNS = ['.git', 'node_modules', '.DS_Store', '__pycache__', '.venv'];

async function scanDirectory(dirPath: string): Promise<Record<string, string>> {
  const files: Record<string, string> = {};

  async function walk(currentPath: string) {
    const entries = await readdir(currentPath, { withFileTypes: true });
    for (const entry of entries) {
      if (IGNORED_PATTERNS.includes(entry.name)) continue;
      const fullPath = join(currentPath, entry.name);
      if (entry.isDirectory()) {
        await walk(fullPath);
      } else if (entry.isFile()) {
        const relPath = relative(dirPath, fullPath);
        const content = await readFile(fullPath, 'utf-8');
        files[relPath] = content;
      }
    }
  }

  await walk(dirPath);
  return files;
}

async function fileExists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

export const publishCommand = new Command('publish')
  .description('发布基因到 GeneHub Registry (支持目录路径或 gene.yaml 文件路径)')
  .argument('<path>', '基因目录路径或 gene.yaml 文件路径')
  .option('-y, --yes', '非交互模式，使用默认值')
  .action(async (inputPath: string, opts: { yes?: boolean }) => {
    const config = await loadConfig();

    if (!config.token) {
      output.fail('未配置认证 token');
      output.info('  方式 1: genehub config set token <token>');
      output.info('  方式 2: export GENEHUB_TOKEN=<token>');
      process.exit(1);
    }

    const client = new GeneHubClient({ registryUrl: config.registryUrl, token: config.token });
    const resolved = resolve(inputPath);

    let absPath: string;
    let yamlPath: string;
    let hasGeneYaml: boolean;

    try {
      const info = await stat(resolved);
      if (info.isFile() && basename(resolved).endsWith('.yaml')) {
        yamlPath = resolved;
        absPath = dirname(resolved);
        hasGeneYaml = true;
      } else if (info.isDirectory()) {
        absPath = resolved;
        yamlPath = join(absPath, 'gene.yaml');
        hasGeneYaml = await fileExists(yamlPath);
      } else {
        output.fail(`路径不是目录也不是 YAML 文件: ${inputPath}`);
        process.exit(1);
      }
    } catch {
      output.fail(`路径不存在: ${inputPath}`);
      process.exit(1);
    }

    try {
      let parsed: Record<string, unknown>;

      if (hasGeneYaml) {
        parsed = await loadFromGeneYaml(absPath, yamlPath);
      } else {
        parsed = await autoDetectAndBuild(absPath, yamlPath, opts.yes);
      }

      const validation = GeneManifestSchema.safeParse(parsed);
      if (!validation.success) {
        output.fail('Manifest 校验失败:');
        for (const issue of validation.error.issues) {
          output.fail(`  ${issue.path.join('.')}: ${issue.message}`);
        }
        process.exit(1);
      }

      const { slug, version } = validation.data;

      if (!hasGeneYaml && !opts.yes) {
        const shouldPublish = await confirmPublish(slug, version);
        if (!shouldPublish) {
          output.info('已取消发布');
          process.exit(0);
        }
      }

      const scanSpinner = ora('扫描基因目录...').start();
      const files = await scanDirectory(absPath);
      const fileCount = Object.keys(files).length;
      scanSpinner.succeed(`扫描完成: ${fileCount} 个文件`);

      const spinner = ora(`发布 ${slug}@${version} (${fileCount} 个文件)...`).start();

      let gene: Gene;
      try {
        gene = await client.publishGene(validation.data, files);
      } catch (err) {
        const isSlugExists = err instanceof Error && err.message.includes('gene_slug_exists');
        if (!isSlugExists) throw err;

        spinner.text = `基因 ${slug} 已存在，发布新版本 ${version}...`;
        gene = await client.publishVersion(slug, validation.data, undefined, files);
      }

      spinner.succeed('发布成功');
      output.ok(`${gene.slug}@${gene.version} 已发布到 GeneHub Registry (${fileCount} 个文件)`);
    } catch (err) {
      output.fail(err instanceof Error ? err.message : String(err));
      process.exit(1);
    }
  });

async function loadFromGeneYaml(
  absPath: string,
  yamlPath: string,
): Promise<Record<string, unknown>> {
  const raw = await readFile(yamlPath, 'utf-8');
  const parsed = parse(raw);

  if (!parsed.skill?.content) {
    if (!parsed.skill) parsed.skill = {};
    const candidates: string[] = [];
    if (parsed.skill.file) {
      candidates.push(join(absPath, parsed.skill.file));
    }
    candidates.push(join(absPath, 'SKILL.md'));
    candidates.push(join(absPath, 'CLAUDE.md'));
    candidates.push(join(absPath, 'AGENTS.md'));

    for (const candidate of candidates) {
      try {
        parsed.skill.content = await readFile(candidate, 'utf-8');
        break;
      } catch {
        // try next candidate
      }
    }
  }

  return parsed;
}

async function autoDetectAndBuild(
  absPath: string,
  yamlPath: string,
  isNonInteractive = false,
): Promise<Record<string, unknown>> {
  output.info('未找到 gene.yaml，尝试自动检测 skill 文件...');

  const detected = await detectSkillFile(absPath);
  if (!detected) {
    output.fail('目录中未找到任何可识别的 skill 文件');
    output.info('  支持的格式: CLAUDE.md, SKILL.md, AGENTS.md, .cursorrules, .clinerules, *.md');
    output.info('  或使用 genehub init 创建标准模板');
    process.exit(1);
  }

  output.ok(`检测到: ${detected.fileName} (${getFormatLabel(detected.format)})`);
  output.info('自动推断基因元数据，请确认或修改:');
  console.log();

  const manifest = await buildManifestInteractively(detected, isNonInteractive);
  console.log();

  const shouldSave = isNonInteractive || (await confirmSaveManifest());
  if (shouldSave) {
    const yamlManifest = { ...manifest } as Record<string, unknown>;
    if (yamlManifest.skill && typeof yamlManifest.skill === 'object') {
      const s = { ...(yamlManifest.skill as Record<string, unknown>) };
      delete s.content;
      yamlManifest.skill = s;
    }
    await writeFile(yamlPath, stringify(yamlManifest), 'utf-8');
    output.ok('gene.yaml 已保存');
  }

  return manifest as unknown as Record<string, unknown>;
}
