import type { GeneManifest } from './manifest.js';

export type InstallOptions = {
  targetPath?: string;
  force?: boolean;
  skipDependencies?: boolean;
};

export type UninstallOptions = {
  keepConfig?: boolean;
};

export type InstallResult = {
  success: boolean;
  slug: string;
  version: string;
  files: string[];
  needsRestart: boolean;
  dependencies: string[];
};

export type UninstallResult = {
  success: boolean;
  slug: string;
  files: string[];
  needsRestart: boolean;
};

export type InstalledGene = {
  slug: string;
  version: string;
  installedAt: string;
  files: string[];
};

export interface GeneAdapter {
  readonly product: string;

  detect(): Promise<boolean>;

  install(manifest: GeneManifest, options?: InstallOptions): Promise<InstallResult>;

  /**
   * Install a gene from an extracted directory containing all gene files.
   * Used for multi-file genes downloaded as tarballs from the registry.
   * Falls back to manifest-based install if not implemented.
   */
  installFromDirectory?(
    geneDir: string,
    manifest: GeneManifest,
    options?: InstallOptions,
  ): Promise<InstallResult>;

  uninstall(slug: string, options?: UninstallOptions): Promise<UninstallResult>;

  list(): Promise<InstalledGene[]>;

  isInstalled(slug: string): Promise<boolean>;

  getInstalledVersion(slug: string): Promise<string | null>;

  notifySkillChange?(
    geneName: string,
    action: 'installed' | 'updated' | 'uninstalled',
  ): Promise<void>;

  triggerLearning?(prompt: string): Promise<void>;
}
