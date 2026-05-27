import type { GeneSource, ReviewStatus } from './enums.js';
import type { Author, GeneManifest } from './manifest.js';

export type Gene = {
  id: string;
  name: string;
  slug: string;
  version: string;
  description: string;
  short_description: string;
  category: string;
  tags: string[];
  icon: string | null;
  source: GeneSource;
  source_ref: string | null;
  manifest: GeneManifest;
  compatibility: string[];
  dependencies: { slug: string; version: string }[];
  synergies: string[];
  parent_gene_id: string | null;
  author: Author;
  install_count: number;
  avg_rating: number;
  effectiveness_score: number;
  review_status: ReviewStatus;
  ai_score: number | null;
  ai_verdict: string | null;
  ai_enriched: boolean;
  publisher_id: string | null;
  is_published: boolean;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
};

export type Publisher = {
  id: string;
  github_id: number;
  github_login: string;
  github_name: string;
  github_avatar_url: string;
  github_profile_url: string;
  created_at: string;
  last_login_at: string;
};

export type ApiKey = {
  id: string;
  publisher_id: string;
  token_prefix: string;
  name: string;
  last_used_at: string | null;
  created_at: string;
  revoked_at: string | null;
};

export type GenomeGeneRef = {
  slug: string;
  version: string;
  config_override?: Record<string, unknown>;
};

export type Genome = {
  id: string;
  name: string;
  slug: string;
  version: string;
  description: string;
  short_description: string;
  category: string;
  tags: string[];
  icon: string | null;
  genes: GenomeGeneRef[];
  compatibility: string[];
  install_count: number;
  avg_rating: number;
  author: Author;
  repository_url: string | null;
  file_count: number;
  is_published: boolean;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
};

export type GenomeVersion = {
  id: string;
  genome_id: string;
  version: string;
  genes: GenomeGeneRef[];
  commit_sha: string | null;
  git_tag: string | null;
  files: { path: string; size: number; sha: string }[] | null;
  changelog: string;
  is_latest: boolean;
  published_at: string;
};

export type GenomeResolveResult = {
  genome: { slug: string; name: string; version: string };
  genes: {
    slug: string;
    version: string;
    manifest: unknown;
    config_override?: Record<string, unknown>;
    resolved_from: 'direct' | 'dependency';
  }[];
  compatibility: string[];
  conflicts: string[];
  warnings: string[];
};

export type GeneReview = {
  id: string;
  gene_id: string;
  reviewer: string;
  score: number | null;
  verdict: string | null;
  comments: string[];
  changes_made: Record<string, unknown> | null;
  feedback: string | null;
  model: string | null;
  created_at: string;
};

export type GeneRelation = {
  id: string;
  source_gene_id: string;
  target_gene_id: string;
  relation_type: 'synergy' | 'conflict' | 'extends' | 'replaces';
  strength: number;
  reason: string | null;
  created_by: string;
  created_at: string;
};

export type AgentTemplateGeneRef = {
  slug: string;
  version: string;
};

export type AgentTemplate = {
  id: string;
  name: string;
  slug: string;
  version: string;
  description: string;
  short_description: string;
  role: string | null;
  category: string;
  tags: string[];
  icon: string | null;
  avatar_url: string | null;
  genomes: AgentTemplateGeneRef[];
  genes: AgentTemplateGeneRef[];
  compatibility: string[];
  install_count: number;
  avg_rating: number;
  author: Author;
  publisher_id: string | null;
  repository_url: string | null;
  file_count: number;
  is_published: boolean;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
};

export type AgentTemplateVersion = {
  id: string;
  template_id: string;
  version: string;
  genomes: AgentTemplateGeneRef[];
  genes: AgentTemplateGeneRef[];
  commit_sha: string | null;
  git_tag: string | null;
  files: { path: string; size: number; sha: string }[] | null;
  changelog: string;
  is_latest: boolean;
  published_at: string;
};

export type GeneVersion = {
  id: string;
  gene_id: string;
  version: string;
  manifest: GeneManifest;
  changelog: string;
  is_latest: boolean;
  published_at: string;
};
