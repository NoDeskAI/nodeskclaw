import { detectAdapter, getAdapter } from '@nodeskai/genehub-sdk';
import { Command } from 'commander';
import * as output from '../output.js';

export const listCommand = new Command('list')
  .description('列出当前环境已安装的基因')
  .option('-p, --product <product>', '指定目标产品')
  .option('--json', 'JSON 格式输出', false)
  .action(async (opts) => {
    try {
      const adapter = opts.product ? getAdapter(opts.product) : await detectAdapter();

      const genes = await adapter.list();

      if (opts.json) {
        console.log(JSON.stringify(genes, null, 2));
        return;
      }

      if (genes.length === 0) {
        output.info(`[${adapter.product}] 没有已安装的基因`);
        return;
      }

      output.info(`[${adapter.product}] 已安装 ${genes.length} 个基因:\n`);

      for (const gene of genes) {
        const date = new Date(gene.installedAt).toLocaleDateString('zh-CN');
        console.log(`  ${gene.slug.padEnd(24)} v${gene.version.padEnd(10)} ${date}`);
      }
    } catch (err) {
      output.fail(err instanceof Error ? err.message : String(err));
      process.exit(1);
    }
  });
