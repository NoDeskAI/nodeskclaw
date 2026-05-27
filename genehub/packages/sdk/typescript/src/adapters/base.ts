import type {
  GeneAdapter,
  GeneManifest,
  InstalledGene,
  InstallOptions,
  InstallResult,
  UninstallOptions,
  UninstallResult,
} from '@nodeskai/genehub-types';

export abstract class BaseAdapter implements GeneAdapter {
  abstract readonly product: string;

  abstract detect(): Promise<boolean>;

  async install(manifest: GeneManifest, options?: InstallOptions): Promise<InstallResult> {
    const result = await this.doInstall(manifest, options);
    await this.onPostInstall(manifest, result);
    return result;
  }

  async installFromDirectory(
    geneDir: string,
    manifest: GeneManifest,
    options?: InstallOptions,
  ): Promise<InstallResult> {
    const result = await this.doInstallFromDirectory(geneDir, manifest, options);
    await this.onPostInstall(manifest, result);
    return result;
  }

  protected abstract doInstall(
    manifest: GeneManifest,
    options?: InstallOptions,
  ): Promise<InstallResult>;

  protected async doInstallFromDirectory(
    _geneDir: string,
    manifest: GeneManifest,
    options?: InstallOptions,
  ): Promise<InstallResult> {
    return this.doInstall(manifest, options);
  }

  protected async onPostInstall(_manifest: GeneManifest, _result: InstallResult): Promise<void> {}

  protected async onPostUninstall(_slug: string, _result: UninstallResult): Promise<void> {}

  async uninstall(slug: string, options?: UninstallOptions): Promise<UninstallResult> {
    const result = await this.doUninstall(slug, options);
    await this.onPostUninstall(slug, result);
    return result;
  }

  protected abstract doUninstall(
    slug: string,
    options?: UninstallOptions,
  ): Promise<UninstallResult>;

  abstract list(): Promise<InstalledGene[]>;

  abstract isInstalled(slug: string): Promise<boolean>;

  abstract getInstalledVersion(slug: string): Promise<string | null>;

  protected generateSkillContent(manifest: GeneManifest, metadataNamespace: string): string {
    const skillMeta = manifest.skill.always ? 'true' : 'false';
    const frontMatter = [
      '---',
      `name: ${manifest.skill.name}`,
      `version: ${manifest.version}`,
      `description: ${manifest.short_description}`,
      'metadata:',
      `  ${metadataNamespace}:`,
      `    always: ${skillMeta}`,
      '---',
    ].join('\n');

    if (manifest.skill.content) {
      const content = manifest.skill.content.trim();
      if (content.startsWith('---')) {
        return content;
      }
      return `${frontMatter}\n\n${content}`;
    }

    return frontMatter;
  }

  protected parseSkillVersion(content: string): string | null {
    const match = content.match(/^---[\s\S]*?version:\s*(.+?)[\s\n][\s\S]*?---/m);
    return match?.[1]?.trim() ?? null;
  }
}
