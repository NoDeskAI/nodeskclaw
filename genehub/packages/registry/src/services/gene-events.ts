import { sql } from 'drizzle-orm';
import { db } from '../db/index.js';

export type GeneEventType = 'gene.created' | 'gene.updated' | 'gene.flagged' | 'gene.reviewed';
export type GenomeEventType = 'genome.created' | 'genome.updated';
export type TemplateEventType = 'template.created' | 'template.updated';

export type GeneHubEvent = {
  type: GeneEventType | GenomeEventType | TemplateEventType;
  slug: string;
  source: string;
  timestamp: string;
  meta?: Record<string, unknown>;
};

async function emitToChannel(channel: string, payload: GeneHubEvent) {
  try {
    await db.execute(sql`SELECT pg_notify(${channel}, ${JSON.stringify(payload)})`);
  } catch (err) {
    console.error(
      `[events] Failed to emit ${payload.type} for ${payload.slug} on ${channel}:`,
      err,
    );
  }
}

export async function emitGeneEvent(
  type: GeneEventType,
  slug: string,
  source: string,
  meta?: Record<string, unknown>,
) {
  await emitToChannel('gene_events', {
    type,
    slug,
    source,
    timestamp: new Date().toISOString(),
    meta,
  });
}

export async function emitGenomeEvent(
  type: GenomeEventType,
  slug: string,
  source: string,
  meta?: Record<string, unknown>,
) {
  await emitToChannel('gene_events', {
    type,
    slug,
    source,
    timestamp: new Date().toISOString(),
    meta,
  });
}

export async function emitTemplateEvent(
  type: TemplateEventType,
  slug: string,
  source: string,
  meta?: Record<string, unknown>,
) {
  await emitToChannel('gene_events', {
    type,
    slug,
    source,
    timestamp: new Date().toISOString(),
    meta,
  });
}
