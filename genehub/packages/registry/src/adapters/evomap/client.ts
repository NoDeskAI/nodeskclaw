/**
 * HTTP client for the EvoMap platform API (evomap.ai).
 *
 * EvoMap implements the Genome Evolution Protocol (GEP). Core concepts:
 *   - Gene   — atomic, reusable capability unit
 *   - Capsule — packaged successful execution path (composite solution)
 *   - Event  — immutable evolution log entry
 *
 * Uses native `fetch` — no external HTTP dependencies required.
 */

// ---------------------------------------------------------------------------
// GEP data types
// ---------------------------------------------------------------------------

export type GepGene = {
  type: 'Gene';
  id: string;
  category: string;
  signals_match: string[];
  preconditions: string[];
  strategy: string[];
  constraints?: {
    max_files?: number;
    forbidden_paths?: string[];
  };
  validation?: string[];
};

export type GepCapsule = {
  type: 'Capsule';
  schema_version?: string;
  id: string;
  trigger: string[];
  gene: string;
  summary: string;
  confidence: number;
  blast_radius?: { files: number; lines: number };
  outcome?: { status: string; score: number };
  success_streak?: number;
  env_fingerprint?: Record<string, unknown>;
  a2a?: { eligible_to_broadcast: boolean };
  asset_id?: string;
};

export type GepEvent = {
  type: 'Event';
  id: string;
  gene_id: string;
  capsule_id?: string;
  intent: string;
  signals: string[];
  changes: Array<{ file: string; lines: number }>;
  outcome: string;
  timestamp: string;
};

// ---------------------------------------------------------------------------
// API response types
// ---------------------------------------------------------------------------

export type EvoMapGenesResponse = {
  version: number;
  genes: GepGene[];
};

export type EvoMapCapsulesResponse = {
  version: number;
  capsules: GepCapsule[];
};

export type AgentCapabilityProfile = {
  agent_id?: string;
  product: string;
  installed_genes: string[];
  performance_signals?: string[];
  context?: Record<string, unknown>;
};

export type RecommendationItem = {
  type: 'gene' | 'capsule';
  id: string;
  score: number;
  reason: string;
  data: GepGene | GepCapsule;
};

export type EvoMapRecommendResponse = {
  request_id: string;
  recommendations: RecommendationItem[];
};

export type EvoMapFeedbackPayload = {
  request_id: string;
  gene_slug: string;
  outcome: 'success' | 'failure' | 'partial';
  score?: number;
  signals?: string[];
};

// ---------------------------------------------------------------------------
// Client options
// ---------------------------------------------------------------------------

export type EvoMapClientOptions = {
  /** Base URL, defaults to https://evomap.ai */
  baseUrl?: string;
  /** API key for authentication */
  apiKey?: string;
  /** Request timeout in ms (default 20 000) */
  timeoutMs?: number;
};

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

export class EvoMapClient {
  private baseUrl: string;
  private headers: Record<string, string>;
  private timeoutMs: number;

  constructor(options: EvoMapClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? 'https://evomap.ai').replace(/\/$/, '');
    this.timeoutMs = options.timeoutMs ?? 20_000;
    this.headers = {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    };
    if (options.apiKey) {
      this.headers['X-Api-Key'] = options.apiKey;
    }
  }

  // -------------------------------------------------------------------------
  // Gene catalogue
  // -------------------------------------------------------------------------

  async listGenes(): Promise<EvoMapGenesResponse> {
    return this.get<EvoMapGenesResponse>('/api/v1/genes');
  }

  async getGene(id: string): Promise<GepGene> {
    return this.get<GepGene>(`/api/v1/genes/${encodeURIComponent(id)}`);
  }

  // -------------------------------------------------------------------------
  // Capsule catalogue
  // -------------------------------------------------------------------------

  async listCapsules(): Promise<EvoMapCapsulesResponse> {
    return this.get<EvoMapCapsulesResponse>('/api/v1/capsules');
  }

  async getCapsule(id: string): Promise<GepCapsule> {
    return this.get<GepCapsule>(`/api/v1/capsules/${encodeURIComponent(id)}`);
  }

  // -------------------------------------------------------------------------
  // Recommendation — the core Evomap interaction
  // -------------------------------------------------------------------------

  async recommend(profile: AgentCapabilityProfile): Promise<EvoMapRecommendResponse> {
    return this.post<EvoMapRecommendResponse>('/api/v1/recommend', profile);
  }

  // -------------------------------------------------------------------------
  // Feedback — report performance data back to Evolver
  // -------------------------------------------------------------------------

  async feedback(payload: EvoMapFeedbackPayload): Promise<{ ok: boolean }> {
    return this.post<{ ok: boolean }>('/api/v1/feedback', payload);
  }

  // -------------------------------------------------------------------------
  // Internal helpers
  // -------------------------------------------------------------------------

  private async get<T>(path: string): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const res = await this.fetchWithTimeout(url, { method: 'GET' });
    if (!res.ok) {
      throw new EvoMapApiError(res.status, `GET ${path} failed`);
    }
    return (await res.json()) as T;
  }

  private async post<T>(path: string, body: unknown): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const res = await this.fetchWithTimeout(url, {
      method: 'POST',
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      throw new EvoMapApiError(res.status, `POST ${path} failed`);
    }
    return (await res.json()) as T;
  }

  private async fetchWithTimeout(url: string, init: RequestInit): Promise<Response> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      return await fetch(url, {
        ...init,
        headers: this.headers,
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timer);
    }
  }
}

// ---------------------------------------------------------------------------
// Error class
// ---------------------------------------------------------------------------

export class EvoMapApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(`EvoMap API ${status}: ${message}`);
    this.name = 'EvoMapApiError';
  }
}
