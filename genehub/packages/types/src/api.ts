import type {
  AgentTemplate,
  AgentTemplateVersion,
  Gene,
  GeneVersion,
  Genome,
  GenomeResolveResult,
  GenomeVersion,
} from './gene.js';

export type ApiResponse<T = unknown> = {
  code: number;
  message: string;
  data: T;
};

export type ApiErrorResponse = {
  code: number;
  error_code: string;
  message: string;
  data: null;
};

export type PaginatedData<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type GeneListParams = {
  q?: string;
  category?: string;
  tags?: string[];
  compatibility?: string;
  sort?: 'newest' | 'popular' | 'rating';
  page?: number;
  page_size?: number;
};

export type GeneListResponse = ApiResponse<PaginatedData<Gene>>;
export type GeneDetailResponse = ApiResponse<Gene>;
export type GeneManifestResponse = ApiResponse<Gene['manifest']>;
export type GeneVersionsResponse = ApiResponse<GeneVersion[]>;
export type GenomeListParams = {
  q?: string;
  category?: string;
  sort?: 'newest' | 'popular' | 'rating';
  page?: number;
  page_size?: number;
};

export type GenomeListResponse = ApiResponse<PaginatedData<Genome>>;
export type GenomeDetailResponse = ApiResponse<Genome>;
export type GenomeVersionsResponse = ApiResponse<GenomeVersion[]>;
export type GenomeResolveResponse = ApiResponse<GenomeResolveResult>;

export type CreateGenomeRequest = {
  name: string;
  slug: string;
  version: string;
  description?: string;
  short_description?: string;
  category?: string;
  tags?: string[];
  icon?: string;
  genes: { slug: string; version: string; config_override?: Record<string, unknown> }[];
  compatibility?: string[];
  author?: { type: string; id?: string; name: string };
  files?: Record<string, string>;
};

export type PublishGenomeVersionRequest = {
  version: string;
  genes: { slug: string; version: string; config_override?: Record<string, unknown> }[];
  changelog?: string;
  files?: Record<string, string>;
};

export type GenomeFileTreeResponse = ApiResponse<GeneFileEntry[]>;
export type GenomeFileContentResponse = ApiResponse<{ path: string; content: string }>;

export type FederatedSearchParams = {
  q: string;
  category?: string;
  limit?: number;
};

export type FederatedGeneItem = {
  slug: string;
  name: string;
  description: string | null;
  version: string | null;
  category: string | null;
  tags: string[];
  source: 'local' | 'clawhub';
  score: number;
  install_count: number | null;
  avg_rating: number | null;
  clawhub_display_name?: string;
};

export type FederatedSearchResult = {
  query: string;
  total: number;
  items: FederatedGeneItem[];
  sources: { local: number; clawhub: number };
};

export type FederatedSearchResponse = ApiResponse<FederatedSearchResult>;

export type AgentTemplateListParams = {
  q?: string;
  category?: string;
  role?: string;
  sort?: 'newest' | 'popular' | 'rating';
  page?: number;
  page_size?: number;
};

export type AgentTemplateListResponse = ApiResponse<PaginatedData<AgentTemplate>>;
export type AgentTemplateDetailResponse = ApiResponse<AgentTemplate>;
export type AgentTemplateVersionsResponse = ApiResponse<AgentTemplateVersion[]>;

export type CreateAgentTemplateRequest = {
  name: string;
  slug: string;
  version: string;
  description?: string;
  short_description?: string;
  role?: string;
  category?: string;
  tags?: string[];
  icon?: string;
  avatar_url?: string;
  genomes: { slug: string; version: string }[];
  genes?: { slug: string; version: string }[];
  compatibility?: string[];
  author?: { type: string; id?: string; name: string };
  files?: Record<string, string>;
};

export type PublishAgentTemplateVersionRequest = {
  version: string;
  genomes: { slug: string; version: string }[];
  genes?: { slug: string; version: string }[];
  changelog?: string;
  files?: Record<string, string>;
};

export type AgentTemplateFileTreeResponse = ApiResponse<GeneFileEntry[]>;
export type AgentTemplateFileContentResponse = ApiResponse<{ path: string; content: string }>;

export type GeneFileEntry = {
  path: string;
  size: number;
  sha: string;
  type: 'file' | 'dir';
};

export type GeneFileTreeResponse = ApiResponse<GeneFileEntry[]>;
export type GeneFileContentResponse = ApiResponse<{ path: string; content: string }>;

export type CreateGeneRequest = {
  manifest: Gene['manifest'];
  files?: Record<string, string>;
  source?: string;
  source_ref?: string;
};

export type ResolveRequest = {
  slug: string;
  version?: string;
  product?: string;
};

export type ResolvedGene = {
  slug: string;
  version: string;
  manifest: unknown;
  optional: boolean;
};

export type ResolveResponse = ApiResponse<{
  plan: ResolvedGene[];
  warnings: string[];
}>;

export type EffectivenessReport = {
  gene_slug: string;
  gene_version: string;
  product: string;
  instance_id: string;
  metric_type: 'user_positive' | 'user_negative' | 'agent_self_eval' | 'task_success';
  value: number;
  context?: string;
  timestamp: string;
};

export const ERROR_CODES = {
  TOKEN_INVALID: 10001,
  TOKEN_EXPIRED: 10002,
  PERMISSION_DENIED: 10003,
  GENE_NOT_FOUND: 20001,
  GENE_VERSION_CONFLICT: 20002,
  GENE_SLUG_EXISTS: 20003,
  GENE_MANIFEST_INVALID: 20004,
  GENE_VERSION_NOT_FOUND: 20005,
  GENOME_NOT_FOUND: 30001,
  GENOME_SLUG_EXISTS: 30002,
  GENOME_VERSION_CONFLICT: 30003,
  GENOME_VALIDATION_FAILED: 30004,
  GENOME_VERSION_NOT_FOUND: 30005,
  TEMPLATE_NOT_FOUND: 60001,
  TEMPLATE_SLUG_EXISTS: 60002,
  TEMPLATE_VERSION_CONFLICT: 60003,
  TEMPLATE_VALIDATION_FAILED: 60004,
  TEMPLATE_VERSION_NOT_FOUND: 60005,
  DEPENDENCY_RESOLVE_FAILED: 40001,
  COMPATIBILITY_MISMATCH: 40002,
  GITEA_UNAVAILABLE: 50101,
  GITEA_REPO_ERROR: 50102,
  LEARNING_TASK_TIMEOUT: 50001,
  LEARNING_CALLBACK_FAILED: 50002,
  INTERNAL_ERROR: 90001,
} as const;
