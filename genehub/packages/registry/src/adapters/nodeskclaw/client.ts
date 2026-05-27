import postgres from 'postgres';
import type { NoDeskClawGeneRow } from './converter.js';

export type NoDeskClawClientOptions = {
  databaseUrl: string;
};

export type NoDeskClawGenomeRow = {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  short_description: string | null;
  icon: string | null;
  gene_slugs: string | null;
  config_override: string | null;
  install_count: number;
  avg_rating: number;
  is_published: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};

/**
 * Read-only client for NoDeskClaw's PostgreSQL database.
 * Used by the sync adapter to pull gene data into GeneHub.
 */
export class NoDeskClawClient {
  private sql: ReturnType<typeof postgres>;

  constructor(options: NoDeskClawClientOptions) {
    this.sql = postgres(options.databaseUrl, { max: 3 });
  }

  async fetchGenes(options?: { since?: string; limit?: number }): Promise<NoDeskClawGeneRow[]> {
    const limit = options?.limit ?? 1000;

    if (options?.since) {
      return this.sql<NoDeskClawGeneRow[]>`
        SELECT id, name, slug, version, description, short_description,
               category, tags, icon, source, source_ref, manifest,
               dependencies, synergies, parent_gene_id,
               install_count, avg_rating, effectiveness_score,
               review_status, is_published, created_by,
               created_at::text, updated_at::text
        FROM genes
        WHERE deleted_at IS NULL
          AND updated_at > ${options.since}
        ORDER BY updated_at ASC
        LIMIT ${limit}
      `;
    }

    return this.sql<NoDeskClawGeneRow[]>`
      SELECT id, name, slug, version, description, short_description,
             category, tags, icon, source, source_ref, manifest,
             dependencies, synergies, parent_gene_id,
             install_count, avg_rating, effectiveness_score,
             review_status, is_published, created_by,
             created_at::text, updated_at::text
      FROM genes
      WHERE deleted_at IS NULL
      ORDER BY updated_at ASC
      LIMIT ${limit}
    `;
  }

  async fetchGenomes(options?: { since?: string; limit?: number }): Promise<NoDeskClawGenomeRow[]> {
    const limit = options?.limit ?? 500;

    if (options?.since) {
      return this.sql<NoDeskClawGenomeRow[]>`
        SELECT id, name, slug, description, short_description, icon,
               gene_slugs, config_override,
               install_count, avg_rating, is_published, created_by,
               created_at::text, updated_at::text
        FROM genomes
        WHERE deleted_at IS NULL
          AND updated_at > ${options.since}
        ORDER BY updated_at ASC
        LIMIT ${limit}
      `;
    }

    return this.sql<NoDeskClawGenomeRow[]>`
      SELECT id, name, slug, description, short_description, icon,
             gene_slugs, config_override,
             install_count, avg_rating, is_published, created_by,
             created_at::text, updated_at::text
      FROM genomes
      WHERE deleted_at IS NULL
      ORDER BY updated_at ASC
      LIMIT ${limit}
    `;
  }

  async close() {
    await this.sql.end();
  }
}
