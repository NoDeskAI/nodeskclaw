import { mkdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { detectSkillFile } from '../utils/detect-skill.js';

let testDir: string;

beforeEach(async () => {
  testDir = join(tmpdir(), `genehub-test-${Date.now()}`);
  await mkdir(testDir, { recursive: true });
});

afterEach(async () => {
  await rm(testDir, { recursive: true, force: true });
});

describe('detectSkillFile', () => {
  it('检测 CLAUDE.md 并推断元数据', async () => {
    await writeFile(
      join(testDir, 'CLAUDE.md'),
      '# My Coding Assistant\n\nThis agent helps with TypeScript development.\n\nMore details here.',
    );

    const result = await detectSkillFile(testDir);

    expect(result).not.toBeNull();
    expect(result?.format).toBe('claude');
    expect(result?.fileName).toBe('CLAUDE.md');
    expect(result?.inferredName).toBe('My Coding Assistant');
    expect(result?.inferredDescription).toContain('TypeScript development');
  });

  it('检测 SKILL.md (带 frontmatter)', async () => {
    await writeFile(
      join(testDir, 'SKILL.md'),
      '---\nname: memory-manager\ndescription: Manages long-term memory\n---\n\n# Memory Manager\n\nImplementation details...',
    );

    const result = await detectSkillFile(testDir);

    expect(result).not.toBeNull();
    expect(result?.format).toBe('skill');
    expect(result?.inferredName).toBe('memory-manager');
    expect(result?.inferredDescription).toBe('Manages long-term memory');
  });

  it('CLAUDE.md 优先于 SKILL.md', async () => {
    await writeFile(join(testDir, 'CLAUDE.md'), '# Claude');
    await writeFile(join(testDir, 'SKILL.md'), '# Skill');

    const result = await detectSkillFile(testDir);
    expect(result?.fileName).toBe('CLAUDE.md');
  });

  it('检测 AGENTS.md', async () => {
    await writeFile(
      join(testDir, 'AGENTS.md'),
      '# Project Agent Guide\n\nHow to work with this codebase.',
    );

    const result = await detectSkillFile(testDir);

    expect(result).not.toBeNull();
    expect(result?.format).toBe('agents');
  });

  it('检测 .cursorrules', async () => {
    await writeFile(join(testDir, '.cursorrules'), 'Always use TypeScript strict mode.');

    const result = await detectSkillFile(testDir);

    expect(result).not.toBeNull();
    expect(result?.format).toBe('cursorrules');
  });

  it('目录名推断 slug', async () => {
    const namedDir = join(tmpdir(), `genehub-test-My Cool Gene-${Date.now()}`);
    await mkdir(namedDir, { recursive: true });
    await writeFile(join(namedDir, 'SKILL.md'), '# Test');

    try {
      const result = await detectSkillFile(namedDir);
      expect(result?.inferredSlug).toMatch(/^[a-z0-9][a-z0-9-]*[a-z0-9]$/);
    } finally {
      await rm(namedDir, { recursive: true, force: true });
    }
  });

  it('空目录返回 null', async () => {
    const result = await detectSkillFile(testDir);
    expect(result).toBeNull();
  });

  it('只有 README.md 时返回 null', async () => {
    await writeFile(join(testDir, 'README.md'), '# Just a readme');

    const result = await detectSkillFile(testDir);
    expect(result).toBeNull();
  });

  it('fallback 到非 README 的 .md 文件', async () => {
    await writeFile(join(testDir, 'guide.md'), '# Development Guide\n\nFollow these rules...');

    const result = await detectSkillFile(testDir);

    expect(result).not.toBeNull();
    expect(result?.format).toBe('markdown');
    expect(result?.fileName).toBe('guide.md');
  });
});
