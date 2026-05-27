import type { GeneManifest, GeneSource } from '@nodeskai/genehub-types';
import { eq } from 'drizzle-orm';
import { db, schema } from '../../db/index.js';
import type { InboundAdapter, SyncEvent, SyncOptions } from '../base.js';
import {
  type AgentCapabilityProfile,
  EvoMapClient,
  type EvoMapClientOptions,
  type RecommendationItem,
} from './client.js';
import { convertRecommendation, extractEvoMapMetadata } from './converter.js';

const { genes, geneVersions } = schema;

export type EvoMapAdapterOptions = EvoMapClientOptions & {
  profile?: AgentCapabilityProfile;
};

export class EvoMapAdapter implements InboundAdapter {
  readonly source: GeneSource = 'evomap';
  readonly displayName = 'EvoMap';

  private client: EvoMapClient;
  private profile: AgentCapabilityProfile;

  constructor(options: EvoMapAdapterOptions = {}) {
    this.client = new EvoMapClient(options);
    this.profile = options.profile ?? {
      product: 'genehub',
      installed_genes: [],
    };
  }

  convert(raw: unknown): GeneManifest {
    return convertRecommendation(raw as RecommendationItem);
  }

  async *sync(options?: SyncOptions): AsyncGenerator<SyncEvent> {
    let processed = 0;
    const limit = options?.limit ?? Infinity;

    const response = await this.client.recommend(this.profile);

    for (const item of response.recommendations) {
      if (processed >= limit) return;
      yield await this.processRecommendation(item);
      processed++;
    }
  }

  private async processRecommendation(item: RecommendationItem): Promise<SyncEvent> {
    try {
      const manifest = convertRecommendation(item);
      const meta = extractEvoMapMetadata(item);

      const existing = await db
        .select({ id: genes.id, version: genes.version })
        .from(genes)
        .where(eq(genes.slug, manifest.slug));

      if (existing.length === 0) {
        return await this.insertNew(manifest, meta);
      }

      const current = existing[0];
      if (current.version === manifest.version) {
        return { kind: 'skipped', slug: manifest.slug, message: 'version unchanged' };
      }

      return await this.updateExisting(current.id, manifest, meta);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return { kind: 'failed', slug: item.id, message };
    }
  }

  private async insertNew(
    manifest: GeneManifest,
    meta: ReturnType<typeof extractEvoMapMetadata>,
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
        author: manifest.author ?? { type: 'agent', name: 'EvoMap' },
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
      changelog: 'Recommended by EvoMap Evolver',
      is_latest: true,
    });

    return { kind: 'created', slug: manifest.slug, version: manifest.version };
  }

  private async updateExisting(
    geneId: string,
    manifest: GeneManifest,
    meta: ReturnType<typeof extractEvoMapMetadata>,
  ): Promise<SyncEvent> {
    const compatibility = manifest.compatibility.map((c) => c.product);

    await db.update(geneVersions).set({ is_latest: false }).where(eq(geneVersions.gene_id, geneId));

    await db.insert(geneVersions).values({
      gene_id: geneId,
      version: manifest.version,
      manifest,
      changelog: 'Updated via EvoMap recommendation',
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
}
