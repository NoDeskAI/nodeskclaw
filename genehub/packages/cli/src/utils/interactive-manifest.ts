/**
 * Interactive manifest builder: prompts for missing fields and returns
 * a complete GeneManifest ready for validation and publish.
 */

import { checkbox, confirm, input, select } from '@inquirer/prompts';
import type { DetectedSkill } from './detect-skill.js';

const CATEGORY_OPTIONS = [
  { name: 'development  - 开发能力', value: 'development' },
  { name: 'data         - 数据处理', value: 'data' },
  { name: 'operations   - 运维能力', value: 'operations' },
  { name: 'network      - 网络协作', value: 'network' },
  { name: 'creative     - 创意创作', value: 'creative' },
  { name: 'communication- 沟通交流', value: 'communication' },
  { name: 'security     - 安全防护', value: 'security' },
  { name: 'efficiency   - 效率工具', value: 'efficiency' },
] as const;

const TAG_OPTIONS = [
  { name: 'ability     - 技能能力', value: 'ability' as const },
  { name: 'personality - 人格特质', value: 'personality' as const },
  { name: 'knowledge   - 知识储备', value: 'knowledge' as const },
  { name: 'tool        - 工具集成', value: 'tool' as const },
] as const;

const DEFAULT_COMPATIBILITY = [
  { product: 'openclaw' as const, min_version: '0.5.0' },
  { product: 'nanobot' as const, min_version: '0.1.0' },
  { product: 'generic' as const, min_version: '0.0.0' },
];

export type ManifestDraft = {
  slug: string;
  name: string;
  version: string;
  description: string;
  short_description: string;
  category: string;
  tags: string[];
  author: { type: 'human'; name: string };
  compatibility: { product: string; min_version: string }[];
  dependencies: never[];
  synergies: never[];
  skill: { name: string; always: boolean; content: string; file: string };
  rules: never[];
  config: Record<string, never>;
  mcp_servers: never[];
};

export async function buildManifestInteractively(
  detected: DetectedSkill,
  isNonInteractive = false,
): Promise<ManifestDraft> {
  if (isNonInteractive) {
    return buildWithDefaults(detected);
  }

  const slug = await input({
    message: 'Slug (基因标识符, kebab-case)',
    default: detected.inferredSlug,
    validate: (v) =>
      /^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$/.test(v) || 'slug 必须为 kebab-case, 3-64 字符',
  });

  const name = await input({
    message: 'Name (显示名称)',
    default: detected.inferredName,
    validate: (v) => (v.length > 0 && v.length <= 128) || '1-128 字符',
  });

  const shortDesc = await input({
    message: 'Short description (一句话描述, 256 字符内)',
    default: detected.inferredDescription.slice(0, 256),
    validate: (v) => v.length <= 256 || '最多 256 字符',
  });

  const category = await select({
    message: 'Category (基因分类)',
    choices: CATEGORY_OPTIONS.map((o) => ({ name: o.name, value: o.value })),
    default: 'development',
  });

  const tags = await checkbox({
    message: 'Tags (至少选一个)',
    choices: TAG_OPTIONS.map((o) => ({
      name: o.name,
      value: o.value,
      checked: o.value === 'ability',
    })),
    validate: (v) => v.length > 0 || '至少选择一个 tag',
  });

  return {
    slug,
    name,
    version: '1.0.0',
    description: detected.inferredDescription || shortDesc,
    short_description: shortDesc,
    category,
    tags,
    author: { type: 'human', name: '' },
    compatibility: DEFAULT_COMPATIBILITY,
    dependencies: [],
    synergies: [],
    skill: {
      name: slug,
      always: false,
      content: detected.content,
      file: detected.fileName,
    },
    rules: [],
    config: {},
    mcp_servers: [],
  };
}

function buildWithDefaults(detected: DetectedSkill): ManifestDraft {
  return {
    slug: detected.inferredSlug,
    name: detected.inferredName,
    version: '1.0.0',
    description: detected.inferredDescription,
    short_description: detected.inferredDescription.slice(0, 256),
    category: 'development',
    tags: ['ability'],
    author: { type: 'human', name: '' },
    compatibility: DEFAULT_COMPATIBILITY,
    dependencies: [],
    synergies: [],
    skill: {
      name: detected.inferredSlug,
      always: false,
      content: detected.content,
      file: detected.fileName,
    },
    rules: [],
    config: {},
    mcp_servers: [],
  };
}

export async function confirmSaveManifest(): Promise<boolean> {
  return confirm({
    message: '是否将 gene.yaml 保存到目录中? (方便下次直接发布)',
    default: true,
  });
}

export async function confirmPublish(slug: string, version: string): Promise<boolean> {
  return confirm({
    message: `确认发布 ${slug}@${version}?`,
    default: true,
  });
}
