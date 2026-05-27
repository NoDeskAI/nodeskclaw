import type {
  AgentTemplate,
  AgentTemplateListParams,
  AgentTemplateVersion,
  ApiResponse,
  CreateAgentTemplateRequest,
  CreateGenomeRequest,
  FederatedSearchParams,
  FederatedSearchResult,
  Gene,
  GeneListParams,
  GeneManifest,
  GeneVersion,
  Genome,
  GenomeListParams,
  GenomeResolveResult,
  GenomeVersion,
  PaginatedData,
  PublishAgentTemplateVersionRequest,
  PublishGenomeVersionRequest,
  ResolvedGene,
} from '@nodeskai/genehub-types';

export type GeneHubClientOptions = {
  registryUrl: string;
  token?: string;
};

export class GeneHubClient {
  private baseUrl: string;
  private token?: string;

  constructor(options: GeneHubClientOptions) {
    this.baseUrl = options.registryUrl.replace(/\/$/, '');
    this.token = options.token;
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(init?.headers as Record<string, string>),
    };

    if (this.token) {
      headers.Authorization = `Bearer ${this.token}`;
    }

    const res = await fetch(`${this.baseUrl}${path}`, { ...init, headers });

    const json = (await res.json()) as ApiResponse<T> & { error_code?: string };

    if (!res.ok || json.code !== 0) {
      const msg = json.message || `HTTP ${res.status}`;
      throw new Error(`[GeneHub] ${json.error_code ?? 'error'}: ${msg}`);
    }

    return json.data;
  }

  // ── Gene ──

  async searchGenes(params: GeneListParams = {}): Promise<PaginatedData<Gene>> {
    const qs = new URLSearchParams();
    if (params.q) qs.set('q', params.q);
    if (params.category) qs.set('category', params.category);
    if (params.tags?.length) qs.set('tags', params.tags.join(','));
    if (params.compatibility) qs.set('compatibility', params.compatibility);
    if (params.sort) qs.set('sort', params.sort);
    if (params.page) qs.set('page', String(params.page));
    if (params.page_size) qs.set('page_size', String(params.page_size));

    const query = qs.toString();
    return this.request<PaginatedData<Gene>>(`/api/v1/genes${query ? `?${query}` : ''}`);
  }

  /** 联邦搜索：合并本地 DB 与外部源（如 ClawHub）结果 */
  async federatedSearch(params: FederatedSearchParams): Promise<FederatedSearchResult> {
    const qs = new URLSearchParams();
    qs.set('q', params.q);
    if (params.category) qs.set('category', params.category);
    if (Number.isFinite(params.limit) && (params.limit as number) > 0) {
      qs.set('limit', String(params.limit));
    }
    return this.request<FederatedSearchResult>(`/api/v1/genes/search?${qs.toString()}`);
  }

  async getGene(slug: string): Promise<Gene> {
    return this.request<Gene>(`/api/v1/genes/${slug}`);
  }

  async getManifest(slug: string, version?: string): Promise<GeneManifest> {
    const qs = version ? `?version=${encodeURIComponent(version)}` : '';
    return this.request<GeneManifest>(`/api/v1/genes/${slug}/manifest${qs}`);
  }

  async getVersions(slug: string): Promise<GeneVersion[]> {
    return this.request<GeneVersion[]>(`/api/v1/genes/${slug}/versions`);
  }

  async getVersion(slug: string, version: string): Promise<GeneVersion> {
    return this.request<GeneVersion>(`/api/v1/genes/${slug}/versions/${version}`);
  }

  async publishGene(manifest: GeneManifest, files?: Record<string, string>): Promise<Gene> {
    return this.request<Gene>('/api/v1/genes', {
      method: 'POST',
      body: JSON.stringify({ manifest, files }),
    });
  }

  async publishVersion(
    slug: string,
    manifest: GeneManifest,
    changelog?: string,
    files?: Record<string, string>,
  ): Promise<Gene> {
    return this.request<Gene>(`/api/v1/genes/${slug}/versions`, {
      method: 'POST',
      body: JSON.stringify({ manifest, changelog, files }),
    });
  }

  async getGeneFiles(
    slug: string,
    version?: string,
  ): Promise<{ path: string; size: number; sha: string; type: string }[]> {
    const qs = version ? `?version=${encodeURIComponent(version)}` : '';
    return this.request(`/api/v1/genes/${slug}/files${qs}`);
  }

  async getGeneFileContent(
    slug: string,
    filePath: string,
    version?: string,
  ): Promise<{ path: string; content: string }> {
    const qs = version ? `?version=${encodeURIComponent(version)}` : '';
    return this.request(`/api/v1/genes/${slug}/files/${filePath}${qs}`);
  }

  async downloadArchive(slug: string, version?: string): Promise<ArrayBuffer> {
    const qs = version ? `?version=${encodeURIComponent(version)}` : '';
    const url = `${this.baseUrl}/api/v1/genes/${slug}/archive${qs}`;
    const headers: Record<string, string> = {};
    if (this.token) {
      headers.Authorization = `Bearer ${this.token}`;
    }
    const res = await fetch(url, { headers });
    if (!res.ok) {
      throw new Error(`[GeneHub] Download archive failed: HTTP ${res.status}`);
    }
    return res.arrayBuffer();
  }

  async resolve(
    slug: string,
    version?: string,
    product?: string,
  ): Promise<{ plan: ResolvedGene[]; warnings: string[] }> {
    return this.request(`/api/v1/resolve`, {
      method: 'POST',
      body: JSON.stringify({ slug, version, product }),
    });
  }

  async reportInstall(slug: string): Promise<void> {
    await this.request(`/api/v1/genes/${slug}/installed`, { method: 'POST', body: '{}' });
  }

  async reportEffectiveness(
    slug: string,
    report: { metric_type: string; value: number; context?: string },
  ): Promise<void> {
    await this.request(`/api/v1/genes/${slug}/effectiveness`, {
      method: 'POST',
      body: JSON.stringify(report),
    });
  }

  // ── Genome ──

  async searchGenomes(params: GenomeListParams = {}): Promise<PaginatedData<Genome>> {
    const qs = new URLSearchParams();
    if (params.q) qs.set('q', params.q);
    if (params.category) qs.set('category', params.category);
    if (params.sort) qs.set('sort', params.sort);
    if (params.page) qs.set('page', String(params.page));
    if (params.page_size) qs.set('page_size', String(params.page_size));

    const query = qs.toString();
    return this.request<PaginatedData<Genome>>(`/api/v1/genomes${query ? `?${query}` : ''}`);
  }

  async getGenome(slug: string): Promise<Genome> {
    return this.request<Genome>(`/api/v1/genomes/${slug}`);
  }

  async getGenomeVersions(slug: string): Promise<GenomeVersion[]> {
    return this.request<GenomeVersion[]>(`/api/v1/genomes/${slug}/versions`);
  }

  async getGenomeVersion(slug: string, version: string): Promise<GenomeVersion> {
    return this.request<GenomeVersion>(`/api/v1/genomes/${slug}/versions/${version}`);
  }

  async resolveGenome(
    slug: string,
    version?: string,
    product?: string,
  ): Promise<GenomeResolveResult> {
    const qs = new URLSearchParams();
    if (version) qs.set('version', version);
    if (product) qs.set('product', product);
    const query = qs.toString();
    return this.request<GenomeResolveResult>(
      `/api/v1/genomes/${slug}/resolve${query ? `?${query}` : ''}`,
    );
  }

  async publishGenome(data: CreateGenomeRequest, files?: Record<string, string>): Promise<Genome> {
    return this.request<Genome>('/api/v1/genomes', {
      method: 'POST',
      body: JSON.stringify({ ...data, files }),
    });
  }

  async publishGenomeVersion(
    slug: string,
    data: PublishGenomeVersionRequest,
    files?: Record<string, string>,
  ): Promise<Genome> {
    return this.request<Genome>(`/api/v1/genomes/${slug}/versions`, {
      method: 'POST',
      body: JSON.stringify({ ...data, files }),
    });
  }

  async getGenomeFiles(
    slug: string,
    version?: string,
  ): Promise<{ path: string; size: number; sha: string; type: string }[]> {
    const qs = version ? `?version=${encodeURIComponent(version)}` : '';
    return this.request(`/api/v1/genomes/${slug}/files${qs}`);
  }

  async getGenomeFileContent(
    slug: string,
    filePath: string,
    version?: string,
  ): Promise<{ path: string; content: string }> {
    const qs = version ? `?version=${encodeURIComponent(version)}` : '';
    return this.request(`/api/v1/genomes/${slug}/files/${filePath}${qs}`);
  }

  async downloadGenomeArchive(slug: string, version?: string): Promise<ArrayBuffer> {
    const qs = version ? `?version=${encodeURIComponent(version)}` : '';
    const url = `${this.baseUrl}/api/v1/genomes/${slug}/archive${qs}`;
    const headers: Record<string, string> = {};
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    const res = await fetch(url, { headers });
    if (!res.ok) throw new Error(`[GeneHub] Download genome archive failed: HTTP ${res.status}`);
    return res.arrayBuffer();
  }

  async reportGenomeInstall(slug: string): Promise<void> {
    await this.request(`/api/v1/genomes/${slug}/installed`, { method: 'POST', body: '{}' });
  }

  // ── Agent Template ──

  async searchTemplates(
    params: AgentTemplateListParams = {},
  ): Promise<PaginatedData<AgentTemplate>> {
    const qs = new URLSearchParams();
    if (params.q) qs.set('q', params.q);
    if (params.category) qs.set('category', params.category);
    if (params.role) qs.set('role', params.role);
    if (params.sort) qs.set('sort', params.sort);
    if (params.page) qs.set('page', String(params.page));
    if (params.page_size) qs.set('page_size', String(params.page_size));

    const query = qs.toString();
    return this.request<PaginatedData<AgentTemplate>>(
      `/api/v1/templates${query ? `?${query}` : ''}`,
    );
  }

  async getTemplate(slug: string): Promise<AgentTemplate> {
    return this.request<AgentTemplate>(`/api/v1/templates/${slug}`);
  }

  async getTemplateVersions(slug: string): Promise<AgentTemplateVersion[]> {
    return this.request<AgentTemplateVersion[]>(`/api/v1/templates/${slug}/versions`);
  }

  async getTemplateVersion(slug: string, version: string): Promise<AgentTemplateVersion> {
    return this.request<AgentTemplateVersion>(`/api/v1/templates/${slug}/versions/${version}`);
  }

  async publishTemplate(
    data: CreateAgentTemplateRequest,
    files?: Record<string, string>,
  ): Promise<AgentTemplate> {
    return this.request<AgentTemplate>('/api/v1/templates', {
      method: 'POST',
      body: JSON.stringify({ ...data, files }),
    });
  }

  async publishTemplateVersion(
    slug: string,
    data: PublishAgentTemplateVersionRequest,
    files?: Record<string, string>,
  ): Promise<AgentTemplate> {
    return this.request<AgentTemplate>(`/api/v1/templates/${slug}/versions`, {
      method: 'POST',
      body: JSON.stringify({ ...data, files }),
    });
  }

  async getTemplateFiles(
    slug: string,
    version?: string,
  ): Promise<{ path: string; size: number; sha: string; type: string }[]> {
    const qs = version ? `?version=${encodeURIComponent(version)}` : '';
    return this.request(`/api/v1/templates/${slug}/files${qs}`);
  }

  async getTemplateFileContent(
    slug: string,
    filePath: string,
    version?: string,
  ): Promise<{ path: string; content: string }> {
    const qs = version ? `?version=${encodeURIComponent(version)}` : '';
    return this.request(`/api/v1/templates/${slug}/files/${filePath}${qs}`);
  }

  async downloadTemplateArchive(slug: string, version?: string): Promise<ArrayBuffer> {
    const qs = version ? `?version=${encodeURIComponent(version)}` : '';
    const url = `${this.baseUrl}/api/v1/templates/${slug}/archive${qs}`;
    const headers: Record<string, string> = {};
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    const res = await fetch(url, { headers });
    if (!res.ok) throw new Error(`[GeneHub] Download template archive failed: HTTP ${res.status}`);
    return res.arrayBuffer();
  }

  async reportTemplateInstall(slug: string): Promise<void> {
    await this.request(`/api/v1/templates/${slug}/installed`, { method: 'POST', body: '{}' });
  }
}
