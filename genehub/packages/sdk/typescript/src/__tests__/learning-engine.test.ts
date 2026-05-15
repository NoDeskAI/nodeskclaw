import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { GeneManifest } from '@nodeskai/genehub-types';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { LearningEngine } from '../learning/engine.js';

const TEST_MANIFEST: GeneManifest = {
  slug: 'test-skill',
  name: '测试技能',
  version: '1.0.0',
  description: '用于测试学习引擎的基因',
  short_description: '测试技能',
  category: 'development',
  tags: ['ability'],
  compatibility: [{ product: 'openclaw', min_version: '0.5.0' }],
  dependencies: [],
  synergies: [],
  skill: { name: 'test-skill', always: false, content: '你是一个测试技能' },
  rules: [],
  mcp_servers: [],
  learning: {
    force_deep_learn: false,
    objectives: ['理解测试的基本概念', '掌握单元测试的写法'],
    scenarios: [{ title: '测试场景', context: '一段有 bug 的代码', expected_focus: '边界条件' }],
  },
};

describe('LearningEngine', () => {
  let tempDir: string;
  let engine: LearningEngine;

  beforeEach(async () => {
    tempDir = await mkdtemp(join(tmpdir(), 'genehub-learn-'));
    engine = new LearningEngine({ workspaceDir: tempDir });
  });

  afterEach(async () => {
    await rm(tempDir, { recursive: true });
  });

  it('createLearningTask() 应创建任务文件', async () => {
    const task = await engine.createLearningTask(TEST_MANIFEST);

    expect(task.gene_slug).toBe('test-skill');
    expect(task.mode).toBe('learn');
    expect(task.learning?.objectives).toHaveLength(2);

    const content = await readFile(join(tempDir, 'learning-tasks', 'test-skill.md'), 'utf-8');
    expect(content).toContain('test-skill');
    expect(content).toContain('理解测试的基本概念');
    expect(content).toContain('测试场景');
  });

  it('listPendingTasks() 应列出未完成的任务', async () => {
    await engine.createLearningTask(TEST_MANIFEST);
    const pending = await engine.listPendingTasks();
    expect(pending).toContain('test-skill');
  });

  it('checkResult() 无结果时返回 null', async () => {
    const result = await engine.checkResult('test-skill');
    expect(result).toBeNull();
  });

  it('checkResult() 应解析学习结果', async () => {
    await engine.createLearningTask(TEST_MANIFEST);

    const resultContent = [
      '---',
      'task_id: learn-test-skill-123',
      'gene_slug: test-skill',
      'mode: learn',
      'decision: learned',
      'self_eval: 0.85',
      'reason: 已深入理解',
      '---',
      '',
      '个性化后的 SKILL.md 内容',
    ].join('\n');

    await mkdir(join(tempDir, 'learning-results'), { recursive: true });
    await writeFile(join(tempDir, 'learning-results', 'test-skill.md'), resultContent);

    const result = await engine.checkResult('test-skill');
    expect(result).not.toBeNull();
    expect(result?.decision).toBe('learned');
    expect(result?.self_eval).toBe(0.85);
    expect(result?.content).toContain('个性化后的 SKILL.md 内容');
  });

  it('applyResult() 应将个性化内容写入 skills 目录', async () => {
    const skillsDir = join(tempDir, 'skills');
    await mkdir(join(skillsDir, 'test-skill'), { recursive: true });
    await writeFile(join(skillsDir, 'test-skill', 'SKILL.md'), '原始内容');

    await mkdir(join(tempDir, 'learning-results'), { recursive: true });
    await writeFile(
      join(tempDir, 'learning-results', 'test-skill.md'),
      '---\ntask_id: t1\ngene_slug: test-skill\nmode: learn\ndecision: learned\n---\n\n新的 SKILL 内容',
    );
    await mkdir(join(tempDir, 'learning-tasks'), { recursive: true });
    await writeFile(join(tempDir, 'learning-tasks', 'test-skill.md'), 'task');

    const applied = await engine.applyResult('test-skill', skillsDir);
    expect(applied).toBe(true);

    const newContent = await readFile(join(skillsDir, 'test-skill', 'SKILL.md'), 'utf-8');
    expect(newContent).toContain('新的 SKILL 内容');
  });

  it('cleanupTask() 应清理任务和结果文件', async () => {
    await engine.createLearningTask(TEST_MANIFEST);
    await engine.cleanupTask('test-skill');

    const pending = await engine.listPendingTasks();
    expect(pending).not.toContain('test-skill');
  });
});
