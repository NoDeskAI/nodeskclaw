import { GeneHubClient } from '@nodeskai/genehub-sdk';
import type { Gene } from '@nodeskai/genehub-types';
import { Command } from 'commander';
import { loadConfig } from '../config.js';
import * as output from '../output.js';

function formatAuthor(gene: Gene): string {
  const a = gene.author;
  if (!a) return '-';
  if (a.ref) return `${a.name} (${a.ref})`;
  return `${a.name} (${a.type})`;
}

function formatGene(gene: Gene): void {
  console.log(`  ${gene.slug} v${gene.version}`);
  console.log(`  ${gene.short_description || gene.description || ''}`);
  console.log('');
  console.log(`  Category:  ${gene.category}`);
  console.log(`  Tags:      ${gene.tags?.join(', ') || '(none)'}`);
  console.log(`  Author:    ${formatAuthor(gene)}`);
  console.log(`  Status:    ${gene.is_published ? 'published' : 'unpublished'}`);
  console.log(`  Downloads: ${gene.install_count}`);
  console.log('');
  console.log('  Compatibility:');
  if (gene.compatibility?.length) {
    for (const c of gene.compatibility) {
      console.log(`    - ${c}`);
    }
  } else {
    console.log('    (none)');
  }
  console.log('');
  console.log(
    '  Dependencies:',
    gene.dependencies?.length
      ? gene.dependencies.map((d) => `${d.slug}@${d.version}`).join(', ')
      : '(none)',
  );
  console.log('');
  console.log('  Install:');
  console.log(`    genehub install ${gene.slug}`);
}

export const infoCommand = new Command('info')
  .description('查看基因详情')
  .argument('<slug>', '基因 slug')
  .option('--json', 'JSON 格式输出', false)
  .action(async (slug: string, opts: { json?: boolean }) => {
    const config = await loadConfig();
    const client = new GeneHubClient({ registryUrl: config.registryUrl, token: config.token });

    try {
      const gene = await client.getGene(slug);

      if (opts.json) {
        console.log(JSON.stringify(gene, null, 2));
        return;
      }

      formatGene(gene);
    } catch (err) {
      output.fail(err instanceof Error ? err.message : String(err));
      process.exit(1);
    }
  });
