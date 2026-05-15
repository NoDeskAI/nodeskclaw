import { detectAdapter, getAdapter } from '@nodeskai/genehub-sdk';
import { Command } from 'commander';
import ora from 'ora';
import * as output from '../output.js';

export const uninstallCommand = new Command('uninstall')
  .description('从当前 Agent 环境卸载基因')
  .argument('<slug>', '基因标识符')
  .option('-p, --product <product>', '指定目标产品（openclaw / nanobot / generic）')
  .action(async (slug: string, opts) => {
    const adapter = opts.product ? getAdapter(opts.product) : await detectAdapter();

    output.info(`目标产品: ${adapter.product}`);

    if (!(await adapter.isInstalled(slug))) {
      output.warn(`${slug} 未安装`);
      return;
    }

    const spinner = ora('卸载中...').start();

    try {
      const result = await adapter.uninstall(slug);
      spinner.succeed('卸载完成');

      output.ok(`${result.slug} 已卸载`);
      output.info(`清理文件: ${result.files.join(', ')}`);

      if (result.needsRestart) {
        output.warn('需要重启 Agent Host 使变更生效');
      }
    } catch (err) {
      spinner.fail('卸载失败');
      output.fail(err instanceof Error ? err.message : String(err));
      process.exit(1);
    }
  });
