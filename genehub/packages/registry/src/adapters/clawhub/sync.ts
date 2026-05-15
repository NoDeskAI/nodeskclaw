import type { GeneManifest, GeneSource } from '@nodeskai/genehub-types';
import { eq } from 'drizzle-orm';
import { db, schema } from '../../db/index.js';
import type { InboundAdapter, SyncEvent, SyncOptions } from '../base.js';
import { ClawHubClient, type ClawHubClientOptions, type ClawHubSkillListItem } from './client.js';
import {
  type ClawHubSkillPayload,
  convertClawHubSkill,
  extractClawHubMetadata,
  isSkillSafe,
} from './converter.js';

const { genes, geneVersions } = schema;

export class ClawHubAdapter implements InboundAdapter {
  readonly source: GeneSource = 'clawhub';
  readonly displayName = 'ClawHub';

  private client: ClawHubClient;

  constructor(options?: ClawHubClientOptions) {
    this.client = new ClawHubClient(options);
  }

  convert(raw: unknown): GeneManifest {
    return convertClawHubSkill(raw as ClawHubSkillPayload);
  }

  async *sync(options?: SyncOptions): AsyncGenerator<SyncEvent> {
    let processed = 0;
    const limit = options?.limit ?? Infinity;

    for await (const page of this.client.listAllSkills()) {
      for (const item of page) {
        if (processed >= limit) return;

        if (options?.since && !options.full) {
          const updatedAt = new Date(item.updatedAt).toISOString();
          if (updatedAt <= options.since) continue;
        }

        yield await this.processSkill(item);
        processed++;
      }
    }
  }

  private async processSkill(item: ClawHubSkillListItem): Promise<SyncEvent> {
    try {
      const detail = await this.client.getSkill(item.slug);
      if (!detail.skill) {
        return { kind: 'skipped', slug: item.slug, message: 'skill not found in detail' };
      }

      const versionStr = detail.latestVersion?.version;
      let versionInfo = null;
      if (versionStr) {
        versionInfo = await this.client.getSkillVersion(item.slug, versionStr);

        if (!isSkillSafe(versionInfo)) {
          return {
            kind: 'skipped',
            slug: item.slug,
            message: `security status: ${versionInfo.version?.security?.status ?? 'unknown'}`,
          };
        }
      }

      let instructionsContent = '';
      if (versionStr) {
        try {
          instructionsContent = await this.client.downloadFile(item.slug, versionStr);
        } catch {
          // non-fatal — some skills don't have downloadable content
        }
      }

      const payload: ClawHubSkillPayload = {
        detail,
        version: versionInfo,
        instructionsContent,
      };

      return await this.upsertGene(payload);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return { kind: 'failed', slug: item.slug, message };
    }
  }

  private async upsertGene(payload: ClawHubSkillPayload): Promise<SyncEvent> {
    const manifest = convertClawHubSkill(payload);
    const meta = extractClawHubMetadata(payload);

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
  }

  private async insertNew(
    manifest: GeneManifest,
    meta: ReturnType<typeof extractClawHubMetadata>,
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
      changelog: 'Imported from ClawHub',
      is_latest: true,
    });

    return { kind: 'created', slug: manifest.slug, version: manifest.version };
  }

  private async updateExisting(
    geneId: string,
    manifest: GeneManifest,
    meta: ReturnType<typeof extractClawHubMetadata>,
  ): Promise<SyncEvent> {
    const compatibility = manifest.compatibility.map((c) => c.product);

    await db.update(geneVersions).set({ is_latest: false }).where(eq(geneVersions.gene_id, geneId));

    await db.insert(geneVersions).values({
      gene_id: geneId,
      version: manifest.version,
      manifest,
      changelog: 'Synced from ClawHub',
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
