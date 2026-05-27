import { readdir, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, relative, resolve } from 'node:path';
import { detectAdapter, GeneHubClient, getAdapter } from '@nodeskai/genehub-sdk';
import type { InstallResult } from '@nodeskai/genehub-types';
import { Command } from 'commander';
import ora from 'ora';
import { parse } from 'yaml';
import { loadConfig } from '../config.js';
import * as output from '../output.js';

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

async function extractTarGz(buffer: ArrayBuffer, destDir: string): Promise<void> {
  const { mkdir } = await import('node:fs/promises');
  await mkdir(destDir, { recursive: true });
  const { extract } = await import('tar');
  const tarPath = join(tmpdir(), `genehub-genome-${Date.now()}.tar.gz`);
  await writeFile(tarPath, Buffer.from(buffer));
  try {
    await extract({ file: tarPath, cwd: destDir, strip: 1 });
  } finally {
    await rm(tarPath, { force: true });
  }
}

type GenomeYaml = {
  name: string;
  slug: string;
  version: string;
  description?: string;
  short_description?: string;
  category?: string;
  tags?: string[];
  icon?: string;
  genes: { slug: string; version: string; config_override?: Record<string, unknown> }[];
  compatibility?: string[];
  author?: { type: string; id?: string; name: string };
};

const publishGenomeCommand = new Command('publish')
  .description('发布基因组到 GeneHub Registry')
  .argument('<path>', '基因组目录路径（包含 genome.yaml）')
  .action(async (dirPath: string) => {
    const config = await loadConfig();

    if (!config.token) {
      output.fail('未配置认证 token');
      process.exit(1);
    }

    const client = new GeneHubClient({ registryUrl: config.registryUrl, token: config.token });
    const absPath = resolve(dirPath);

    try {
      const yamlPath = join(absPath, 'genome.yaml');
      const raw = await readFile(yamlPath, 'utf-8');
      const parsed = parse(raw) as GenomeYaml;

      if (!parsed.name || !parsed.slug || !parsed.version || !parsed.genes?.length) {
        output.fail('genome.yaml 缺少必填字段: name, slug, version, genes');
        process.exit(1);
      }

      const scanSpinner = ora('扫描基因组目录...').start();
      const files = await scanDirectory(absPath);
      const fileCount = Object.keys(files).length;
      scanSpinner.succeed(`扫描完成: ${fileCount} 个文件`);

      const spinner = ora(`发布基因组 ${parsed.slug}@${parsed.version}...`).start();

      try {
        const genome = await client.publishGenome(parsed, files);
        spinner.succeed('发布成功');
        output.ok(
          `${genome.slug}@${genome.version} 已发布到 GeneHub Registry (${fileCount} 个文件)`,
        );
      } catch (err) {
        const isSlugExists = err instanceof Error && err.message.includes('genome_slug_exists');
        if (!isSlugExists) throw err;

        spinner.text = `基因组 ${parsed.slug} 已存在，发布新版本 ${parsed.version}...`;
        const genome = await client.publishGenomeVersion(
          parsed.slug,
          { version: parsed.version, genes: parsed.genes, files },
          files,
        );
        spinner.succeed('发布成功');
        output.ok(`${genome.slug}@${genome.version} 新版本已发布 (${fileCount} 个文件)`);
      }
    } catch (err) {
      output.fail(err instanceof Error ? err.message : String(err));
      process.exit(1);
    }
  });

const installGenomeCommand = new Command('install')
  .description('安装基因组（递归安装所有引用的基因）')
  .argument('<slug>', '基因组标识符（支持 slug@version 格式）')
  .option('-p, --product <product>', '指定目标产品')
  .option('-f, --force', '强制覆盖已安装基因', false)
  .option('--target <path>', '指定安装目标路径')
  .action(async (rawSlug: string, opts) => {
    const config = await loadConfig();
    const client = new GeneHubClient({ registryUrl: config.registryUrl, token: config.token });

    const atIdx = rawSlug.lastIndexOf('@');
    const slug = atIdx > 0 ? rawSlug.slice(0, atIdx) : rawSlug;
    const version = atIdx > 0 ? rawSlug.slice(atIdx + 1) : undefined;

    const spinner = ora(`获取基因组 ${slug}...`).start();

    try {
      const genome = await client.getGenome(slug);
      spinner.succeed(`基因组: ${genome.name} v${genome.version} (${genome.genes.length} 个基因)`);

      const adapter = opts.product ? getAdapter(opts.product) : await detectAdapter();
      output.info(`目标产品: ${adapter.product}`);

      const resolveSpinner = ora('解析基因依赖...').start();
      const resolved = await client.resolveGenome(slug, version);
      resolveSpinner.succeed(`解析完成: ${resolved.genes.length} 个基因（含依赖）`);

      if (resolved.warnings.length > 0) {
        for (const w of resolved.warnings) output.warn(w);
      }
      if (resolved.conflicts.length > 0) {
        for (const c of resolved.conflicts) output.warn(`冲突: ${c}`);
      }

      let installed = 0;
      let skipped = 0;

      for (const gene of resolved.genes) {
        if (!opts.force && (await adapter.isInstalled(gene.slug))) {
          skipped++;
          continue;
        }

        const geneSpinner = ora(`  安装 ${gene.slug}@${gene.version}...`).start();

        try {
          const manifest = await client.getManifest(gene.slug, gene.version);
          let result: InstallResult | undefined;

          try {
            const archive = await client.downloadArchive(gene.slug, gene.version);
            const tempDir = join(tmpdir(), `genehub-install-${gene.slug}-${Date.now()}`);
            await extractTarGz(archive, tempDir);

            if (adapter.installFromDirectory) {
              result = await adapter.installFromDirectory(tempDir, manifest, {
                force: opts.force,
                targetPath: opts.target,
              });
            } else {
              result = await adapter.install(manifest, {
                force: opts.force,
                targetPath: opts.target,
              });
            }

            await rm(tempDir, { recursive: true, force: true });
          } catch {
            result = await adapter.install(manifest, {
              force: opts.force,
              targetPath: opts.target,
            });
          }

          geneSpinner.succeed(`  ${result.slug}@${result.version}`);
          installed++;

          try {
            await client.reportInstall(gene.slug);
          } catch {
            // non-critical
          }
        } catch (err) {
          geneSpinner.fail(
            `  ${gene.slug} 安装失败: ${err instanceof Error ? err.message : String(err)}`,
          );
        }
      }

      output.ok(`基因组安装完成: ${installed} 安装, ${skipped} 跳过`);

      try {
        await client.reportGenomeInstall(slug);
      } catch {
        // non-critical
      }
    } catch (err) {
      spinner.fail('安装失败');
      output.fail(err instanceof Error ? err.message : String(err));
      process.exit(1);
    }
  });

const infoGenomeCommand = new Command('info')
  .description('查看基因组详情')
  .argument('<slug>', '基因组标识符')
  .option('--json', 'JSON 格式输出', false)
  .action(async (slug: string, opts) => {
    const config = await loadConfig();
    const client = new GeneHubClient({ registryUrl: config.registryUrl, token: config.token });

    try {
      const genome = await client.getGenome(slug);

      if (opts.json) {
        console.log(JSON.stringify(genome, null, 2));
        return;
      }

      output.info(`名称: ${genome.name}`);
      output.info(`Slug: ${genome.slug}`);
      output.info(`版本: ${genome.version}`);
      output.info(`分类: ${genome.category}`);
      output.info(`描述: ${genome.description || genome.short_description || '(无)'}`);
      output.info(`安装数: ${genome.install_count}`);

      if (genome.genes.length > 0) {
        output.info(`\n基因列表 (${genome.genes.length}个):`);
        output.table(
          ['slug', '版本'],
          genome.genes.map((g) => [g.slug, g.version]),
        );
      }
    } catch (err) {
      output.fail(err instanceof Error ? err.message : String(err));
      process.exit(1);
    }
  });

const listGenomeCommand = new Command('list')
  .description('搜索基因组')
  .option('-q, --query <keyword>', '搜索关键词')
  .option('-c, --category <category>', '按分类过滤')
  .option('--json', 'JSON 格式输出', false)
  .action(async (opts) => {
    const config = await loadConfig();
    const client = new GeneHubClient({ registryUrl: config.registryUrl, token: config.token });

    try {
      const result = await client.searchGenomes({
        q: opts.query,
        category: opts.category,
      });

      if (opts.json) {
        console.log(JSON.stringify(result, null, 2));
        return;
      }

      if (result.items.length === 0) {
        output.info('未找到基因组');
        return;
      }

      output.table(
        ['slug', '名称', '版本', '分类', '基因数', '安装数'],
        result.items.map((g) => [
          g.slug,
          g.name,
          g.version,
          g.category,
          String(g.genes.length),
          String(g.install_count),
        ]),
      );

      output.info(`共 ${result.total} 条结果`);
    } catch (err) {
      output.fail(err instanceof Error ? err.message : String(err));
      process.exit(1);
    }
  });

export const genomeCommand = new Command('genome').description('基因组管理');

genomeCommand.addCommand(publishGenomeCommand);
genomeCommand.addCommand(installGenomeCommand);
genomeCommand.addCommand(infoGenomeCommand);
genomeCommand.addCommand(listGenomeCommand);
