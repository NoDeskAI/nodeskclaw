import { homedir } from 'node:os';
import { join } from 'node:path';
import { detectAdapter, GeneHubClient, getAdapter, LearningEngine } from '@nodeskai/genehub-sdk';
import { Command } from 'commander';
import ora from 'ora';
import { loadConfig } from '../config.js';
import * as output from '../output.js';

function getWorkspaceDir(product: string): string {
  switch (product) {
    case 'openclaw':
      return join(homedir(), '.openclaw', 'workspace');
    case 'nanobot':
      return join(homedir(), '.nanobot', 'workspace');
    default:
      return join(process.cwd(), '.genehub');
  }
}

export const learnCommand = new Command('learn')
  .description('触发基因深度学习（L2）')
  .argument('<slug>', '基因标识符')
  .option('-p, --product <product>', '指定目标产品')
  .option('--check', '检查学习结果并应用')
  .action(async (slug: string, opts) => {
    const config = await loadConfig();
    const client = new GeneHubClient({ registryUrl: config.registryUrl, token: config.token });

    const adapter = opts.product ? getAdapter(opts.product) : await detectAdapter();

    const workspaceDir = getWorkspaceDir(adapter.product);
    const engine = new LearningEngine({ workspaceDir, adapter, client });

    if (opts.check) {
      const spinner = ora('检查学习结果...').start();
      const result = await engine.checkResult(slug);

      if (!result) {
        spinner.fail('未找到学习结果');
        output.info('Agent 还未完成该基因的学习任务');

        const pending = await engine.listPendingTasks();
        if (pending.length > 0) {
          output.info(`待完成的学习任务: ${pending.join(', ')}`);
        }
        return;
      }

      spinner.succeed(`学习结果: ${result.decision}`);

      if (result.self_eval !== undefined) {
        output.info(`自评分: ${result.self_eval}`);
      }
      if (result.reason) {
        output.info(`理由: ${result.reason}`);
      }

      if (result.decision === 'learned' && result.content) {
        const skillsDir = join(workspaceDir, 'skills');
        const applied = await engine.applyResult(slug, skillsDir);
        if (applied) {
          output.ok('已将个性化版本应用到技能目录');
        }
      }

      return;
    }

    const spinner = ora(`获取 ${slug} 的 manifest...`).start();

    try {
      const manifest = await client.getManifest(slug);
      spinner.succeed(`获取 ${manifest.name} v${manifest.version}`);

      if (!manifest.learning?.objectives?.length && !manifest.learning?.scenarios?.length) {
        output.warn('该基因没有定义学习目标或练习场景，将创建基础学习任务');
      }

      const learnSpinner = ora('生成学习任务...').start();
      const task = await engine.createLearningTask(manifest);
      learnSpinner.succeed('学习任务已创建');

      output.ok(`任务文件: ${join(workspaceDir, 'learning-tasks', `${slug}.md`)}`);
      output.info(`结果路径: ${task.callback_path}`);

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

      output.info('');
      output.info(`学习完成后运行: genehub learn --check ${slug}`);
    } catch (err) {
      spinner.fail('学习任务创建失败');
      output.fail(err instanceof Error ? err.message : String(err));
      process.exit(1);
    }
  });
