import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'

export interface GeneItem {
  id: string
  name: string
  slug: string
  description: string | null
  short_description: string | null
  category: string | null
  tags: string[]
  source: string
  source_ref: string | null
  icon: string | null
  version: string
  manifest: Record<string, unknown> | null
  dependencies: string[]
  synergies: string[]
  parent_gene_id: string | null
  created_by_instance_id: string | null
  install_count: number
  avg_rating: number
  effectiveness_score: number
  is_featured: boolean
  review_status: string | null
  is_published: boolean
  created_by: string | null
  org_id: string | null
  created_at: string | null
  updated_at: string | null
}

export interface GenomeItem {
  id: string
  name: string
  slug: string
  description: string | null
  short_description: string | null
  icon: string | null
  gene_slugs: string[]
  config_override: Record<string, unknown> | null
  install_count: number
  avg_rating: number
  is_featured: boolean
  is_published: boolean
  native_tool_count?: number
  mcp_server_count?: number
  created_by: string | null
  org_id: string | null
  created_at: string | null
}

export interface GeneStats {
  total_genes: number
  total_installs: number
  learning_count: number
  failed_count: number
  agent_created_count: number
}

export interface ActivityItem {
  id: string
  gene_slug: string
  gene_name: string
  metric_type: string
  value: number
  created_at: string | null
}

export const useGeneStore = defineStore('gene', () => {
  const genes = ref<GeneItem[]>([])
  const genomes = ref<GenomeItem[]>([])
  const totalGenes = ref(0)
  const totalGenomes = ref(0)
  const stats = ref<GeneStats | null>(null)
  const activity = ref<ActivityItem[]>([])
  const pendingGenes = ref<GeneItem[]>([])
  const loading = ref(false)

  async function fetchGenes(params: {
    keyword?: string
    category?: string
    is_published?: boolean
    sort?: string
    page?: number
    page_size?: number
  } = {}) {
    loading.value = true
    try {
      const res = await api.get('/admin/genes', { params })
      genes.value = res.data.data ?? []
      totalGenes.value = res.data.pagination?.total ?? 0
    } finally {
      loading.value = false
    }
  }

  async function fetchGenomes(params: {
    keyword?: string
    is_published?: boolean
    page?: number
    page_size?: number
  } = {}) {
    loading.value = true
    try {
      const res = await api.get('/admin/genomes', { params })
      genomes.value = res.data.data ?? []
      totalGenomes.value = res.data.pagination?.total ?? 0
    } finally {
      loading.value = false
    }
  }

  async function fetchStats() {
    const res = await api.get('/admin/genes/stats')
    stats.value = res.data.data
  }

  async function fetchActivity(limit = 50) {
    const res = await api.get('/admin/genes/activity', { params: { limit } })
    activity.value = res.data.data ?? []
  }

  async function fetchPendingGenes() {
    const res = await api.get('/admin/genes/pending-review')
    pendingGenes.value = res.data.data ?? []
  }

  async function createGene(data: Record<string, unknown>) {
    const res = await api.post('/admin/genes', data)
    return res.data.data
  }

  async function updateGene(geneId: string, data: Record<string, unknown>) {
    const res = await api.put(`/admin/genes/${geneId}`, data)
    return res.data.data
  }

  async function deleteGene(geneId: string) {
    await api.delete(`/admin/genes/${geneId}`)
  }

  async function reviewGene(geneId: string, action: string, reason?: string) {
    const res = await api.put(`/admin/genes/${geneId}/review`, { action, reason })
    return res.data.data
  }

  async function createGenome(data: Record<string, unknown>) {
    const res = await api.post('/admin/genomes', data)
    return res.data.data
  }

  async function updateGenome(genomeId: string, data: Record<string, unknown>) {
    const res = await api.put(`/admin/genomes/${genomeId}`, data)
    return res.data.data
  }

  async function deleteGenome(genomeId: string) {
    await api.delete(`/admin/genomes/${genomeId}`)
  }

  return {
    genes,
    genomes,
    totalGenes,
    totalGenomes,
    stats,
    activity,
    pendingGenes,
    loading,
    fetchGenes,
    fetchGenomes,
    fetchStats,
    fetchActivity,
    fetchPendingGenes,
    createGene,
    updateGene,
    deleteGene,
    reviewGene,
    createGenome,
    updateGenome,
    deleteGenome,
  }
})
