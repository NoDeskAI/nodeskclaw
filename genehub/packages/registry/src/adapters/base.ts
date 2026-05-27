import type { GeneManifest, GeneSource } from '@nodeskai/genehub-types';

export type SyncOptions = {
  /** Full sync ignores incremental state and re-imports everything. */
  full?: boolean;
  /** Only sync genes updated after this ISO timestamp. */
  since?: string;
  /** Maximum number of genes to import in one run. */
  limit?: number;
};

export type SyncEventKind = 'created' | 'updated' | 'skipped' | 'failed';

export type SyncEvent = {
  kind: SyncEventKind;
  slug: string;
  version?: string;
  message?: string;
};

export type SyncResult = {
  source: GeneSource;
  created: number;
  updated: number;
  skipped: number;
  failed: number;
  events: SyncEvent[];
  started_at: string;
  finished_at: string;
};

/**
 * InboundAdapter — contract for pulling genes from an external source into
 * GeneHub Registry. Each external ecosystem (NoDeskClaw, ClawHub, EvoMap, …)
 * implements this interface so the sync / import layer stays source-agnostic.
 */
export interface InboundAdapter {
  readonly source: GeneSource;
  readonly displayName: string;

  /**
   * Convert a raw gene record from the external source into a GeneHub
   * GeneManifest.  The implementation is responsible for field mapping,
   * data normalisation and sensible defaults.
   */
  convert(raw: unknown): GeneManifest;

  /**
   * Yield sync events as genes are imported.  Callers can iterate
   * the generator to stream progress updates back to the client.
   */
  sync(options?: SyncOptions): AsyncGenerator<SyncEvent>;
}
