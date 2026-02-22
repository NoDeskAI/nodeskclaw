import { defineStore } from 'pinia'
import { ref } from 'vue'
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

export interface WorkspaceMemberInfo {
  user_id: string
  user_name: string
  user_email: string | null
  user_avatar_url: string | null
  role: string
  created_at: string
}

export interface GroupChatMessage {
  id: string
  sender_type: 'user' | 'agent'
  sender_id: string
  sender_name: string
  content: string
  message_type: string
  created_at: string
  streaming?: boolean
}

export type ChatSSECallback = (event: string, data: Record<string, unknown>) => void

export const useWorkspaceStore = defineStore('workspace', () => {
  const workspaces = ref<WorkspaceListItem[]>([])
  const currentWorkspace = ref<WorkspaceInfo | null>(null)
  const blackboard = ref<BlackboardInfo | null>(null)
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

  // ── Members ───────────────────────────────────────

  async function fetchMembers(workspaceId: string) {
    try {
      const res = await api.get(`/workspaces/${workspaceId}/members`)
      members.value = res.data.data || []
    } catch (e) {
      console.error('fetchMembers error:', e)
    }
  }

  // ── Group Chat ─────────────────────────────────────

  const chatMessages = ref<GroupChatMessage[]>([])
  const chatLoading = ref(false)
  const typingAgents = ref<Map<string, string>>(new Map())

  async function fetchChatHistory(workspaceId: string) {
    try {
      const res = await api.get(`/workspaces/${workspaceId}/messages`, { params: { limit: 50 } })
      const raw = res.data.data || []
      chatMessages.value = raw.map((m: Record<string, unknown>) => ({
        id: m.id as string,
        sender_type: m.sender_type as 'user' | 'agent',
        sender_id: m.sender_id as string,
        sender_name: m.sender_name as string,
        content: m.content as string,
        message_type: m.message_type as string,
        created_at: m.created_at as string,
      }))
    } catch (e) {
      console.error('fetchChatHistory error:', e)
    }
  }

  async function sendWorkspaceMessage(workspaceId: string, message: string) {
    if (chatLoading.value) return
    chatLoading.value = true

    const userMsg: GroupChatMessage = {
      id: `local-${Date.now()}`,
      sender_type: 'user',
      sender_id: 'me',
      sender_name: 'Me',
      content: message,
      message_type: 'chat',
      created_at: new Date().toISOString(),
    }
    chatMessages.value.push(userMsg)

    try {
      await api.post(`/workspaces/${workspaceId}/chat`, { message })
    } catch (e) {
      console.error('sendWorkspaceMessage error:', e)
    } finally {
      chatLoading.value = false
    }
  }

  function _handleAgentTyping(data: Record<string, unknown>) {
    const instanceId = data.instance_id as string
    const agentName = data.agent_name as string
    typingAgents.value.set(instanceId, agentName)
  }

  function _handleAgentChunk(data: Record<string, unknown>) {
    const instanceId = data.instance_id as string
    const agentName = data.agent_name as string
    const content = data.content as string

    const existing = chatMessages.value.find(
      (m) => m.sender_id === instanceId && m.streaming,
    )
    if (existing) {
      existing.content += content
    } else {
      chatMessages.value.push({
        id: `stream-${instanceId}-${Date.now()}`,
        sender_type: 'agent',
        sender_id: instanceId,
        sender_name: agentName,
        content,
        message_type: 'chat',
        created_at: new Date().toISOString(),
        streaming: true,
      })
    }
  }

  function _handleAgentDone(data: Record<string, unknown>) {
    const instanceId = data.instance_id as string
    typingAgents.value.delete(instanceId)

    const streaming = chatMessages.value.find(
      (m) => m.sender_id === instanceId && m.streaming,
    )
    if (streaming) {
      streaming.streaming = false
      streaming.content = (data.full_content as string) || streaming.content
    }
  }

  function _handleAgentError(data: Record<string, unknown>) {
    const instanceId = data.instance_id as string
    const agentName = data.agent_name as string
    typingAgents.value.delete(instanceId)

    const streaming = chatMessages.value.find(
      (m) => m.sender_id === instanceId && m.streaming,
    )
    if (streaming) {
      streaming.streaming = false
      streaming.content += `\n[Error: ${data.error}]`
    } else {
      chatMessages.value.push({
        id: `error-${instanceId}-${Date.now()}`,
        sender_type: 'agent',
        sender_id: instanceId,
        sender_name: agentName,
        content: `[Error: ${data.error}]`,
        message_type: 'chat',
        created_at: new Date().toISOString(),
      })
    }
  }

  function _handleAgentCollaboration(data: Record<string, unknown>) {
    const agentName = data.agent_name as string
    const instanceId = data.instance_id as string
    const content = data.content as string

    chatMessages.value.push({
      id: `collab-${instanceId}-${Date.now()}`,
      sender_type: 'agent',
      sender_id: instanceId,
      sender_name: agentName,
      content,
      message_type: 'collaboration',
      created_at: new Date().toISOString(),
    })
  }

  // ── SSE ───────────────────────────────────────────

  let eventSource: EventSource | null = null
  let externalCallback: ChatSSECallback | null = null

  function connectSSE(workspaceId: string, onEvent?: ChatSSECallback) {
    disconnectSSE()
    externalCallback = onEvent || null
    const token = localStorage.getItem('portal_token') || ''
    eventSource = new EventSource(`/api/v1/workspaces/${workspaceId}/events?token=${token}`)

    eventSource.onmessage = (e) => {
      try {
        const parsed = JSON.parse(e.data)
        externalCallback?.(parsed.event || 'message', parsed)
      } catch { /* ignore */ }
    }

    const sseHandlers: Record<string, (data: Record<string, unknown>) => void> = {
      'agent:typing': _handleAgentTyping,
      'agent:chunk': _handleAgentChunk,
      'agent:done': _handleAgentDone,
      'agent:error': _handleAgentError,
      'agent:collaboration': _handleAgentCollaboration,
    }

    for (const [eventName, handler] of Object.entries(sseHandlers)) {
      eventSource.addEventListener(eventName, (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data)
          handler(data)
          externalCallback?.(eventName, data)
        } catch { /* ignore */ }
      })
    }

    eventSource.addEventListener('agent:status', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        externalCallback?.('agent:status', data)
        if (currentWorkspace.value) {
          const agent = currentWorkspace.value.agents.find(
            (a) => a.instance_id === data.instance_id,
          )
          if (agent) agent.status = data.status as string
        }
      } catch { /* ignore */ }
    })

    eventSource.addEventListener('blackboard:updated', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        externalCallback?.('blackboard:updated', data)
        if (blackboard.value) {
          Object.assign(blackboard.value, data)
        }
      } catch { /* ignore */ }
    })

    eventSource.addEventListener('system:info', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        externalCallback?.('system:info', data)
      } catch { /* ignore */ }
    })

    eventSource.onerror = () => {
      setTimeout(() => {
        if (eventSource?.readyState === EventSource.CLOSED) {
          connectSSE(workspaceId, externalCallback || undefined)
        }
      }, 3000)
    }
  }

  function disconnectSSE() {
    eventSource?.close()
    eventSource = null
    externalCallback = null
  }

  // ── Legacy Chat (deprecated) ──────────────────────

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
    members,
    loading,
    chatMessages,
    chatLoading,
    typingAgents,
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
    fetchMembers,
    fetchChatHistory,
    sendWorkspaceMessage,
    connectSSE,
    disconnectSSE,
    sendMessage,
  }
})
