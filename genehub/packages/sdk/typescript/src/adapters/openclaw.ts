import { randomUUID } from 'node:crypto';
import { appendFile, cp, mkdir, readdir, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { homedir } from 'node:os';
import { basename, join } from 'node:path';
import type {
  GeneManifest,
  InstalledGene,
  InstallOptions,
  InstallResult,
  UninstallOptions,
  UninstallResult,
} from '@nodeskai/genehub-types';
import { BaseAdapter } from './base.js';

const DEFAULT_CONFIG_DIR = join(homedir(), '.openclaw');
const DEFAULT_WORKSPACE_DIR = join(DEFAULT_CONFIG_DIR, 'workspace');
const DEFAULT_SKILLS_DIR = join(DEFAULT_WORKSPACE_DIR, 'skills');
const DEFAULT_CONFIG_PATH = join(DEFAULT_CONFIG_DIR, 'openclaw.json');
const SESSIONS_REL = join('agents', 'main', 'sessions');

export class OpenClawAdapter extends BaseAdapter {
  readonly product = 'openclaw';
  private skillsDir: string;
  private configPath: string;
  private configDir: string;
  private workspaceDir: string;

  constructor(options?: {
    skillsDir?: string;
    configPath?: string;
    workspaceDir?: string;
    configDir?: string;
  }) {
    super();
    this.configDir = options?.configDir ?? DEFAULT_CONFIG_DIR;
    this.workspaceDir = options?.workspaceDir ?? DEFAULT_WORKSPACE_DIR;
    this.skillsDir = options?.skillsDir ?? DEFAULT_SKILLS_DIR;
    this.configPath = options?.configPath ?? DEFAULT_CONFIG_PATH;
  }

  async detect(): Promise<boolean> {
    try {
      await stat(this.configPath);
      return true;
    } catch {
      return false;
    }
  }

  protected async doInstall(
    manifest: GeneManifest,
    options?: InstallOptions,
  ): Promise<InstallResult> {
    const targetDir = options?.targetPath
      ? join(options.targetPath, manifest.skill.name)
      : join(this.skillsDir, manifest.skill.name);

    await mkdir(targetDir, { recursive: true });
    const files: string[] = [];

    const skillPath = join(targetDir, 'SKILL.md');
    const content = this.generateSkillContent(manifest, 'openclaw');
    await writeFile(skillPath, content, 'utf-8');
    files.push(skillPath);

    if (manifest.config?.openclaw) {
      await this.mergeOpenClawConfig(manifest.config.openclaw);
      files.push(this.configPath);
    }

    if (manifest.mcp_servers?.length) {
      await this.mergeMcpServers(manifest.mcp_servers);
      files.push(this.configPath);
    }

    return {
      success: true,
      slug: manifest.slug,
      version: manifest.version,
      files: [...new Set(files)],
      needsRestart: true,
      dependencies: manifest.dependencies.map((d) => d.slug),
    };
  }

  protected override async doInstallFromDirectory(
    geneDir: string,
    manifest: GeneManifest,
    options?: InstallOptions,
  ): Promise<InstallResult> {
    const targetDir = options?.targetPath
      ? join(options.targetPath, manifest.skill.name)
      : join(this.skillsDir, manifest.skill.name);

    await mkdir(targetDir, { recursive: true });
    await cp(geneDir, targetDir, { recursive: true });

    if (manifest.config?.openclaw) {
      await this.mergeOpenClawConfig(manifest.config.openclaw);
    }
    if (manifest.mcp_servers?.length) {
      await this.mergeMcpServers(manifest.mcp_servers);
    }

    const files: string[] = [];
    async function collectFiles(dir: string) {
      const entries = await readdir(dir, { withFileTypes: true });
      for (const entry of entries) {
        const full = join(dir, entry.name);
        if (entry.isDirectory()) await collectFiles(full);
        else files.push(full);
      }
    }
    await collectFiles(targetDir);

    return {
      success: true,
      slug: manifest.slug,
      version: manifest.version,
      files,
      needsRestart: true,
      dependencies: manifest.dependencies.map((d) => d.slug),
    };
  }

  protected async onPostInstall(manifest: GeneManifest, _result: InstallResult): Promise<void> {
    await this.updateAgentsMd(manifest, 'add');
    await this.writeMemoryEntry(manifest, 'install');
    await this.invalidateSkillSnapshots();
    await this.injectEvolutionNotification(manifest.name ?? manifest.slug, 'installed');
  }

  protected async doUninstall(slug: string, _options?: UninstallOptions): Promise<UninstallResult> {
    const targetDir = join(this.skillsDir, slug);
    const files: string[] = [];

    try {
      await rm(targetDir, { recursive: true });
      files.push(targetDir);
    } catch {
      // already removed
    }

    return { success: true, slug, files, needsRestart: true };
  }

  protected async onPostUninstall(slug: string, _result: UninstallResult): Promise<void> {
    await this.updateAgentsMd({ slug } as GeneManifest, 'remove');
    await this.writeMemoryEntry(
      { slug, name: slug, version: 'unknown' } as GeneManifest,
      'uninstall',
    );
    await this.invalidateSkillSnapshots();
    await this.injectEvolutionNotification(slug, 'uninstalled');
  }

  async list(): Promise<InstalledGene[]> {
    try {
      const dirs = await readdir(this.skillsDir, { withFileTypes: true });
      const results: InstalledGene[] = [];

      for (const dir of dirs) {
        if (!dir.isDirectory()) continue;
        const skillPath = join(this.skillsDir, dir.name, 'SKILL.md');
        try {
          const s = await stat(skillPath);
          const content = await readFile(skillPath, 'utf-8');
          const version = this.parseSkillVersion(content) ?? 'unknown';
          results.push({
            slug: dir.name,
            version,
            installedAt: s.mtime.toISOString(),
            files: [skillPath],
          });
        } catch {
          // skip
        }
      }

      return results;
    } catch {
      return [];
    }
  }

  async isInstalled(slug: string): Promise<boolean> {
    try {
      await stat(join(this.skillsDir, slug, 'SKILL.md'));
      return true;
    } catch {
      return false;
    }
  }

  async getInstalledVersion(slug: string): Promise<string | null> {
    try {
      const content = await readFile(join(this.skillsDir, slug, 'SKILL.md'), 'utf-8');
      return this.parseSkillVersion(content);
    } catch {
      return null;
    }
  }

  private async updateAgentsMd(manifest: GeneManifest, action: 'add' | 'remove'): Promise<void> {
    const agentsPath = join(this.workspaceDir, 'AGENTS.md');
    let content: string;
    try {
      content = await readFile(agentsPath, 'utf-8');
    } catch {
      if (action === 'remove') return;
      await mkdir(this.workspaceDir, { recursive: true });
      content = '# AGENTS.md\n';
    }

    const marker = `<!-- genehub:${manifest.slug} -->`;
    const endMarker = `<!-- /genehub:${manifest.slug} -->`;

    const existingPattern = new RegExp(
      `${escapeRegex(marker)}[\\s\\S]*?${escapeRegex(endMarker)}\\n?`,
    );
    content = content.replace(existingPattern, '');

    if (action === 'add') {
      const geneBlock = [
        marker,
        `- **${manifest.name ?? manifest.slug}** (v${manifest.version}) — ${manifest.short_description ?? ''}`,
        endMarker,
      ].join('\n');

      const toolsSection = content.indexOf('## Tools');
      if (toolsSection !== -1) {
        const nextSection = content.indexOf('\n## ', toolsSection + 1);
        const insertPos = nextSection !== -1 ? nextSection : content.length;
        content = `${content.slice(0, insertPos)}\n${geneBlock}\n${content.slice(insertPos)}`;
      } else {
        content += `\n\n## GeneHub Skills\n\n${geneBlock}\n`;
      }
    }

    if (action === 'remove' && manifest.slug === 'genehub-learner') {
      const bootBegin = '<!-- genehub:learning-boot -->';
      const bootEnd = '<!-- /genehub:learning-boot -->';
      const bootPattern = new RegExp(
        `\\n?${escapeRegex(bootBegin)}[\\s\\S]*?${escapeRegex(bootEnd)}\\n?`,
      );
      content = content.replace(bootPattern, '');
    }

    await writeFile(agentsPath, content, 'utf-8');
  }

  private async writeMemoryEntry(
    manifest: GeneManifest,
    action: 'install' | 'uninstall',
  ): Promise<void> {
    const memoryDir = join(this.workspaceDir, 'memory');
    await mkdir(memoryDir, { recursive: true });

    const today = new Date().toISOString().slice(0, 10);
    const memoryPath = join(memoryDir, `${today}.md`);

    let existing = '';
    try {
      existing = await readFile(memoryPath, 'utf-8');
    } catch {
      // new file
    }

    const time = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    const verb = action === 'install' ? '学习了' : '遗忘了';
    const entry = `\n- [${time}] 通过 GeneHub ${verb}基因: **${manifest.name ?? manifest.slug}** v${manifest.version ?? '?'}\n`;

    await writeFile(memoryPath, existing + entry, 'utf-8');
  }

  private async mergeOpenClawConfig(config: NonNullable<GeneManifest['config']>['openclaw']) {
    if (!config) return;

    let existing: Record<string, unknown> = {};
    try {
      const raw = await readFile(this.configPath, 'utf-8');
      existing = JSON.parse(raw);
    } catch {
      // no existing config
    }

    if (config.openclaw_config) {
      Object.assign(existing, config.openclaw_config);
    }

    if (config.tool_allow) {
      const current = ((existing.tools as Record<string, unknown>)?.allow as string[]) ?? [];
      const merged = [...new Set([...current, ...config.tool_allow])];
      if (!existing.tools) existing.tools = {};
      (existing.tools as Record<string, unknown>).allow = merged;
    }

    await writeFile(this.configPath, JSON.stringify(existing, null, 2), 'utf-8');
  }

  private async mergeMcpServers(servers: NonNullable<GeneManifest['mcp_servers']>) {
    if (!servers?.length) return;

    let existing: Record<string, unknown> = {};
    try {
      const raw = await readFile(this.configPath, 'utf-8');
      existing = JSON.parse(raw);
    } catch {
      return;
    }

    const mcpServers = (existing.mcpServers ?? {}) as Record<string, unknown>;
    for (const server of servers) {
      mcpServers[server.name] = {
        transport: server.transport,
        command: server.command,
        args: server.args,
        env: server.env,
      };
    }
    existing.mcpServers = mcpServers;

    await writeFile(this.configPath, JSON.stringify(existing, null, 2), 'utf-8');
  }

  async triggerLearning(prompt: string): Promise<void> {
    const { execFile, spawn } = await import('node:child_process');
    const { promisify } = await import('node:util');
    const { setTimeout: sleep } = await import('node:timers/promises');
    const run = promisify(execFile);

    try {
      await run('openclaw', ['gateway', 'restart'], { timeout: 15_000 });
    } catch {
      // gateway might not be installed as a service; continue anyway
    }

    await sleep(5000);

    const child = spawn('openclaw', ['agent', '--agent', 'main', '--message', prompt], {
      detached: true,
      stdio: 'ignore',
    });
    child.unref();
  }

  async notifySkillChange(
    geneName: string,
    action: 'installed' | 'updated' | 'uninstalled',
  ): Promise<void> {
    await this.invalidateSkillSnapshots();
    const notifyAction = action === 'uninstalled' ? 'uninstalled' : 'installed';
    await this.injectEvolutionNotification(geneName, notifyAction);
  }

  /**
   * Clear cached skillsSnapshot from all OpenClaw sessions.
   * Without this, OpenClaw keeps using the stale skill list even after restart.
   */
  private async invalidateSkillSnapshots(): Promise<void> {
    const sessionsPath = join(this.configDir, SESSIONS_REL, 'sessions.json');
    let raw: string;
    try {
      raw = await readFile(sessionsPath, 'utf-8');
    } catch {
      return;
    }

    try {
      const store = JSON.parse(raw) as Record<string, unknown>;
      let changed = false;

      for (const entry of Object.values(store)) {
        if (entry && typeof entry === 'object' && 'skillsSnapshot' in entry) {
          delete (entry as Record<string, unknown>).skillsSnapshot;
          changed = true;
        }
      }

      if (changed) {
        await writeFile(sessionsPath, JSON.stringify(store, null, 2), 'utf-8');
      }
    } catch {
      // best-effort
    }
  }

  /**
   * Inject evolution notification into all active session JSONL files.
   *
   * Old conversation history may contain stale skill listings from the agent.
   * The LLM repeats its previous answer instead of re-checking the system prompt.
   * By appending a user+assistant message pair about the evolution, we override
   * the stale context. Also resets systemSent to force system prompt rebuild.
   */
  private async injectEvolutionNotification(
    geneName: string,
    action: 'installed' | 'uninstalled',
  ): Promise<void> {
    const sessionsDir = join(this.configDir, SESSIONS_REL);
    const sessionsPath = join(sessionsDir, 'sessions.json');

    let raw: string;
    try {
      raw = await readFile(sessionsPath, 'utf-8');
    } catch {
      return;
    }

    const userText =
      action === 'installed'
        ? `[System] 基因系统通知: 你刚刚获取了新的基因「${geneName}」，完成了一轮进化。你的技能列表已更新，请以 system prompt 中 <available_skills> 为准。`
        : `[System] 基因系统通知: 基因「${geneName}」已遗忘。你的技能列表已更新，请以 system prompt 中 <available_skills> 为准。`;

    const assistantText =
      action === 'installed'
        ? `收到，我已获取新基因「${geneName}」并完成进化。我的技能列表已更新。`
        : `收到，基因「${geneName}」已遗忘。我的技能列表已更新。`;

    try {
      const store = JSON.parse(raw) as Record<string, unknown>;
      let storeChanged = false;

      for (const entry of Object.values(store)) {
        if (!entry || typeof entry !== 'object') continue;
        const rec = entry as Record<string, unknown>;
        const sessionFile = rec.sessionFile as string | undefined;
        if (!sessionFile) continue;

        const localPath = join(sessionsDir, basename(sessionFile));
        let content: string;
        try {
          content = (await readFile(localPath, 'utf-8')).trimEnd();
          if (!content) continue;
        } catch {
          continue;
        }

        try {
          const lastLine = content.split('\n').pop() ?? '';
          const lastEntry = JSON.parse(lastLine) as Record<string, unknown>;
          const parentId = (lastEntry.id as string) ?? randomUUID().slice(0, 8);

          const now = new Date();
          const tsIso = now.toISOString();
          const tsMs = now.getTime();
          const userId = randomUUID().slice(0, 8);
          const assistantId = randomUUID().slice(0, 8);

          const modelProvider = (rec.modelProvider as string) ?? 'system';
          const modelName = (rec.model as string) ?? 'system';

          const userMsg = JSON.stringify({
            type: 'message',
            id: userId,
            parentId,
            timestamp: tsIso,
            message: {
              role: 'user',
              content: [{ type: 'text', text: userText }],
              timestamp: tsMs,
            },
          });

          const assistantMsg = JSON.stringify({
            type: 'message',
            id: assistantId,
            parentId: userId,
            timestamp: tsIso,
            message: {
              role: 'assistant',
              content: [{ type: 'text', text: assistantText }],
              api: 'openai-completions',
              provider: modelProvider,
              model: modelName,
              usage: {
                input: 0,
                output: 0,
                cacheRead: 0,
                cacheWrite: 0,
                totalTokens: 0,
                cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
              },
              stopReason: 'stop',
              timestamp: tsMs,
            },
          });

          await appendFile(localPath, `\n${userMsg}\n${assistantMsg}`, 'utf-8');
        } catch {
          continue;
        }

        rec.systemSent = false;
        storeChanged = true;
      }

      if (storeChanged) {
        await writeFile(sessionsPath, JSON.stringify(store, null, 2), 'utf-8');
      }
    } catch {
      // best-effort
    }
  }
}

function escapeRegex(str: string) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
