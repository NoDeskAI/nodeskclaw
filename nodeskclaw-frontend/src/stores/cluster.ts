import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'

export interface ClusterInfo {
  id: string
  name: string
  provider: string
  auth_type: string
  ingress_class: string
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

export const useClusterStore = defineStore('cluster', () => {
  const clusters = ref<ClusterInfo[]>([])
  const currentClusterId = ref<string | null>(localStorage.getItem('current_cluster_id'))
  const loading = ref(false)

  const currentCluster = computed(() =>
    clusters.value.find((c) => c.id === currentClusterId.value) ?? clusters.value[0] ?? null,
  )

  function selectCluster(id: string) {
    currentClusterId.value = id
    localStorage.setItem('current_cluster_id', id)
  }

  async function fetchClusters() {
    loading.value = true
    try {
      const res = await api.get('/clusters')
      clusters.value = res.data.data
      // Auto-select first if none selected
      if (!currentClusterId.value && clusters.value.length > 0) {
        selectCluster(clusters.value[0].id)
      }
    } finally {
      loading.value = false
    }
  }

  async function addCluster(name: string, kubeconfig: string, provider = 'vke') {
    const res = await api.post('/clusters', { name, kubeconfig, provider })
    const cluster = res.data.data as ClusterInfo
    clusters.value.unshift(cluster)
    return cluster
  }

  async function deleteCluster(id: string) {
    await api.delete(`/clusters/${id}`)
    clusters.value = clusters.value.filter((c) => c.id !== id)
    if (currentClusterId.value === id) {
      currentClusterId.value = clusters.value[0]?.id ?? null
    }
  }

  async function testConnection(id: string) {
    const res = await api.post(`/clusters/${id}/test`)
    return res.data.data
  }

  async function updateCluster(id: string, data: { name?: string; provider?: string; ingress_class?: string }) {
    const res = await api.put(`/clusters/${id}`, data)
    const updated = res.data.data as ClusterInfo
    const idx = clusters.value.findIndex((c) => c.id === id)
    if (idx >= 0) clusters.value[idx] = updated
    return updated
  }

  async function updateKubeconfig(id: string, kubeconfig: string) {
    const res = await api.post(`/clusters/${id}/kubeconfig`, { kubeconfig })
    const updated = res.data.data as ClusterInfo
    const idx = clusters.value.findIndex((c) => c.id === id)
    if (idx >= 0) clusters.value[idx] = updated
    return updated
  }

  return {
    clusters,
    currentClusterId,
    currentCluster,
    loading,
    selectCluster,
    fetchClusters,
    addCluster,
    updateCluster,
    deleteCluster,
    testConnection,
    updateKubeconfig,
  }
})
