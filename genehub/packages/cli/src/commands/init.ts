import { mkdir, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { Command } from 'commander';
import { stringify } from 'yaml';
import * as output from '../output.js';

const TEMPLATE = {
  slug: 'my-gene',
  name: '我的基因',
  version: '1.0.0',
  description: '基因功能描述',
  short_description: '一句话描述',
  category: 'development',
  tags: ['ability'],
  author: { type: 'human', name: '' },
  compatibility: [
    { product: 'openclaw', min_version: '0.5.0' },
    { product: 'nanobot', min_version: '0.1.0' },
  ],
  dependencies: [],
  synergies: [],
  skill: {
    name: 'my-gene',
    always: false,
    file: 'SKILL.md',
  },
  rules: [],
  config: {},
  mcp_servers: [],
  learning: {
    force_deep_learn: false,
    objectives: [],
    scenarios: [],
  },
};

const SKILL_TEMPLATE = `---
name: my-gene
description: 一句话描述
metadata:
  openclaw:
    always: false
  nanobot:
    always: false
---

在此编写基因的技能描述...
`;

export const initCommand = new Command('init')
  .description('初始化基因模板')
  .argument('[path]', '目标目录', '.')
  .action(async (dirPath: string) => {
    const absPath = resolve(dirPath);

    try {
      await mkdir(absPath, { recursive: true });

      const yamlPath = join(absPath, 'gene.yaml');
      await writeFile(yamlPath, stringify(TEMPLATE), 'utf-8');

      const skillPath = join(absPath, 'SKILL.md');
      await writeFile(skillPath, SKILL_TEMPLATE, 'utf-8');

      output.ok(`基因模板已创建:`);
      output.info(`  ${yamlPath}`);
      output.info(`  ${skillPath}`);
      output.info('编辑这两个文件后，使用 genehub publish 发布');
    } catch (err) {
      output.fail(err instanceof Error ? err.message : String(err));
      process.exit(1);
    }
  });
