import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'

export interface GeneItem {
  id: string
  name: string
  slug: string
  description?: string
  short_description?: string
  category?: string
  tags: string[]
  source: string
  icon?: string
  version: string
  install_count: number
  avg_rating: number
  effectiveness_score: number
  is_featured: boolean
  parent_gene_id?: string
  created_by_instance_id?: string
  manifest?: Record<string, unknown>
  dependencies?: string[]
  synergies?: string[]
  review_status?: string
  is_published: boolean
  created_at?: string
}

export interface GenomeItem {
  id: string
  name: string
  slug: string
  description?: string
  short_description?: string
  icon?: string
  gene_slugs: string[]
  install_count: number
  avg_rating: number
  is_featured: boolean
  native_tool_count?: number
  mcp_server_count?: number
  created_at?: string
}

export interface InstanceGeneItem {
  id: string
  instance_id: string
  gene_id: string
  genome_id?: string
  status: string
  installed_version?: string
  learning_output?: string
  agent_self_eval?: number
  usage_count: number
  variant_published: boolean
  installed_at?: string
  gene?: GeneItem
}

export interface InstanceSkillItem {
  type: 'hub' | 'emerged'
  skill_name: string
  name: string
  description: string
  file_count: number
  content_preview?: string
  full_content?: string
  frontmatter?: Record<string, unknown>
  gene?: GeneItem
  instance_gene?: InstanceGeneItem
}

export interface GeneStats {
  total_genes: number
  total_installs: number
  learning_count: number
  failed_count: number
  agent_created_count: number
}

export interface TemplateItem {
  id: string
  name: string
  slug: string
  description?: string
  short_description?: string
  icon?: string
  gene_slugs: string[]
  genes?: GeneRef[]
  source_instance_id?: string
  is_published: boolean
  is_featured: boolean
  use_count: number
  created_by?: string
  org_id?: string
  created_at?: string
}

export interface GeneRef {
  slug: string
  name: string
  short_description?: string
  category?: string
  icon?: string
}

export interface EvolutionEventItem {
  id: string
  instance_id: string
  event_type: string
  gene_name: string
  gene_slug?: string
  gene_id?: string
  genome_id?: string
  details?: Record<string, unknown>
  created_at?: string
}

export const useGeneStore = defineStore('gene', () => {
  const genes = ref<GeneItem[]>([])
  const genomes = ref<GenomeItem[]>([])
  const featuredGenes = ref<GeneItem[]>([])
  const featuredGenomes = ref<GenomeItem[]>([])
  const currentGene = ref<GeneItem | null>(null)
  const currentGenome = ref<GenomeItem | null>(null)
  const instanceGenes = ref<InstanceGeneItem[]>([])
  const instanceSkills = ref<InstanceSkillItem[]>([])
  const geneStats = ref<GeneStats | null>(null)
  const templates = ref<TemplateItem[]>([])
  const featuredTemplates = ref<TemplateItem[]>([])
  const currentTemplate = ref<TemplateItem | null>(null)
  const totalTemplates = ref(0)
  const loading = ref(false)
  const totalGenes = ref(0)
  const totalGenomes = ref(0)
  const tagStats = ref<{ tag: string; count: number }[]>([])

  // ── Gene Market ───────────────────────────────

  async function fetchGenes(params: {
    keyword?: string
    tag?: string
    category?: string
    source?: string
    sort?: string
    page?: number
    page_size?: number
  } = {}) {
    loading.value = true
    try {
      const res = await api.get('/genes', { params })
      genes.value = res.data.data || []
      totalGenes.value = res.data.pagination?.total || 0
    } catch (e) {
      console.error('fetchGenes error:', e)
    } finally {
      loading.value = false
    }
  }

  async function fetchFeaturedGenes() {
    try {
      const res = await api.get('/genes/featured')
      featuredGenes.value = res.data.data || []
    } catch (e) {
      console.error('fetchFeaturedGenes error:', e)
    }
  }

  async function fetchGeneTags() {
    try {
      const res = await api.get('/genes/tags')
      tagStats.value = res.data.data || []
    } catch (e) {
      console.error('fetchGeneTags error:', e)
    }
  }

  async function fetchGene(id: string) {
    loading.value = true
    try {
      const res = await api.get(`/genes/${id}`)
      currentGene.value = res.data.data
    } catch (e) {
      console.error('fetchGene error:', e)
    } finally {
      loading.value = false
    }
  }

  async function fetchGeneVariants(id: string): Promise<GeneItem[]> {
    try {
      const res = await api.get(`/genes/${id}/variants`)
      return res.data.data || []
    } catch (e) {
      console.error('fetchGeneVariants error:', e)
      return []
    }
  }

  async function fetchGeneSynergies(id: string): Promise<GeneItem[]> {
    try {
      const res = await api.get(`/genes/${id}/synergies`)
      return res.data.data || []
    } catch (e) {
      console.error('fetchGeneSynergies error:', e)
      return []
    }
  }

  async function fetchGeneGenomes(id: string): Promise<GenomeItem[]> {
    try {
      const res = await api.get(`/genes/${id}/genomes`)
      return res.data.data || []
    } catch (e) {
      console.error('fetchGeneGenomes error:', e)
      return []
    }
  }

  async function rateGene(geneId: string, rating: number, comment?: string) {
    await api.post(`/genes/${geneId}/rate`, { rating, comment })
  }

  // ── Genome Market ─────────────────────────────

  async function fetchGenomes(params: { keyword?: string; page?: number; page_size?: number } = {}) {
    loading.value = true
    try {
      const res = await api.get('/genomes', { params })
      genomes.value = res.data.data || []
      totalGenomes.value = res.data.pagination?.total || 0
    } catch (e) {
      console.error('fetchGenomes error:', e)
    } finally {
      loading.value = false
    }
  }

  async function fetchFeaturedGenomes() {
    try {
      const res = await api.get('/genomes/featured')
      featuredGenomes.value = res.data.data || []
    } catch (e) {
      console.error('fetchFeaturedGenomes error:', e)
    }
  }

  async function fetchGenome(id: string) {
    loading.value = true
    try {
      const res = await api.get(`/genomes/${id}`)
      currentGenome.value = res.data.data
    } catch (e) {
      console.error('fetchGenome error:', e)
    } finally {
      loading.value = false
    }
  }

  async function rateGenome(genomeId: string, rating: number, comment?: string) {
    await api.post(`/genomes/${genomeId}/rate`, { rating, comment })
  }

  // ── Instance Genes ────────────────────────────

  async function fetchInstanceGenes(instanceId: string) {
    loading.value = true
    try {
      const res = await api.get(`/instances/${instanceId}/genes`)
      instanceGenes.value = res.data.data || []
    } catch (e) {
      console.error('fetchInstanceGenes error:', e)
    } finally {
      loading.value = false
    }
  }

  async function fetchInstanceSkills(instanceId: string) {
    loading.value = true
    try {
      const res = await api.get(`/instances/${instanceId}/skills`)
      instanceSkills.value = res.data.data || []
    } catch (e) {
      console.error('fetchInstanceSkills error:', e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function installGene(instanceId: string, geneSlug: string) {
    const res = await api.post(`/instances/${instanceId}/genes/install`, { gene_slug: geneSlug })
    return res.data.data
  }

  async function uninstallGene(instanceId: string, geneId: string) {
    const res = await api.post(`/instances/${instanceId}/genes/uninstall`, { gene_id: geneId })
    return res.data.data
  }

  async function applyGenome(instanceId: string, genomeId: string) {
    const res = await api.post(`/instances/${instanceId}/genomes/apply`, { genome_id: genomeId })
    return res.data.data
  }

  async function publishVariant(instanceId: string, geneId: string, name?: string, slug?: string) {
    const res = await api.post(`/instances/${instanceId}/genes/${geneId}/publish-variant`, {
      variant_name: name,
      variant_slug: slug,
    })
    return res.data.data
  }

  async function logEffectiveness(instanceId: string, geneId: string, metricType: string, value: number = 1.0) {
    await api.post(`/instances/${instanceId}/genes/${geneId}/effectiveness`, {
      metric_type: metricType,
      value,
    })
  }

  async function fetchEvolutionLog(instanceId: string, page = 1, pageSize = 20): Promise<EvolutionEventItem[]> {
    const res = await api.get(`/instances/${instanceId}/evolution-log`, {
      params: { page, page_size: pageSize },
    })
    return res.data.data || []
  }

  async function triggerCreation(instanceId: string, prompt?: string) {
    const res = await api.post(`/instances/${instanceId}/genes/create`, {
      creation_prompt: prompt,
    })
    return res.data.data
  }

  // ── Instance Templates ──────────────────────────

  async function fetchTemplates(params: { keyword?: string; page?: number; page_size?: number } = {}) {
    loading.value = true
    try {
      const res = await api.get('/instance-templates', { params })
      templates.value = res.data.data || []
      totalTemplates.value = res.data.pagination?.total || 0
    } catch (e) {
      console.error('fetchTemplates error:', e)
    } finally {
      loading.value = false
    }
  }

  async function fetchFeaturedTemplates() {
    try {
      const res = await api.get('/instance-templates/featured')
      featuredTemplates.value = res.data.data || []
    } catch (e) {
      console.error('fetchFeaturedTemplates error:', e)
    }
  }

  async function fetchTemplate(id: string) {
    loading.value = true
    try {
      const res = await api.get(`/instance-templates/${id}`)
      currentTemplate.value = res.data.data
    } catch (e) {
      console.error('fetchTemplate error:', e)
    } finally {
      loading.value = false
    }
  }

  async function createTemplate(data: {
    name: string
    slug: string
    description?: string
    short_description?: string
    icon?: string
    gene_slugs: string[]
  }) {
    const res = await api.post('/instance-templates', data)
    return res.data.data
  }

  async function createTemplateFromInstance(instanceId: string, data: {
    name: string
    slug: string
    description?: string
    short_description?: string
    icon?: string
  }) {
    const res = await api.post(`/instance-templates/from-instance/${instanceId}`, data)
    return res.data.data
  }

  async function updateTemplate(id: string, data: {
    name?: string
    description?: string
    short_description?: string
    icon?: string
    gene_slugs?: string[]
  }) {
    const res = await api.put(`/instance-templates/${id}`, data)
    return res.data.data
  }

  async function deleteTemplate(id: string) {
    const res = await api.delete(`/instance-templates/${id}`)
    return res.data.data
  }

  // ── Admin ─────────────────────────────────────

  async function fetchGeneStats() {
    try {
      const res = await api.get('/admin/genes/stats')
      geneStats.value = res.data.data
    } catch (e) {
      console.error('fetchGeneStats error:', e)
    }
  }

  async function fetchGeneActivity(limit = 50) {
    const res = await api.get('/admin/genes/activity', { params: { limit } })
    return res.data.data || []
  }

  async function fetchPendingReviewGenes() {
    const res = await api.get('/admin/genes/pending-review')
    return res.data.data || []
  }

  async function fetchGeneMatrix() {
    const res = await api.get('/admin/genes/matrix')
    return res.data.data || []
  }

  async function fetchCoInstall(minCount = 2) {
    const res = await api.get('/admin/genes/co-install', { params: { min_count: minCount } })
    return res.data.data || []
  }

  async function reviewGene(geneId: string, action: string, reason?: string) {
    const res = await api.put(`/admin/genes/${geneId}/review`, { action, reason })
    return res.data.data
  }

  return {
    genes,
    genomes,
    templates,
    featuredGenes,
    featuredGenomes,
    featuredTemplates,
    currentGene,
    currentGenome,
    currentTemplate,
    instanceGenes,
    instanceSkills,
    geneStats,
    loading,
    totalGenes,
    totalGenomes,
    totalTemplates,
    tagStats,

    fetchGenes,
    fetchFeaturedGenes,
    fetchGeneTags,
    fetchGene,
    fetchGeneVariants,
    fetchGeneSynergies,
    fetchGeneGenomes,
    rateGene,

    fetchGenomes,
    fetchFeaturedGenomes,
    fetchGenome,
    rateGenome,

    fetchTemplates,
    fetchFeaturedTemplates,
    fetchTemplate,
    createTemplate,
    createTemplateFromInstance,
    updateTemplate,
    deleteTemplate,

    fetchInstanceGenes,
    fetchInstanceSkills,
    installGene,
    uninstallGene,
    applyGenome,
    publishVariant,
    logEffectiveness,
    triggerCreation,
    fetchEvolutionLog,

    fetchGeneStats,
    fetchGeneActivity,
    fetchPendingReviewGenes,
    fetchGeneMatrix,
    fetchCoInstall,
    reviewGene,
  }
})
