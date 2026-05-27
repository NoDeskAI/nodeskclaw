const BASE = '/api/v1';

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
  source: string;
  source_ref: string | null;
  compatibility: string[];
  dependencies: { slug: string; version: string }[];
  synergies: string[];
  author: { type: string; name: string };
  install_count: number;
  avg_rating: number;
  effectiveness_score: number;
  review_status: string;
  ai_score: number | null;
  ai_verdict: string | null;
  ai_enriched: boolean;
  publisher_id: string | null;
  is_published: boolean;
  manifest: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type GeneVersion = {
  id: string;
  version: string;
  changelog: string;
  is_latest: boolean;
  published_at: string;
  commit_sha: string | null;
  git_tag: string | null;
  files: { path: string; size: number; sha: string }[] | null;
};

export type GeneReview = {
  id: string;
  gene_id: string | null;
  entity_type: string;
  entity_slug: string | null;
  reviewer: string;
  score: number | null;
  verdict: string | null;
  comments: string[];
  changes_made: Record<string, unknown> | null;
  feedback: string | null;
  model: string | null;
  created_at: string;
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
  genes: { slug: string; version: string; config_override?: Record<string, unknown> }[];
  compatibility: string[];
  install_count: number;
  avg_rating: number;
  author: { type: string; name: string };
  is_published: boolean;
  created_at: string;
  updated_at: string;
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

type ApiResponse<T> = { code: number; message: string; data: T };
export type PagedData<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`API ${res.status}`);
  const json: ApiResponse<T> = await res.json();
  if (json.code !== 0) throw new Error(json.message);
  return json.data;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API ${res.status}`);
  const json: ApiResponse<T> = await res.json();
  if (json.code !== 0) throw new Error(json.message);
  return json.data;
}

export async function listGenes(params?: {
  q?: string;
  category?: string;
  compatibility?: string;
  tag?: string;
  sort?: string;
  page?: number;
  page_size?: number;
  review_status?: string;
  include_unpublished?: boolean;
}): Promise<PagedData<Gene>> {
  const sp = new URLSearchParams();
  if (params?.q) sp.set('q', params.q);
  if (params?.category) sp.set('category', params.category);
  if (params?.compatibility) sp.set('compatibility', params.compatibility);
  if (params?.tag) sp.set('tags', params.tag);
  if (params?.sort) sp.set('sort', params.sort);
  if (params?.page) sp.set('page', String(params.page));
  if (params?.page_size) sp.set('page_size', String(params.page_size));
  if (params?.review_status) sp.set('review_status', params.review_status);
  if (params?.include_unpublished) sp.set('include_unpublished', 'true');
  const qs = sp.toString();
  return get<PagedData<Gene>>(`/genes${qs ? `?${qs}` : ''}`);
}

export async function getGene(slug: string): Promise<Gene> {
  return get<Gene>(`/genes/${slug}`);
}

export async function getGeneVersions(slug: string): Promise<GeneVersion[]> {
  return get<GeneVersion[]>(`/genes/${slug}/versions`);
}

export async function getGeneReviews(
  slug: string,
  params?: { page?: number; page_size?: number },
): Promise<PagedData<GeneReview>> {
  const sp = new URLSearchParams();
  if (params?.page) sp.set('page', String(params.page));
  if (params?.page_size) sp.set('page_size', String(params.page_size));
  const qs = sp.toString();
  return get<PagedData<GeneReview>>(`/genes/${slug}/reviews${qs ? `?${qs}` : ''}`);
}

export async function listGenomes(params?: {
  q?: string;
  category?: string;
  sort?: string;
  page?: number;
  page_size?: number;
  include_unpublished?: boolean;
}): Promise<PagedData<Genome>> {
  const sp = new URLSearchParams();
  if (params?.q) sp.set('q', params.q);
  if (params?.category) sp.set('category', params.category);
  if (params?.sort) sp.set('sort', params.sort);
  if (params?.page) sp.set('page', String(params.page));
  if (params?.page_size) sp.set('page_size', String(params.page_size));
  if (params?.include_unpublished) sp.set('include_unpublished', 'true');
  const qs = sp.toString();
  return get<PagedData<Genome>>(`/genomes${qs ? `?${qs}` : ''}`);
}

export async function getGenome(slug: string): Promise<Genome> {
  return get<Genome>(`/genomes/${slug}`);
}

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
  genomes: { slug: string; version: string }[];
  genes: { slug: string; version: string }[];
  compatibility: string[];
  install_count: number;
  avg_rating: number;
  author: { type: string; name: string };
  is_published: boolean;
  created_at: string;
  updated_at: string;
};

export async function listTemplates(params?: {
  q?: string;
  category?: string;
  role?: string;
  sort?: string;
  page?: number;
  page_size?: number;
  include_unpublished?: boolean;
}): Promise<PagedData<AgentTemplate>> {
  const sp = new URLSearchParams();
  if (params?.q) sp.set('q', params.q);
  if (params?.category) sp.set('category', params.category);
  if (params?.role) sp.set('role', params.role);
  if (params?.sort) sp.set('sort', params.sort);
  if (params?.page) sp.set('page', String(params.page));
  if (params?.page_size) sp.set('page_size', String(params.page_size));
  if (params?.include_unpublished) sp.set('include_unpublished', 'true');
  const qs = sp.toString();
  return get<PagedData<AgentTemplate>>(`/templates${qs ? `?${qs}` : ''}`);
}

export async function getTemplate(slug: string): Promise<AgentTemplate> {
  return get<AgentTemplate>(`/templates/${slug}`);
}

export type GeneFileEntry = {
  path: string;
  size: number;
  sha: string;
  type: string;
};

export async function getGeneFiles(slug: string, version?: string): Promise<GeneFileEntry[]> {
  const qs = version ? `?version=${encodeURIComponent(version)}` : '';
  return get<GeneFileEntry[]>(`/genes/${slug}/files${qs}`);
}

export async function getGeneFileContent(
  slug: string,
  filePath: string,
  version?: string,
): Promise<{ path: string; content: string }> {
  const qs = version ? `?version=${encodeURIComponent(version)}` : '';
  return get<{ path: string; content: string }>(`/genes/${slug}/files/${filePath}${qs}`);
}

export async function federatedSearch(params: {
  q: string;
  category?: string;
  limit?: number;
}): Promise<FederatedSearchResult> {
  const sp = new URLSearchParams();
  sp.set('q', params.q);
  if (params.category) sp.set('category', params.category);
  if (params.limit) sp.set('limit', String(params.limit));
  return get<FederatedSearchResult>(`/genes/search?${sp.toString()}`);
}

export async function getGenomeVersions(slug: string): Promise<GeneVersion[]> {
  return get<GeneVersion[]>(`/genomes/${slug}/versions`);
}

export async function getGenomeFiles(slug: string, version?: string): Promise<GeneFileEntry[]> {
  const qs = version ? `?version=${encodeURIComponent(version)}` : '';
  return get<GeneFileEntry[]>(`/genomes/${slug}/files${qs}`);
}

export async function getGenomeFileContent(
  slug: string,
  filePath: string,
  version?: string,
): Promise<{ path: string; content: string }> {
  const qs = version ? `?version=${encodeURIComponent(version)}` : '';
  return get<{ path: string; content: string }>(`/genomes/${slug}/files/${filePath}${qs}`);
}

export async function getGenomeReviews(
  slug: string,
  params?: { page?: number; page_size?: number },
): Promise<PagedData<GeneReview>> {
  const sp = new URLSearchParams();
  if (params?.page) sp.set('page', String(params.page));
  if (params?.page_size) sp.set('page_size', String(params.page_size));
  const qs = sp.toString();
  return get<PagedData<GeneReview>>(`/genomes/${slug}/reviews${qs ? `?${qs}` : ''}`);
}

export async function getTemplateVersions(slug: string): Promise<GeneVersion[]> {
  return get<GeneVersion[]>(`/templates/${slug}/versions`);
}

export async function getTemplateFiles(slug: string, version?: string): Promise<GeneFileEntry[]> {
  const qs = version ? `?version=${encodeURIComponent(version)}` : '';
  return get<GeneFileEntry[]>(`/templates/${slug}/files${qs}`);
}

export async function getTemplateFileContent(
  slug: string,
  filePath: string,
  version?: string,
): Promise<{ path: string; content: string }> {
  const qs = version ? `?version=${encodeURIComponent(version)}` : '';
  return get<{ path: string; content: string }>(`/templates/${slug}/files/${filePath}${qs}`);
}

export async function getTemplateReviews(
  slug: string,
  params?: { page?: number; page_size?: number },
): Promise<PagedData<GeneReview>> {
  const sp = new URLSearchParams();
  if (params?.page) sp.set('page', String(params.page));
  if (params?.page_size) sp.set('page_size', String(params.page_size));
  const qs = sp.toString();
  return get<PagedData<GeneReview>>(`/templates/${slug}/reviews${qs ? `?${qs}` : ''}`);
}

export type ReviewPayload = {
  score?: number;
  verdict: string;
  comments?: string[];
};

const REVIEW_ENTITY_PREFIX: Record<string, string> = {
  gene: '/genes',
  genome: '/genomes',
  template: '/templates',
};

export async function submitReview(
  entityType: string,
  slug: string,
  payload: ReviewPayload,
): Promise<GeneReview> {
  const prefix = REVIEW_ENTITY_PREFIX[entityType] ?? '/genes';
  return post<GeneReview>(`${prefix}/${slug}/reviews`, payload);
}
