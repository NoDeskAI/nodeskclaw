import { cp, mkdir, readdir, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import type {
  GeneManifest,
  InstalledGene,
  InstallOptions,
  InstallResult,
  UninstallOptions,
  UninstallResult,
} from '@nodeskai/genehub-types';
import { stringify } from 'yaml';
import { BaseAdapter } from './base.js';

const DEFAULT_DIR = join(process.cwd(), '.genehub', 'genes');

export class GenericAdapter extends BaseAdapter {
  readonly product = 'generic';
  private genesDir: string;

  constructor(options?: { genesDir?: string }) {
    super();
    this.genesDir = options?.genesDir ?? DEFAULT_DIR;
  }

  async detect(): Promise<boolean> {
    return true;
  }

  protected async doInstall(
    manifest: GeneManifest,
    options?: InstallOptions,
  ): Promise<InstallResult> {
    const targetDir = options?.targetPath
      ? join(options.targetPath, manifest.slug)
      : join(this.genesDir, manifest.slug);

    await mkdir(targetDir, { recursive: true });
    const files: string[] = [];

    const yamlPath = join(targetDir, 'gene.yaml');
    await writeFile(yamlPath, stringify(manifest), 'utf-8');
    files.push(yamlPath);

    if (manifest.skill.content) {
      const skillPath = join(targetDir, 'SKILL.md');
      await writeFile(skillPath, manifest.skill.content, 'utf-8');
      files.push(skillPath);
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
      ? join(options.targetPath, manifest.slug)
      : join(this.genesDir, manifest.slug);

    await cp(geneDir, targetDir, { recursive: true });

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

  protected async doUninstall(slug: string, _options?: UninstallOptions): Promise<UninstallResult> {
    const targetDir = join(this.genesDir, slug);
    try {
      await rm(targetDir, { recursive: true });
    } catch {
      // already removed
    }
    return { success: true, slug, files: [targetDir], needsRestart: false };
  }

  async list(): Promise<InstalledGene[]> {
    try {
      const dirs = await readdir(this.genesDir, { withFileTypes: true });
      const results: InstalledGene[] = [];

      for (const dir of dirs) {
        if (!dir.isDirectory()) continue;
        const yamlPath = join(this.genesDir, dir.name, 'gene.yaml');
        try {
          const s = await stat(yamlPath);
          const raw = await readFile(yamlPath, 'utf-8');
          const versionMatch = raw.match(/^version:\s*["']?(.+?)["']?\s*$/m);
          results.push({
            slug: dir.name,
            version: versionMatch?.[1] ?? 'unknown',
            installedAt: s.mtime.toISOString(),
            files: [yamlPath],
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
      await stat(join(this.genesDir, slug, 'gene.yaml'));
      return true;
    } catch {
      return false;
    }
  }

  async getInstalledVersion(slug: string): Promise<string | null> {
    try {
      const raw = await readFile(join(this.genesDir, slug, 'gene.yaml'), 'utf-8');
      const match = raw.match(/^version:\s*["']?(.+?)["']?\s*$/m);
      return match?.[1] ?? null;
    } catch {
      return null;
    }
  }
}
