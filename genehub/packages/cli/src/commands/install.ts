import { mkdir, rm, writeFile } from 'node:fs/promises';
import { homedir, tmpdir } from 'node:os';
import { join } from 'node:path';
import { detectAdapter, GeneHubClient, getAdapter, LearningEngine } from '@nodeskai/genehub-sdk';
import type { InstallResult } from '@nodeskai/genehub-types';
import { Command } from 'commander';
import ora from 'ora';
import { loadConfig } from '../config.js';
import * as output from '../output.js';

function parseSlugVersion(input: string): { slug: string; version?: string } {
  const atIdx = input.lastIndexOf('@');
  if (atIdx > 0) {
    return { slug: input.slice(0, atIdx), version: input.slice(atIdx + 1) };
  }
  return { slug: input };
}

async function extractTarGz(buffer: ArrayBuffer, destDir: string): Promise<void> {
  await mkdir(destDir, { recursive: true });
  const { extract } = await import('tar');
  const tarPath = join(tmpdir(), `genehub-${Date.now()}.tar.gz`);
  await writeFile(tarPath, Buffer.from(buffer));
  try {
    await extract({ file: tarPath, cwd: destDir, strip: 1 });
  } finally {
    await rm(tarPath, { force: true });
  }
}

export const installCommand = new Command('install')
  .description('安装基因到当前 Agent 环境')
  .argument('<slug>', '基因标识符（支持 slug@version 格式）')
  .option('-p, --product <product>', '指定目标产品（openclaw / nanobot / generic）')
  .option('-f, --force', '强制覆盖已安装版本', false)
  .option('--target <path>', '指定安装目标路径')
  .option('--learn', '安装后自动触发深度学习', false)
  .action(async (rawSlug: string, opts) => {
    const config = await loadConfig();
    const client = new GeneHubClient({ registryUrl: config.registryUrl, token: config.token });

    const { slug, version } = parseSlugVersion(rawSlug);
    const spinner = ora(`获取基因 ${slug}${version ? `@${version}` : ''} 的 manifest...`).start();

    try {
      const manifest = await client.getManifest(slug, version);
      spinner.succeed(`获取 ${manifest.name} v${manifest.version}`);

      const adapter = opts.product ? getAdapter(opts.product) : await detectAdapter();

      output.info(`目标产品: ${adapter.product}`);

      if (!opts.force && (await adapter.isInstalled(slug))) {
        const installedVer = await adapter.getInstalledVersion(slug);
        output.warn(`${slug}${installedVer ? ` v${installedVer}` : ''} 已安装，使用 --force 覆盖`);
        return;
      }

      const installSpinner = ora('安装中...').start();

      let result: InstallResult | undefined;
      let isMultiFile = false;

      try {
        const archive = await client.downloadArchive(slug, version);
        const tempDir = join(tmpdir(), `genehub-install-${slug}-${Date.now()}`);
        await extractTarGz(archive, tempDir);
        isMultiFile = true;

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

      installSpinner.succeed(isMultiFile ? '安装完成（多文件基因）' : '安装完成');

      output.ok(`${result.slug}@${result.version} 安装成功`);
      output.info(`文件: ${result.files.join(', ')}`);

      if (result.needsRestart) {
        output.warn('需要重启 Agent Host 使基因生效');
      }

      if (result.dependencies.length > 0) {
        output.info(`依赖基因: ${result.dependencies.join(', ')}`);
      }

      try {
        await client.reportInstall(slug);
      } catch {
        // non-critical
      }

      if (opts.learn) {
        const workspaceDir =
          adapter.product === 'openclaw'
            ? join(homedir(), '.openclaw', 'workspace')
            : adapter.product === 'nanobot'
              ? join(homedir(), '.nanobot', 'workspace')
              : join(process.cwd(), '.genehub');

        const engine = new LearningEngine({ workspaceDir, adapter, client });
        const learnSpinner = ora('生成学习任务...').start();
        await engine.createLearningTask(manifest);
        learnSpinner.succeed('学习任务已创建');

        if (adapter.triggerLearning) {
          const triggerSpinner = ora('触发 bot 学习...').start();
          try {
            await adapter.triggerLearning('检查 learning-tasks/ 目录并处理学习任务');
            triggerSpinner.succeed('已触发 bot 学习（后台处理中）');
          } catch {
            triggerSpinner.warn('自动触发失败，Agent 将在下次对话中处理');
          }
        } else {
          output.info('Agent 将在下次对话中处理学习任务');
        }
      }
    } catch (err) {
      spinner.fail('安装失败');
      output.fail(err instanceof Error ? err.message : String(err));
      process.exit(1);
    }
  });
