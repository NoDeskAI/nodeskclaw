import { mkdir, readdir, readFile, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import type { GeneAdapter, GeneManifest } from '@nodeskai/genehub-types';
import type { GeneHubClient } from '../client.js';
import { META_LEARNER_MANIFEST } from './meta-gene.js';
import { generateForgetTaskMarkdown, generateLearningTaskMarkdown } from './prompts.js';
import type { LearningResult, LearningTask } from './task.js';

export type LearningEngineOptions = {
  workspaceDir: string;
  adapter?: GeneAdapter;
  client?: GeneHubClient;
};

export class LearningEngine {
  private workspaceDir: string;
  private adapter?: GeneAdapter;
  private client?: GeneHubClient;

  constructor(options: LearningEngineOptions) {
    this.workspaceDir = options.workspaceDir;
    this.adapter = options.adapter;
    this.client = options.client;
  }

  private get tasksDir(): string {
    return join(this.workspaceDir, 'learning-tasks');
  }

  private get resultsDir(): string {
    return join(this.workspaceDir, 'learning-results');
  }

  async ensureMetaGeneInstalled(): Promise<boolean> {
    if (!this.adapter) return false;

    await this.injectBootInstruction();

    const installed = await this.adapter.isInstalled('genehub-learner');
    if (installed) return false;

    let manifest = META_LEARNER_MANIFEST;
    if (this.client) {
      try {
        manifest = await this.client.getManifest('genehub-learner');
      } catch {
        // Fallback to built-in manifest if remote fetch fails
      }
    }

    await this.adapter.install(manifest, { force: true });
    return true;
  }

  private async injectBootInstruction(): Promise<void> {
    const agentsPath = join(this.workspaceDir, 'AGENTS.md');
    let content: string;
    try {
      content = await readFile(agentsPath, 'utf-8');
    } catch {
      content = '# AGENTS.md\n';
    }

    const BEGIN = '<!-- genehub:learning-boot -->';
    const END = '<!-- /genehub:learning-boot -->';

    if (content.includes(BEGIN)) return;

    const instruction = [
      '',
      BEGIN,
      '### GeneHub Learning',
      '',
      'Check `learning-tasks/` for pending `.md` files. If any exist:',
      '',
      '1. Read `skills/genehub-learner/SKILL.md` for the full learning protocol',
      '2. Process each task file following those instructions',
      '3. Write results to `learning-results/`',
      '4. **Delete the completed task file from `learning-tasks/`**',
      '5. Log what you learned in `memory/YYYY-MM-DD.md`',
      END,
    ].join('\n');

    const everySession = content.indexOf('## Every Session');
    if (everySession !== -1) {
      const nextSection = content.indexOf('\n## ', everySession + 1);
      const insertPos = nextSection !== -1 ? nextSection : content.length;
      content = `${content.slice(0, insertPos)}\n${instruction}\n${content.slice(insertPos)}`;
    } else {
      content += `\n${instruction}\n`;
    }

    await mkdir(join(this.workspaceDir), { recursive: true });
    await writeFile(agentsPath, content, 'utf-8');
  }

  async createLearningTask(manifest: GeneManifest): Promise<LearningTask> {
    await this.ensureMetaGeneInstalled();

    await mkdir(this.tasksDir, { recursive: true });
    await mkdir(this.resultsDir, { recursive: true });

    const task: LearningTask = {
      mode: 'learn',
      task_id: `learn-${manifest.slug}-${Date.now()}`,
      gene_slug: manifest.slug,
      gene_name: manifest.name,
      gene_version: manifest.version,
      gene_content: manifest.skill.content ?? '',
      gene_meta: {
        name: manifest.name,
        description: manifest.description,
        category: manifest.category,
        short_description: manifest.short_description,
      },
      learning: manifest.learning
        ? {
            objectives: manifest.learning.objectives,
            scenarios: manifest.learning.scenarios,
            force_deep_learn: manifest.learning.force_deep_learn,
          }
        : undefined,
      callback_path: join(this.resultsDir, `${manifest.slug}.md`),
      created_at: new Date().toISOString(),
    };

    const md = generateLearningTaskMarkdown(task);
    await writeFile(join(this.tasksDir, `${manifest.slug}.md`), md, 'utf-8');

    return task;
  }

  async createForgetTask(slug: string, name: string, skillContent: string): Promise<void> {
    await mkdir(this.tasksDir, { recursive: true });
    await mkdir(this.resultsDir, { recursive: true });

    const callbackPath = join(this.resultsDir, `${slug}.md`);
    const md = generateForgetTaskMarkdown(slug, name, skillContent, callbackPath);
    await writeFile(join(this.tasksDir, `${slug}.md`), md, 'utf-8');
  }

  async checkResult(slug: string): Promise<LearningResult | null> {
    const resultPath = join(this.resultsDir, `${slug}.md`);

    try {
      const content = await readFile(resultPath, 'utf-8');
      return this.parseResult(content);
    } catch {
      return null;
    }
  }

  async listPendingTasks(): Promise<string[]> {
    try {
      const files = await readdir(this.tasksDir);
      const pending: string[] = [];

      for (const file of files) {
        if (!file.endsWith('.md')) continue;
        const slug = file.replace('.md', '');
        const result = await this.checkResult(slug);
        if (!result) {
          pending.push(slug);
        }
      }

      return pending;
    } catch {
      return [];
    }
  }

  async listCompletedResults(): Promise<LearningResult[]> {
    const results: LearningResult[] = [];

    try {
      const files = await readdir(this.resultsDir);
      for (const file of files) {
        if (!file.endsWith('.md')) continue;
        const content = await readFile(join(this.resultsDir, file), 'utf-8');
        const result = this.parseResult(content);
        if (result) results.push(result);
      }
    } catch {
      // no results
    }

    return results;
  }

  async applyResult(slug: string, skillsDir: string): Promise<boolean> {
    const result = await this.checkResult(slug);
    if (!result) return false;

    if (result.decision === 'learned' && result.content) {
      const skillDir = join(skillsDir, slug);
      await mkdir(skillDir, { recursive: true });
      await writeFile(join(skillDir, 'SKILL.md'), result.content, 'utf-8');

      if (this.adapter?.notifySkillChange) {
        await this.adapter.notifySkillChange(slug, 'updated');
      }
    }

    await this.cleanupTask(slug);
    return true;
  }

  async cleanupTask(slug: string): Promise<void> {
    try {
      await rm(join(this.tasksDir, `${slug}.md`));
    } catch {
      /* ok */
    }
    try {
      await rm(join(this.resultsDir, `${slug}.md`));
    } catch {
      /* ok */
    }
  }

  private parseResult(content: string): LearningResult | null {
    const fmMatch = content.match(/^---\n([\s\S]*?)\n---/);
    if (!fmMatch) return null;

    const fm = fmMatch[1];
    const get = (key: string): string | undefined => {
      const m = fm.match(new RegExp(`^${key}:\\s*["']?(.+?)["']?\\s*$`, 'm'));
      return m?.[1];
    };

    const taskId = get('task_id');
    const geneSlug = get('gene_slug');
    const mode = get('mode') as LearningResult['mode'] | undefined;
    const decision = get('decision') as LearningResult['decision'] | undefined;

    if (!taskId || !geneSlug || !decision) return null;

    const bodyStart = content.indexOf('---', 4);
    const body = bodyStart !== -1 ? content.slice(bodyStart + 3).trim() : undefined;

    return {
      task_id: taskId,
      gene_slug: geneSlug,
      mode: mode ?? 'learn',
      decision,
      content: body || undefined,
      self_eval: get('self_eval') ? Number.parseFloat(get('self_eval') as string) : undefined,
      reason: get('reason'),
      completed_at: new Date().toISOString(),
    };
  }
}
