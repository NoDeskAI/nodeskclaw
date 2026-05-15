/**
 * Auto-detect skill files in a directory and infer gene manifest metadata.
 *
 * Supported formats (priority order):
 * - CLAUDE.md    (Claude Code)
 * - SKILL.md     (ClawHub / GeneHub)
 * - AGENTS.md    (Cursor / generic)
 * - .cursorrules (Cursor rules)
 * - .clinerules  (Cline rules)
 * - instructions.md (generic)
 * - Any other .md file (fallback)
 */

import { readdir, readFile } from 'node:fs/promises';
import { basename, join } from 'node:path';

export type DetectedSkill = {
  filePath: string;
  fileName: string;
  format: 'claude' | 'skill' | 'agents' | 'cursorrules' | 'clinerules' | 'markdown';
  content: string;
  frontmatter: Record<string, unknown>;
  inferredSlug: string;
  inferredName: string;
  inferredDescription: string;
};

const DETECTION_ORDER: { pattern: string | RegExp; format: DetectedSkill['format'] }[] = [
  { pattern: 'CLAUDE.md', format: 'claude' },
  { pattern: 'SKILL.md', format: 'skill' },
  { pattern: 'AGENTS.md', format: 'agents' },
  { pattern: '.cursorrules', format: 'cursorrules' },
  { pattern: '.clinerules', format: 'clinerules' },
  { pattern: 'instructions.md', format: 'markdown' },
  { pattern: /^(?!readme\.md$).*\.md$/i, format: 'markdown' },
];

const SLUG_REGEX = /^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$/;

export async function detectSkillFile(dirPath: string): Promise<DetectedSkill | null> {
  let entries: string[];
  try {
    entries = (await readdir(dirPath)).map((e) => e.toString());
  } catch {
    return null;
  }

  for (const rule of DETECTION_ORDER) {
    const match =
      typeof rule.pattern === 'string'
        ? entries.find((e) => e === rule.pattern)
        : entries.find((e) => rule.pattern instanceof RegExp && rule.pattern.test(e));

    if (match) {
      const filePath = join(dirPath, match);
      const content = await readFile(filePath, 'utf-8');
      const frontmatter = parseFrontmatter(content);
      const slug = inferSlug(dirPath);
      const name = inferName(frontmatter, content, slug);
      const description = inferDescription(frontmatter, content);

      return {
        filePath,
        fileName: match,
        format: rule.format,
        content,
        frontmatter,
        inferredSlug: slug,
        inferredName: name,
        inferredDescription: description,
      };
    }
  }

  return null;
}

function parseFrontmatter(content: string): Record<string, unknown> {
  const match = content.match(/^---\s*\n([\s\S]*?)\n---/);
  if (!match) return {};

  const result: Record<string, unknown> = {};
  for (const line of match[1].split('\n')) {
    const kv = line.match(/^(\w[\w-]*):\s*(.+)/);
    if (kv) {
      result[kv[1]] = kv[2].trim();
    }
  }
  return result;
}

function inferSlug(dirPath: string): string {
  const dirName = basename(dirPath);
  const slug = dirName
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');

  if (SLUG_REGEX.test(slug)) return slug;

  const padded = slug.length < 3 ? `${slug}-gene`.slice(0, 64) : slug.slice(0, 64);
  return SLUG_REGEX.test(padded) ? padded : 'my-gene';
}

function inferName(frontmatter: Record<string, unknown>, content: string, slug: string): string {
  if (typeof frontmatter.name === 'string' && frontmatter.name) {
    return frontmatter.name;
  }
  if (typeof frontmatter.title === 'string' && frontmatter.title) {
    return frontmatter.title;
  }

  const h1 = content.match(/^#\s+(.+)/m);
  if (h1) return h1[1].trim().slice(0, 128);

  return slug
    .split('-')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

function inferDescription(frontmatter: Record<string, unknown>, content: string): string {
  if (typeof frontmatter.description === 'string' && frontmatter.description) {
    return frontmatter.description;
  }

  const body = content.replace(/^---[\s\S]*?---\s*\n?/, '').replace(/^#[^\n]*\n?/, '');

  const firstPara = body.match(/\S[^\n]*(?:\n(?!\s*\n|\s*#)[^\n]*)*/);
  if (firstPara) {
    return firstPara[0].trim().slice(0, 256);
  }

  return '';
}

export function getFormatLabel(format: DetectedSkill['format']): string {
  const labels: Record<DetectedSkill['format'], string> = {
    claude: 'Claude Code (CLAUDE.md)',
    skill: 'SKILL.md',
    agents: 'AGENTS.md',
    cursorrules: 'Cursor Rules (.cursorrules)',
    clinerules: 'Cline Rules (.clinerules)',
    markdown: 'Markdown',
  };
  return labels[format];
}
