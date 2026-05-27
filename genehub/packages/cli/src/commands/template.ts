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
  const tarPath = join(tmpdir(), `genehub-template-${Date.now()}.tar.gz`);
  await writeFile(tarPath, Buffer.from(buffer));
  try {
    await extract({ file: tarPath, cwd: destDir, strip: 1 });
  } finally {
    await rm(tarPath, { force: true });
  }
}

type TemplateYaml = {
  name: string;
  slug: string;
  version: string;
  description?: string;
  short_description?: string;
  role?: string;
  category?: string;
  tags?: string[];
  icon?: string;
  avatar_url?: string;
  genomes: { slug: string; version: string }[];
  genes?: { slug: string; version: string }[];
  compatibility?: string[];
  author?: { type: string; id?: string; name: string };
};

const publishTemplateCommand = new Command('publish')
  .description('发布 AI 员工模板到 GeneHub Registry')
  .argument('<path>', '模板目录路径（包含 template.yaml）')
  .action(async (dirPath: string) => {
    const config = await loadConfig();

    if (!config.token) {
      output.fail('未配置认证 token');
      process.exit(1);
    }

    const client = new GeneHubClient({ registryUrl: config.registryUrl, token: config.token });
    const absPath = resolve(dirPath);

    try {
      const yamlPath = join(absPath, 'template.yaml');
      const raw = await readFile(yamlPath, 'utf-8');
      const parsed = parse(raw) as TemplateYaml;

      if (!parsed.name || !parsed.slug || !parsed.version) {
        output.fail('template.yaml 缺少必填字段: name, slug, version');
        process.exit(1);
      }
      if (!parsed.genomes?.length && !parsed.genes?.length) {
        output.fail('template.yaml 至少需要引用一个 genome 或 gene');
        process.exit(1);
      }

      const scanSpinner = ora('扫描模板目录...').start();
      const files = await scanDirectory(absPath);
      const fileCount = Object.keys(files).length;
      scanSpinner.succeed(`扫描完成: ${fileCount} 个文件`);

      const spinner = ora(`发布模板 ${parsed.slug}@${parsed.version}...`).start();

      try {
        const template = await client.publishTemplate(parsed, files);
        spinner.succeed('发布成功');
        output.ok(
          `${template.slug}@${template.version} 已发布到 GeneHub Registry (${fileCount} 个文件)`,
        );
      } catch (err) {
        const isSlugExists = err instanceof Error && err.message.includes('template_slug_exists');
        if (!isSlugExists) throw err;

        spinner.text = `模板 ${parsed.slug} 已存在，发布新版本 ${parsed.version}...`;
        const template = await client.publishTemplateVersion(
          parsed.slug,
          {
            version: parsed.version,
            genomes: parsed.genomes ?? [],
            genes: parsed.genes,
            files,
          },
          files,
        );
        spinner.succeed('发布成功');
        output.ok(`${template.slug}@${template.version} 新版本已发布 (${fileCount} 个文件)`);
      }
    } catch (err) {
      output.fail(err instanceof Error ? err.message : String(err));
      process.exit(1);
    }
  });

const installTemplateCommand = new Command('install')
  .description('安装 AI 员工模板（递归安装所有基因组和基因）')
  .argument('<slug>', '模板标识符（支持 slug@version 格式）')
  .option('-p, --product <product>', '指定目标产品')
  .option('-f, --force', '强制覆盖已安装基因', false)
  .option('--target <path>', '指定安装目标路径')
  .action(async (rawSlug: string, opts) => {
    const config = await loadConfig();
    const client = new GeneHubClient({ registryUrl: config.registryUrl, token: config.token });

    const atIdx = rawSlug.lastIndexOf('@');
    const slug = atIdx > 0 ? rawSlug.slice(0, atIdx) : rawSlug;

    const spinner = ora(`获取模板 ${slug}...`).start();

    try {
      const template = await client.getTemplate(slug);
      spinner.succeed(
        `模板: ${template.name} v${template.version} (${template.genomes.length} 基因组, ${template.genes.length} 额外基因)`,
      );

      const adapter = opts.product ? getAdapter(opts.product) : await detectAdapter();
      output.info(`目标产品: ${adapter.product}`);

      const allGeneSlugs = new Set<string>();
      let installed = 0;
      let skipped = 0;

      for (const genomeRef of template.genomes) {
        output.info(`\n解析基因组: ${genomeRef.slug}@${genomeRef.version}`);
        try {
          const resolved = await client.resolveGenome(genomeRef.slug, genomeRef.version);

          if (resolved.warnings.length > 0) {
            for (const w of resolved.warnings) output.warn(w);
          }

          for (const gene of resolved.genes) {
            if (allGeneSlugs.has(gene.slug)) continue;
            allGeneSlugs.add(gene.slug);

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
        } catch (err) {
          output.warn(
            `基因组 ${genomeRef.slug} 解析失败: ${err instanceof Error ? err.message : String(err)}`,
          );
        }
      }

      if (template.genes.length > 0) {
        output.info(`\n安装额外基因 (${template.genes.length}个):`);
        for (const geneRef of template.genes) {
          if (allGeneSlugs.has(geneRef.slug)) continue;
          allGeneSlugs.add(geneRef.slug);

          if (!opts.force && (await adapter.isInstalled(geneRef.slug))) {
            skipped++;
            continue;
          }

          const geneSpinner = ora(`  安装 ${geneRef.slug}@${geneRef.version}...`).start();
          try {
            const manifest = await client.getManifest(geneRef.slug, geneRef.version);
            let result: InstallResult | undefined;

            try {
              const archive = await client.downloadArchive(geneRef.slug, geneRef.version);
              const tempDir = join(tmpdir(), `genehub-install-${geneRef.slug}-${Date.now()}`);
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
              await client.reportInstall(geneRef.slug);
            } catch {
              // non-critical
            }
          } catch (err) {
            geneSpinner.fail(
              `  ${geneRef.slug} 安装失败: ${err instanceof Error ? err.message : String(err)}`,
            );
          }
        }
      }

      output.ok(`模板安装完成: ${installed} 安装, ${skipped} 跳过`);

      try {
        await client.reportTemplateInstall(slug);
      } catch {
        // non-critical
      }
    } catch (err) {
      spinner.fail('安装失败');
      output.fail(err instanceof Error ? err.message : String(err));
      process.exit(1);
    }
  });

const infoTemplateCommand = new Command('info')
  .description('查看 AI 员工模板详情')
  .argument('<slug>', '模板标识符')
  .option('--json', 'JSON 格式输出', false)
  .action(async (slug: string, opts) => {
    const config = await loadConfig();
    const client = new GeneHubClient({ registryUrl: config.registryUrl, token: config.token });

    try {
      const template = await client.getTemplate(slug);

      if (opts.json) {
        console.log(JSON.stringify(template, null, 2));
        return;
      }

      output.info(`名称: ${template.name}`);
      output.info(`Slug: ${template.slug}`);
      output.info(`版本: ${template.version}`);
      output.info(`角色: ${template.role ?? '(无)'}`);
      output.info(`分类: ${template.category}`);
      output.info(`描述: ${template.description || template.short_description || '(无)'}`);
      output.info(`安装数: ${template.install_count}`);

      if (template.genomes.length > 0) {
        output.info(`\n基因组 (${template.genomes.length}个):`);
        output.table(
          ['slug', '版本'],
          template.genomes.map((g) => [g.slug, g.version]),
        );
      }

      if (template.genes.length > 0) {
        output.info(`\n额外基因 (${template.genes.length}个):`);
        output.table(
          ['slug', '版本'],
          template.genes.map((g) => [g.slug, g.version]),
        );
      }
    } catch (err) {
      output.fail(err instanceof Error ? err.message : String(err));
      process.exit(1);
    }
  });

const listTemplateCommand = new Command('list')
  .description('搜索 AI 员工模板')
  .option('-q, --query <keyword>', '搜索关键词')
  .option('-c, --category <category>', '按分类过滤')
  .option('-r, --role <role>', '按角色过滤')
  .option('--json', 'JSON 格式输出', false)
  .action(async (opts) => {
    const config = await loadConfig();
    const client = new GeneHubClient({ registryUrl: config.registryUrl, token: config.token });

    try {
      const result = await client.searchTemplates({
        q: opts.query,
        category: opts.category,
        role: opts.role,
      });

      if (opts.json) {
        console.log(JSON.stringify(result, null, 2));
        return;
      }

      if (result.items.length === 0) {
        output.info('未找到模板');
        return;
      }

      output.table(
        ['slug', '名称', '版本', '角色', '基因组', '安装数'],
        result.items.map((t) => [
          t.slug,
          t.name,
          t.version,
          t.role ?? '-',
          String(t.genomes.length),
          String(t.install_count),
        ]),
      );

      output.info(`共 ${result.total} 条结果`);
    } catch (err) {
      output.fail(err instanceof Error ? err.message : String(err));
      process.exit(1);
    }
  });

export const templateCommand = new Command('template').description('AI 员工模板管理');

templateCommand.addCommand(publishTemplateCommand);
templateCommand.addCommand(installTemplateCommand);
templateCommand.addCommand(infoTemplateCommand);
templateCommand.addCommand(listTemplateCommand);
