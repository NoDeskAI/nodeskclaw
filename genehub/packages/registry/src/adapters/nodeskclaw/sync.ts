import type { GeneManifest, GeneSource } from '@nodeskai/genehub-types';
import { eq } from 'drizzle-orm';
import { db, schema } from '../../db/index.js';
import type { InboundAdapter, SyncEvent, SyncOptions } from '../base.js';
import { NoDeskClawClient, type NoDeskClawClientOptions } from './client.js';
import { convertNoDeskClawGene, extractGeneMetadata, type NoDeskClawGeneRow } from './converter.js';

const { genes, geneVersions } = schema;

export class NoDeskClawAdapter implements InboundAdapter {
  readonly source: GeneSource = 'official';
  readonly displayName = 'NoDeskClaw';

  private client: NoDeskClawClient;

  constructor(options: NoDeskClawClientOptions) {
    this.client = new NoDeskClawClient(options);
  }

  convert(raw: unknown): GeneManifest {
    return convertNoDeskClawGene(raw as NoDeskClawGeneRow);
  }

  async *sync(options?: SyncOptions): AsyncGenerator<SyncEvent> {
    const rows = await this.client.fetchGenes({
      since: options?.full ? undefined : options?.since,
      limit: options?.limit,
    });

    for (const row of rows) {
      yield await this.upsertGene(row);
    }
  }

  private async upsertGene(row: NoDeskClawGeneRow): Promise<SyncEvent> {
    try {
      const manifest = convertNoDeskClawGene(row);
      const meta = extractGeneMetadata(row);

      const existing = await db
        .select({ id: genes.id, version: genes.version })
        .from(genes)
        .where(eq(genes.slug, row.slug));

      if (existing.length === 0) {
        return await this.insertNew(manifest, meta);
      }

      const current = existing[0];

      if (current.version === manifest.version) {
        return { kind: 'skipped', slug: row.slug, message: 'version unchanged' };
      }

      return await this.updateExisting(current.id, manifest, meta);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return { kind: 'failed', slug: row.slug, message };
    }
  }

  private async insertNew(
    manifest: GeneManifest,
    meta: ReturnType<typeof extractGeneMetadata>,
  ): Promise<SyncEvent> {
    const compatibility = manifest.compatibility.map((c) => c.product);

    const [gene] = await db
      .insert(genes)
      .values({
        name: manifest.name,
        slug: manifest.slug,
        version: manifest.version,
        description: manifest.description,
        short_description: manifest.short_description,
        category: manifest.category,
        tags: manifest.tags,
        icon: manifest.icon ?? null,
        manifest,
        compatibility,
        dependencies: manifest.dependencies,
        synergies: manifest.synergies,
        author: manifest.author ?? { type: 'human', name: '' },
        source: meta.source,
        source_ref: meta.source_ref,
        parent_gene_id: meta.parent_gene_id,
        install_count: meta.install_count,
        avg_rating: meta.avg_rating,
        effectiveness_score: meta.effectiveness_score,
        review_status: meta.review_status,
        is_published: meta.is_published,
      })
      .returning();

    await db.insert(geneVersions).values({
      gene_id: gene.id,
      version: manifest.version,
      manifest,
      changelog: 'Imported from NoDeskClaw',
      is_latest: true,
    });

    return { kind: 'created', slug: manifest.slug, version: manifest.version };
  }

  private async updateExisting(
    geneId: string,
    manifest: GeneManifest,
    meta: ReturnType<typeof extractGeneMetadata>,
  ): Promise<SyncEvent> {
    const compatibility = manifest.compatibility.map((c) => c.product);

    await db.update(geneVersions).set({ is_latest: false }).where(eq(geneVersions.gene_id, geneId));

    await db.insert(geneVersions).values({
      gene_id: geneId,
      version: manifest.version,
      manifest,
      changelog: 'Synced from NoDeskClaw',
      is_latest: true,
    });

    await db
      .update(genes)
      .set({
        version: manifest.version,
        name: manifest.name,
        description: manifest.description,
        short_description: manifest.short_description,
        category: manifest.category,
        tags: manifest.tags,
        icon: manifest.icon ?? null,
        manifest,
        compatibility,
        dependencies: manifest.dependencies,
        synergies: manifest.synergies,
        install_count: meta.install_count,
        avg_rating: meta.avg_rating,
        effectiveness_score: meta.effectiveness_score,
        updated_at: new Date(),
      })
      .where(eq(genes.id, geneId));

    return { kind: 'updated', slug: manifest.slug, version: manifest.version };
  }

  async close() {
    await this.client.close();
  }
}
