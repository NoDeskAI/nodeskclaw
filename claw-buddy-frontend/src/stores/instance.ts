import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'

export interface InstanceInfo {
  id: string
  name: string
  cluster_id: string
  namespace: string
  image_version: string
  replicas: number
  available_replicas: number
  status: string
  service_type: string
  ingress_domain: string | null
  storage_class: string
  storage_size: string
  advanced_config: string | null
  pending_config: string | null
  created_by: string
  created_at: string
  updated_at: string
}

export interface PodInfo {
  name: string
  status: string
  node: string | null
  ip: string | null
  restart_count: number
  containers: { name: string; image: string; ready: boolean; restart_count: number; state: string }[]
}

export interface ServiceInfoType {
  name: string
  type: string
  cluster_ip: string | null
  external_ip: string | null
  ports: Record<string, unknown>[]
}

export interface InstanceDetail extends InstanceInfo {
  cpu_request: string
  cpu_limit: string
  mem_request: string
  mem_limit: string
  env_vars: Record<string, string>
  pods: PodInfo[]
  service_info: ServiceInfoType | null
  events: { type: string; reason: string; message: string; count: number }[]
}

export interface DeployRecord {
  id: string
  instance_id: string
  revision: number
  action: string
  image_version: string | null
  replicas: number | null
  config_snapshot: string | null
  status: string
  message: string | null
  triggered_by: string
  started_at: string | null
  finished_at: string | null
  created_at: string
}

export interface UpdateConfigPayload {
  image_version?: string
  cpu_request?: string
  cpu_limit?: string
  mem_request?: string
  mem_limit?: string
  env_vars?: Record<string, string>
  replicas?: number
  advanced_config?: Record<string, unknown>
}

export const useInstanceStore = defineStore('instance', () => {
  const instances = ref<InstanceInfo[]>([])
  const loading = ref(false)

  async function fetchInstances(clusterId?: string) {
    loading.value = true
    try {
      const params = clusterId ? { cluster_id: clusterId } : {}
      const res = await api.get('/instances', { params })
      instances.value = res.data.data
    } finally {
      loading.value = false
    }
  }

  async function fetchDetail(id: string): Promise<InstanceDetail> {
    const res = await api.get(`/instances/${id}`)
    return res.data.data
  }

  async function deleteInstance(id: string) {
    await api.delete(`/instances/${id}`)
    instances.value = instances.value.filter((i) => i.id !== id)
  }

  async function scale(id: string, replicas: number) {
    await api.post(`/instances/${id}/scale`, { replicas })
  }

  async function restart(id: string) {
    await api.post(`/instances/${id}/restart`)
  }

  async function saveConfig(id: string, payload: UpdateConfigPayload): Promise<InstanceInfo> {
    const res = await api.put(`/instances/${id}/config`, payload)
    return res.data.data
  }

  async function applyConfig(id: string): Promise<InstanceInfo> {
    const res = await api.post(`/instances/${id}/apply`)
    return res.data.data
  }

  /** @deprecated Use saveConfig + applyConfig for two-step mode */
  async function updateConfig(id: string, payload: UpdateConfigPayload): Promise<InstanceInfo> {
    const res = await api.put(`/instances/${id}/config`, payload)
    return res.data.data
  }

  async function rollback(id: string, targetRevision: number): Promise<InstanceInfo> {
    const res = await api.post(`/instances/${id}/rollback`, { target_revision: targetRevision })
    return res.data.data
  }

  async function getHistory(id: string): Promise<DeployRecord[]> {
    const res = await api.get(`/instances/${id}/history`)
    return res.data.data
  }

  async function getLogs(id: string, podName: string, container?: string) {
    const params: Record<string, string | number> = {}
    if (container) params.container = container
    const res = await api.get(`/instances/${id}/pods/${podName}/logs`, { params })
    return res.data.data as string
  }

  return {
    instances,
    loading,
    fetchInstances,
    fetchDetail,
    deleteInstance,
    scale,
    restart,
    saveConfig,
    applyConfig,
    updateConfig,
    rollback,
    getHistory,
    getLogs,
  }
})
