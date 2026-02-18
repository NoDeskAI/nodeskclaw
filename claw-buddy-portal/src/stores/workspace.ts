import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'

export interface AgentBrief {
  instance_id: string
  name: string
  display_name: string | null
  status: string
  hex_q: number
  hex_r: number
}

export interface WorkspaceListItem {
  id: string
  name: string
  description: string
  color: string
  icon: string
  agent_count: number
  agents: AgentBrief[]
  created_at: string
}

export interface WorkspaceInfo {
  id: string
  org_id: string
  name: string
  description: string
  color: string
  icon: string
  created_by: string
  agent_count: number
  agents: AgentBrief[]
  created_at: string
  updated_at: string
}

export interface BlackboardInfo {
  id: string
  workspace_id: string
  auto_summary: string
  manual_notes: string
  summary_updated_at: string | null
  updated_at: string
}

export interface ContextEntryInfo {
  id: string
  workspace_id: string
  source_instance_id: string
  entry_type: string
  content: string
  tags: string[]
  visibility: string
  target_instance_ids: string[]
  ttl_hours: number
  expires_at: string
  created_at: string
}

export interface WorkspaceMemberInfo {
  user_id: string
  user_name: string
  user_email: string | null
  user_avatar_url: string | null
  role: string
  created_at: string
}

export const useWorkspaceStore = defineStore('workspace', () => {
  const workspaces = ref<WorkspaceListItem[]>([])
  const currentWorkspace = ref<WorkspaceInfo | null>(null)
  const blackboard = ref<BlackboardInfo | null>(null)
  const contextEntries = ref<ContextEntryInfo[]>([])
  const members = ref<WorkspaceMemberInfo[]>([])
  const loading = ref(false)

  // ── Workspace CRUD ────────────────────────────────

  async function fetchWorkspaces() {
    loading.value = true
    try {
      const res = await api.get('/workspaces')
      workspaces.value = res.data.data || []
    } catch (e) {
      console.error('fetchWorkspaces error:', e)
    } finally {
      loading.value = false
    }
  }

  async function fetchWorkspace(id: string) {
    loading.value = true
    try {
      const res = await api.get(`/workspaces/${id}`)
      currentWorkspace.value = res.data.data
    } catch (e) {
      console.error('fetchWorkspace error:', e)
    } finally {
      loading.value = false
    }
  }

  async function createWorkspace(data: { name: string; description?: string; color?: string; icon?: string }) {
    const res = await api.post('/workspaces', data)
    const ws = res.data.data
    workspaces.value.unshift(ws)
    return ws as WorkspaceInfo
  }

  async function updateWorkspace(id: string, data: Record<string, unknown>) {
    const res = await api.put(`/workspaces/${id}`, data)
    currentWorkspace.value = res.data.data
    const idx = workspaces.value.findIndex((w) => w.id === id)
    if (idx >= 0) {
      Object.assign(workspaces.value[idx], res.data.data)
    }
  }

  async function deleteWorkspace(id: string) {
    await api.delete(`/workspaces/${id}`)
    workspaces.value = workspaces.value.filter((w) => w.id !== id)
    if (currentWorkspace.value?.id === id) currentWorkspace.value = null
  }

  // ── Agent Management ──────────────────────────────

  async function addAgent(workspaceId: string, instanceId: string, displayName?: string) {
    const res = await api.post(`/workspaces/${workspaceId}/agents`, {
      instance_id: instanceId,
      display_name: displayName,
    })
    if (currentWorkspace.value?.id === workspaceId) {
      await fetchWorkspace(workspaceId)
    }
    return res.data.data
  }

  async function removeAgent(workspaceId: string, instanceId: string) {
    await api.delete(`/workspaces/${workspaceId}/agents/${instanceId}`)
    if (currentWorkspace.value?.id === workspaceId) {
      await fetchWorkspace(workspaceId)
    }
  }

  async function updateAgent(workspaceId: string, instanceId: string, data: Record<string, unknown>) {
    await api.put(`/workspaces/${workspaceId}/agents/${instanceId}`, data)
    if (currentWorkspace.value?.id === workspaceId) {
      await fetchWorkspace(workspaceId)
    }
  }

  // ── Blackboard ────────────────────────────────────

  async function fetchBlackboard(workspaceId: string) {
    try {
      const res = await api.get(`/workspaces/${workspaceId}/blackboard`)
      blackboard.value = res.data.data
    } catch (e) {
      console.error('fetchBlackboard error:', e)
    }
  }

  async function updateBlackboard(workspaceId: string, notes: string) {
    const res = await api.put(`/workspaces/${workspaceId}/blackboard`, { manual_notes: notes })
    blackboard.value = res.data.data
  }

  // ── Context ───────────────────────────────────────

  async function fetchContext(workspaceId: string, limit = 50) {
    try {
      const res = await api.get(`/workspaces/${workspaceId}/context`, { params: { limit } })
      contextEntries.value = res.data.data || []
    } catch (e) {
      console.error('fetchContext error:', e)
    }
  }

  // ── Members ───────────────────────────────────────

  async function fetchMembers(workspaceId: string) {
    try {
      const res = await api.get(`/workspaces/${workspaceId}/members`)
      members.value = res.data.data || []
    } catch (e) {
      console.error('fetchMembers error:', e)
    }
  }

  // ── SSE ───────────────────────────────────────────

  let eventSource: EventSource | null = null

  function connectSSE(workspaceId: string, onEvent?: (event: string, data: unknown) => void) {
    disconnectSSE()
    const token = localStorage.getItem('portal_token') || ''
    eventSource = new EventSource(`/api/v1/workspaces/${workspaceId}/events?token=${token}`)

    eventSource.onmessage = (e) => {
      try {
        const parsed = JSON.parse(e.data)
        onEvent?.(parsed.event || 'message', parsed)
      } catch { /* ignore */ }
    }

    eventSource.addEventListener('agent:status', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        onEvent?.('agent:status', data)
        if (currentWorkspace.value) {
          const agent = currentWorkspace.value.agents.find((a) => a.instance_id === data.instance_id)
          if (agent) agent.status = data.status
        }
      } catch { /* ignore */ }
    })

    eventSource.addEventListener('context:published', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        onEvent?.('context:published', data)
      } catch { /* ignore */ }
    })

    eventSource.addEventListener('blackboard:updated', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        onEvent?.('blackboard:updated', data)
        if (blackboard.value) {
          Object.assign(blackboard.value, data)
        }
      } catch { /* ignore */ }
    })

    eventSource.onerror = () => {
      setTimeout(() => {
        if (eventSource?.readyState === EventSource.CLOSED) {
          connectSSE(workspaceId, onEvent)
        }
      }, 3000)
    }
  }

  function disconnectSSE() {
    eventSource?.close()
    eventSource = null
  }

  // ── Chat ──────────────────────────────────────────

  async function* sendMessage(
    workspaceId: string,
    instanceId: string,
    message: string,
    history: { role: string; content: string }[],
  ): AsyncGenerator<string, void, unknown> {
    const res = await fetch(`/api/v1/workspaces/${workspaceId}/agents/${instanceId}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('portal_token') || ''}`,
      },
      body: JSON.stringify({ message, history }),
    })

    if (!res.ok) throw new Error(`Chat failed: ${res.status}`)
    if (!res.body) return

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const payload = line.slice(6).trim()
          if (payload === '[DONE]') return
          try {
            const parsed = JSON.parse(payload)
            if (parsed.content) yield parsed.content
          } catch { /* ignore */ }
        }
      }
    }
  }

  return {
    workspaces,
    currentWorkspace,
    blackboard,
    contextEntries,
    members,
    loading,
    fetchWorkspaces,
    fetchWorkspace,
    createWorkspace,
    updateWorkspace,
    deleteWorkspace,
    addAgent,
    removeAgent,
    updateAgent,
    fetchBlackboard,
    updateBlackboard,
    fetchContext,
    fetchMembers,
    connectSSE,
    disconnectSSE,
    sendMessage,
  }
})
