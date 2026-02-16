import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'
import { useAuthStore } from './auth'

export interface OrgInfo {
  id: string
  name: string
  slug: string
  plan: string
  max_instances: number
  max_cpu_total: string
  max_mem_total: string
  cluster_id: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface MemberInfo {
  id: string
  user_id: string
  org_id: string
  role: string
  user_name: string | null
  user_email: string | null
  created_at: string
}

export interface PlanInfo {
  id: string
  name: string
  display_name: string
  max_instances: number
  max_cpu_per_instance: string
  max_mem_per_instance: string
  allowed_specs: string
  dedicated_cluster: boolean
  price_monthly: number
  is_active: boolean
}

export interface OrgUsage {
  instance_count: number
  instance_limit: number
  cpu_used: string
  cpu_limit: string
  mem_used: string
  mem_limit: string
}

export const useOrgStore = defineStore('org', () => {
  const orgs = ref<OrgInfo[]>([])
  const currentOrg = ref<OrgInfo | null>(null)
  const members = ref<MemberInfo[]>([])
  const plans = ref<PlanInfo[]>([])
  const usage = ref<OrgUsage | null>(null)
  const loading = ref(false)

  const currentOrgId = computed(() => currentOrg.value?.id ?? null)

  async function fetchMyOrgs() {
    const res = await api.get('/orgs/my')
    orgs.value = res.data.data ?? []

    // 同步当前组织
    const authStore = useAuthStore()
    if (authStore.user?.current_org_id) {
      currentOrg.value = orgs.value.find(o => o.id === authStore.user!.current_org_id) ?? null
    } else if (orgs.value.length > 0) {
      currentOrg.value = orgs.value[0]
    }
  }

  async function switchOrg(orgId: string) {
    const res = await api.post(`/orgs/switch/${orgId}`)
    const orgData = res.data.data
    currentOrg.value = orgData

    // 更新 auth store 的 current_org_id
    const authStore = useAuthStore()
    if (authStore.user) {
      authStore.user.current_org_id = orgId
    }
  }

  // ── 超管组织管理 ──
  async function fetchAllOrgs() {
    loading.value = true
    try {
      const res = await api.get('/orgs')
      orgs.value = res.data.data ?? []
    } finally {
      loading.value = false
    }
  }

  async function createOrg(data: { name: string; slug: string; plan?: string }) {
    const res = await api.post('/orgs', data)
    const newOrg = res.data.data
    orgs.value.unshift(newOrg)
    return newOrg
  }

  async function updateOrg(orgId: string, data: Record<string, unknown>) {
    const res = await api.put(`/orgs/${orgId}`, data)
    const updated = res.data.data
    const idx = orgs.value.findIndex(o => o.id === orgId)
    if (idx >= 0) orgs.value[idx] = updated
    if (currentOrg.value?.id === orgId) currentOrg.value = updated
    return updated
  }

  async function deleteOrg(orgId: string) {
    await api.delete(`/orgs/${orgId}`)
    orgs.value = orgs.value.filter(o => o.id !== orgId)
  }

  // ── 成员管理 ──
  async function fetchMembers(orgId: string) {
    const res = await api.get(`/orgs/${orgId}/members`)
    members.value = res.data.data ?? []
  }

  async function addMember(orgId: string, userId: string, role: string = 'member') {
    const res = await api.post(`/orgs/${orgId}/members`, { user_id: userId, role })
    members.value.push(res.data.data)
    return res.data.data
  }

  async function updateMemberRole(orgId: string, membershipId: string, role: string) {
    const res = await api.put(`/orgs/${orgId}/members/${membershipId}`, { role })
    const idx = members.value.findIndex(m => m.id === membershipId)
    if (idx >= 0) members.value[idx] = res.data.data
    return res.data.data
  }

  async function removeMember(orgId: string, membershipId: string) {
    await api.delete(`/orgs/${orgId}/members/${membershipId}`)
    members.value = members.value.filter(m => m.id !== membershipId)
  }

  // ── 计费 ──
  async function fetchPlans() {
    const res = await api.get('/billing/plans')
    plans.value = res.data.data ?? []
  }

  async function fetchUsage() {
    const res = await api.get('/billing/usage')
    usage.value = res.data.data
  }

  async function upgradePlan(planName: string) {
    const res = await api.post('/billing/upgrade', { plan_name: planName })
    if (currentOrg.value) {
      currentOrg.value = res.data.data
    }
    return res.data.data
  }

  return {
    orgs,
    currentOrg,
    currentOrgId,
    members,
    plans,
    usage,
    loading,
    fetchMyOrgs,
    switchOrg,
    fetchAllOrgs,
    createOrg,
    updateOrg,
    deleteOrg,
    fetchMembers,
    addMember,
    updateMemberRole,
    removeMember,
    fetchPlans,
    fetchUsage,
    upgradePlan,
  }
})
