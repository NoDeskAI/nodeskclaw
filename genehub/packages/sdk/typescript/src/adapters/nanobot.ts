import { cp, mkdir, readdir, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { homedir } from 'node:os';
import { join } from 'node:path';
import type {
  GeneManifest,
  InstalledGene,
  InstallOptions,
  InstallResult,
  UninstallOptions,
  UninstallResult,
} from '@nodeskai/genehub-types';
import { BaseAdapter } from './base.js';

const DEFAULT_WORKSPACE = join(homedir(), '.nanobot', 'workspace');
const DEFAULT_CONFIG_PATH = join(homedir(), '.nanobot', 'config.json');

export class NanobotAdapter extends BaseAdapter {
  readonly product = 'nanobot';
  private workspace: string;
  private configPath: string;

  constructor(options?: { workspace?: string; configPath?: string }) {
    super();
    this.workspace = options?.workspace ?? DEFAULT_WORKSPACE;
    this.configPath = options?.configPath ?? DEFAULT_CONFIG_PATH;
  }

  private get skillsDir(): string {
    return join(this.workspace, 'skills');
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

    const skillContent = this.buildNanobotSkillContent(manifest);
    const skillPath = join(targetDir, 'SKILL.md');
    await writeFile(skillPath, skillContent, 'utf-8');
    files.push(skillPath);

    if (manifest.mcp_servers.length > 0) {
      await this.mergeNanobotMcpConfig(manifest.mcp_servers);
    }

    return {
      success: true,
      slug: manifest.slug,
      version: manifest.version,
      files,
      needsRestart: false,
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

    if (manifest.mcp_servers.length > 0) {
      await this.mergeNanobotMcpConfig(manifest.mcp_servers);
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
      needsRestart: false,
      dependencies: manifest.dependencies.map((d) => d.slug),
    };
  }

  protected async onPostInstall(manifest: GeneManifest, _result: InstallResult): Promise<void> {
    await this.writeMemoryEntry(manifest, 'install');
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

    return { success: true, slug, files, needsRestart: false };
  }

  protected async onPostUninstall(slug: string, _result: UninstallResult): Promise<void> {
    await this.writeMemoryEntry(
      { slug, name: slug, version: 'unknown' } as GeneManifest,
      'uninstall',
    );
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

  async triggerLearning(prompt: string): Promise<void> {
    const { exec } = await import('node:child_process');
    const { promisify } = await import('node:util');
    const execAsync = promisify(exec);

    const escaped = prompt.replace(/"/g, '\\"');
    try {
      await execAsync(`nanobot run --prompt "${escaped}"`, { timeout: 5000 });
    } catch {
      // fire-and-forget: nanobot CLI support is tentative
    }
  }

  private async writeMemoryEntry(
    manifest: GeneManifest,
    action: 'install' | 'uninstall',
  ): Promise<void> {
    const memoryDir = join(this.workspace, 'memory');
    await mkdir(memoryDir, { recursive: true });

    const today = new Date().toISOString().slice(0, 10);
    const memoryPath = join(memoryDir, `${today}.md`);

    let existing = '';
    try {
      existing = await readFile(memoryPath, 'utf-8');
    } catch {
      /* new file */
    }

    const time = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    const verb = action === 'install' ? '学习了' : '遗忘了';
    const entry = `\n- [${time}] 通过 GeneHub ${verb}基因: **${manifest.name ?? manifest.slug}** v${manifest.version ?? '?'}\n`;

    await writeFile(memoryPath, existing + entry, 'utf-8');
  }

  private buildNanobotSkillContent(manifest: GeneManifest): string {
    if (manifest.skill.content?.trim().startsWith('---')) {
      return manifest.skill.content;
    }

    return this.generateSkillContent(manifest, 'nanobot');
  }

  private async mergeNanobotMcpConfig(mcpServers: GeneManifest['mcp_servers']): Promise<void> {
    let config: Record<string, unknown> = {};
    try {
      const raw = await readFile(this.configPath, 'utf-8');
      const parsed = JSON.parse(raw) as unknown;
      if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
        console.warn(
          '[NanobotAdapter] config.json 内容不是有效对象，MCP 配置未写入:',
          this.configPath,
        );
        return;
      }
      config = parsed as Record<string, unknown>;
    } catch (err) {
      const errorDetail = err instanceof Error ? err.message : err;
      if (
        err &&
        typeof err === 'object' &&
        'code' in err &&
        (err as { code?: string }).code === 'ENOENT'
      ) {
        console.warn(
          '[NanobotAdapter] config.json 不存在，MCP 配置未写入:',
          this.configPath,
          errorDetail,
        );
      } else if (err instanceof SyntaxError) {
        console.warn(
          '[NanobotAdapter] config.json 解析失败（JSON 格式错误），MCP 配置未写入:',
          this.configPath,
          errorDetail,
        );
      } else {
        console.warn(
          '[NanobotAdapter] config.json 读取或解析失败，MCP 配置未写入:',
          this.configPath,
          errorDetail,
        );
      }
      return;
    }

    if (!config.tools) config.tools = {};
    const tools = config.tools as Record<string, unknown>;
    if (!tools.mcpServers) tools.mcpServers = {};
    const servers = tools.mcpServers as Record<string, unknown>;

    for (const srv of mcpServers) {
      if (servers[srv.name]) continue;
      servers[srv.name] = {
        ...(srv.command ? { command: srv.command, args: srv.args ?? [], env: srv.env ?? {} } : {}),
        ...(srv.url ? { url: srv.url, headers: srv.headers ?? {} } : {}),
      };
    }

    await writeFile(this.configPath, JSON.stringify(config, null, 2), 'utf-8');
  }
}
