import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'

export interface ClusterInfo {
  id: string
  name: string
  provider: string
  compute_provider: string
  auth_type: string
  ingress_class: string
  proxy_endpoint: string | null
  api_server_url: string | null
  k8s_version: string | null
  status: string
  health_status: string | null
  token_expires_at: string | null
  last_health_check: string | null
  created_by: string
  created_at: string
  updated_at: string
}

export interface ClusterOverviewSummary {
  node_count: number
  node_ready: number
  cpu_total: string
  cpu_used: string
  cpu_percent: number
  memory_total: string
  memory_used: string
  memory_percent: number
  pod_count: number
}

export interface NodeInfo {
  name: string
  status: string
  ip: string | null
  cpu_capacity: string
  cpu_used: string
  mem_capacity: string
  mem_used: string
  os: string | null
  kubelet_version: string | null
}

export interface StorageClassInfo {
  name: string
  provisioner: string
  reclaim_policy: string | null
  allow_volume_expansion: boolean
  is_default: boolean
  enabled: boolean
}

export interface IngressClassInfo {
  name: string
  controller: string
}

export interface ClusterOverview {
  summary: ClusterOverviewSummary
  nodes: NodeInfo[]
  storage_classes: StorageClassInfo[]
  ingress_classes: IngressClassInfo[]
}

export interface ConnectionTestResult {
  ok: boolean
  version: string | null
  nodes: number | null
  message: string | null
}

export const useClusterStore = defineStore('cluster', () => {
  const clusters = ref<ClusterInfo[]>([])
  const loading = ref(false)
  const currentCluster = ref<ClusterInfo | null>(null)
  const overview = ref<ClusterOverview | null>(null)
  const overviewLoading = ref(false)

  async function fetchClusters() {
    loading.value = true
    try {
      const res = await api.get('/clusters')
      clusters.value = res.data.data ?? []
    } finally {
      loading.value = false
    }
  }

  async function createCluster(payload: { name: string; kubeconfig: string; provider?: string }) {
    const res = await api.post('/clusters', payload)
    const created: ClusterInfo = res.data.data
    clusters.value.unshift(created)
    return created
  }

  async function updateCluster(id: string, payload: { name?: string; provider?: string; ingress_class?: string }) {
    const res = await api.put(`/clusters/${id}`, payload)
    const updated: ClusterInfo = res.data.data
    const idx = clusters.value.findIndex(c => c.id === id)
    if (idx >= 0) clusters.value[idx] = updated
    if (currentCluster.value?.id === id) currentCluster.value = updated
    return updated
  }

  async function deleteCluster(id: string) {
    await api.delete(`/clusters/${id}`)
    clusters.value = clusters.value.filter(c => c.id !== id)
    if (currentCluster.value?.id === id) currentCluster.value = null
  }

  async function testConnection(id: string): Promise<ConnectionTestResult> {
    const res = await api.post(`/clusters/${id}/test`)
    const result: ConnectionTestResult = res.data.data
    if (result.ok) {
      const idx = clusters.value.findIndex(c => c.id === id)
      if (idx >= 0) clusters.value[idx] = { ...clusters.value[idx], status: 'connected' }
      if (currentCluster.value?.id === id) currentCluster.value = { ...currentCluster.value, status: 'connected' }
    }
    return result
  }

  async function updateKubeconfig(id: string, kubeconfig: string) {
    const res = await api.post(`/clusters/${id}/kubeconfig`, { kubeconfig })
    const updated: ClusterInfo = res.data.data
    const idx = clusters.value.findIndex(c => c.id === id)
    if (idx >= 0) clusters.value[idx] = updated
    if (currentCluster.value?.id === id) currentCluster.value = updated
    return updated
  }

  async function createDockerCluster(name = 'local-docker') {
    const res = await api.post('/clusters/docker', { name })
    const created: ClusterInfo = res.data.data
    clusters.value.unshift(created)
    return created
  }

  async function fetchCluster(id: string) {
    const res = await api.get(`/clusters/${id}`)
    currentCluster.value = res.data.data
    return currentCluster.value
  }

  async function fetchOverview(id: string) {
    overviewLoading.value = true
    try {
      const res = await api.get(`/clusters/${id}/overview`)
      overview.value = res.data.data
    } finally {
      overviewLoading.value = false
    }
  }

  return {
    clusters,
    loading,
    currentCluster,
    overview,
    overviewLoading,
    fetchClusters,
    createCluster,
    createDockerCluster,
    updateCluster,
    deleteCluster,
    testConnection,
    updateKubeconfig,
    fetchCluster,
    fetchOverview,
  }
})
