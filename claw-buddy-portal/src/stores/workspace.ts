import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'
import { useAuthStore } from '@/stores/auth'

export interface AgentBrief {
  instance_id: string
  name: string
  display_name: string | null
  slug: string | null
  status: string
  hex_q: number
  hex_r: number
  sse_connected: boolean
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
  hex_q?: number | null
  hex_r?: number | null
  channel_type?: string | null
  display_color?: string | null
}

export interface CorridorHexInfo {
  id: string
  hex_q: number
  hex_r: number
  display_name: string
}

export interface HexConnectionInfo {
  id: string
  hex_a_q: number
  hex_a_r: number
  hex_b_q: number
  hex_b_r: number
  direction: 'both' | 'a_to_b' | 'b_to_a'
  auto_created: boolean
}

export interface TopologyNode {
  q: number
  r: number
  type: 'blackboard' | 'agent' | 'human' | 'corridor'
  entity_id: string | null
  display_name: string | null
}

export interface TopologyEdge {
  id: string
  a_q: number
  a_r: number
  b_q: number
  b_r: number
  direction: string
  auto_created: boolean
}

export type HexType = 'empty' | 'agent' | 'blackboard' | 'human' | 'corridor'

export interface GroupChatMessage {
  id: string
  sender_type: 'user' | 'agent' | 'system'
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

  const corridorHexes = ref<CorridorHexInfo[]>([])
  const connections = ref<HexConnectionInfo[]>([])
  const topologyNodes = ref<TopologyNode[]>([])
  const topologyEdges = ref<TopologyEdge[]>([])

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

  async function addAgent(workspaceId: string, instanceId: string, displayName?: string, hexQ?: number, hexR?: number) {
    const body: Record<string, unknown> = { instance_id: instanceId }
    if (displayName) body.display_name = displayName
    if (hexQ !== undefined) { body.hex_q = hexQ; body.hex_r = hexR ?? 0 }
    const res = await api.post(`/workspaces/${workspaceId}/agents`, body)
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
  const unreadCount = ref(0)
  const chatVisible = ref(false)

  function setChatVisible(visible: boolean) {
    chatVisible.value = visible
    if (visible) unreadCount.value = 0
  }

  function _incrementUnread() {
    if (!chatVisible.value) unreadCount.value++
  }

  async function fetchChatHistory(workspaceId: string) {
    try {
      const res = await api.get(`/workspaces/${workspaceId}/messages`, { params: { limit: 50 } })
      const raw = res.data.data || []
      chatMessages.value = raw.map((m: Record<string, unknown>) => ({
        id: m.id as string,
        sender_type: m.sender_type as 'user' | 'agent' | 'system',
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

  async function sendWorkspaceMessage(workspaceId: string, message: string, mentions?: string[]) {
    if (chatLoading.value) return
    chatLoading.value = true

    const auth = useAuthStore()
    const userMsg: GroupChatMessage = {
      id: `local-${Date.now()}`,
      sender_type: 'user',
      sender_id: auth.user?.id || 'me',
      sender_name: auth.user?.name || 'Me',
      content: message,
      message_type: 'chat',
      created_at: new Date().toISOString(),
    }
    chatMessages.value.push(userMsg)

    try {
      const body: Record<string, unknown> = { message }
      if (mentions && mentions.length > 0) body.mentions = mentions
      await api.post(`/workspaces/${workspaceId}/chat`, body)
    } catch (e) {
      console.error('sendWorkspaceMessage error:', e)
    } finally {
      chatLoading.value = false
    }
  }

  async function sendSystemMessage(workspaceId: string, content: string) {
    try {
      await api.post(`/workspaces/${workspaceId}/system-message`, { content })
    } catch (e) {
      console.error('sendSystemMessage error:', e)
    }
  }

  const _typingTimers = new Map<string, ReturnType<typeof setTimeout>>()

  function _handleAgentTyping(data: Record<string, unknown>) {
    const instanceId = data.instance_id as string
    const agentName = data.agent_name as string
    typingAgents.value.set(instanceId, agentName)
    const prev = _typingTimers.get(instanceId)
    if (prev) clearTimeout(prev)
    _typingTimers.set(instanceId, setTimeout(() => {
      typingAgents.value.delete(instanceId)
      _typingTimers.delete(instanceId)
    }, 45_000))
  }

  function _handleAgentChunk(data: Record<string, unknown>) {
    const instanceId = data.instance_id as string
    const agentName = data.agent_name as string
    const content = data.content as string

    typingAgents.value.delete(instanceId)
    _clearTypingTimer(instanceId)

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
      _incrementUnread()
    }
  }

  function _clearTypingTimer(instanceId: string) {
    const t = _typingTimers.get(instanceId)
    if (t) { clearTimeout(t); _typingTimers.delete(instanceId) }
  }

  function _handleAgentDone(data: Record<string, unknown>) {
    const instanceId = data.instance_id as string
    typingAgents.value.delete(instanceId)
    _clearTypingTimer(instanceId)

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
    _clearTypingTimer(instanceId)

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
    _incrementUnread()
  }

  function _handleSystemWelcome(data: Record<string, unknown>) {
    const agentName = data.agent_name as string
    const content = data.content as string

    chatMessages.value.push({
      id: `sys-${Date.now()}`,
      sender_type: 'system',
      sender_id: 'system',
      sender_name: 'System',
      content: content || `${agentName} 已加入工作区`,
      message_type: 'system',
      created_at: new Date().toISOString(),
    })
    _incrementUnread()
  }

  // ── SSE ───────────────────────────────────────────

  let eventSource: EventSource | null = null
  let externalCallback: ChatSSECallback | null = null

  async function connectSSE(workspaceId: string, onEvent?: ChatSSECallback) {
    disconnectSSE()
    externalCallback = onEvent || null

    let token = ''
    try {
      const { data } = await api.post('/workspaces/sse-token')
      token = data?.data?.sse_token || ''
    } catch { /* ignore */ }
    if (!token) token = localStorage.getItem('portal_token') || ''

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
      'system:welcome': _handleSystemWelcome,
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

    eventSource.addEventListener('agent:sse_connected', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        externalCallback?.('agent:sse_connected', data)
        if (currentWorkspace.value) {
          const agent = currentWorkspace.value.agents.find(
            (a) => a.instance_id === data.instance_id,
          )
          if (agent) agent.sse_connected = true
        }
      } catch { /* ignore */ }
    })

    eventSource.addEventListener('agent:sse_disconnected', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        externalCallback?.('agent:sse_disconnected', data)
        if (currentWorkspace.value) {
          const agent = currentWorkspace.value.agents.find(
            (a) => a.instance_id === data.instance_id,
          )
          if (agent) agent.sse_connected = false
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
        if (data.id && data.content) {
          const exists = chatMessages.value.some(m => m.id === data.id)
          if (!exists) {
            chatMessages.value.push({
              id: data.id as string,
              sender_type: 'system',
              sender_id: (data.sender_id as string) || 'system',
              sender_name: (data.sender_name as string) || 'System',
              content: data.content as string,
              message_type: 'system',
              created_at: (data.created_at as string) || new Date().toISOString(),
            })
          }
        }
      } catch { /* ignore */ }
    })

    const corridorEvents = [
      'corridor:hex_placed', 'corridor:hex_removed',
      'human:hex_placed', 'human:hex_removed', 'human:channel_updated',
      'connection:created', 'connection:updated', 'connection:removed',
    ]
    for (const eventName of corridorEvents) {
      eventSource.addEventListener(eventName, (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data)
          externalCallback?.(eventName, data)
        } catch { /* ignore */ }
      })
    }

    const geneEvents = [
      'gene:install_start', 'gene:learn_start', 'gene:learn_decided',
      'gene:installed', 'gene:learn_failed', 'gene:variant_published',
      'gene:created', 'gene:effect_logged', 'gene:recommended',
    ]
    for (const eventName of geneEvents) {
      eventSource.addEventListener(eventName, (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data)
          externalCallback?.(eventName, data)
        } catch { /* ignore */ }
      })
    }

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

  // ── Topology / Corridor ─────────────────────────────

  async function fetchTopology(workspaceId: string) {
    try {
      const res = await api.get(`/workspaces/${workspaceId}/topology`)
      const data = res.data.data
      topologyNodes.value = data.nodes || []
      topologyEdges.value = data.edges || []
    } catch (e) {
      console.error('fetchTopology error:', e)
    }
  }

  async function fetchCorridorHexes(workspaceId: string) {
    try {
      const res = await api.get(`/workspaces/${workspaceId}/corridor-hexes`)
      corridorHexes.value = res.data.data || []
    } catch (e) {
      console.error('fetchCorridorHexes error:', e)
    }
  }

  async function fetchConnections(workspaceId: string) {
    try {
      const res = await api.get(`/workspaces/${workspaceId}/connections`)
      connections.value = res.data.data || []
    } catch (e) {
      console.error('fetchConnections error:', e)
    }
  }

  async function createCorridorHex(workspaceId: string, hexQ: number, hexR: number, displayName?: string) {
    const res = await api.post(`/workspaces/${workspaceId}/corridor-hexes`, {
      hex_q: hexQ, hex_r: hexR, display_name: displayName || '',
    })
    const ch = res.data.data
    corridorHexes.value.push(ch)
    return ch
  }

  async function deleteCorridorHex(workspaceId: string, hexId: string) {
    await api.delete(`/workspaces/${workspaceId}/corridor-hexes/${hexId}`)
    corridorHexes.value = corridorHexes.value.filter(c => c.id !== hexId)
  }

  async function createConnection(workspaceId: string, aQ: number, aR: number, bQ: number, bR: number, direction = 'both') {
    const res = await api.post(`/workspaces/${workspaceId}/connections`, {
      hex_a_q: aQ, hex_a_r: aR, hex_b_q: bQ, hex_b_r: bR, direction,
    })
    const conn = res.data.data
    connections.value.push(conn)
    return conn
  }

  async function updateConnection(workspaceId: string, connId: string, direction: string) {
    await api.put(`/workspaces/${workspaceId}/connections/${connId}`, { direction })
    const idx = connections.value.findIndex(c => c.id === connId)
    if (idx >= 0) connections.value[idx].direction = direction as HexConnectionInfo['direction']
  }

  async function deleteConnection(workspaceId: string, connId: string) {
    await api.delete(`/workspaces/${workspaceId}/connections/${connId}`)
    connections.value = connections.value.filter(c => c.id !== connId)
  }

  async function placeHumanHex(workspaceId: string, userId: string, hexQ: number, hexR: number) {
    await api.put(`/workspaces/${workspaceId}/members/${userId}/hex`, { hex_q: hexQ, hex_r: hexR })
    const member = members.value.find(m => m.user_id === userId)
    if (member) { member.hex_q = hexQ; member.hex_r = hexR }
  }

  async function removeHumanHex(workspaceId: string, userId: string) {
    await api.delete(`/workspaces/${workspaceId}/members/${userId}/hex`)
    const member = members.value.find(m => m.user_id === userId)
    if (member) { member.hex_q = null; member.hex_r = null }
  }

  async function updateHumanChannel(workspaceId: string, userId: string, channelType: string, channelConfig: Record<string, unknown>) {
    await api.put(`/workspaces/${workspaceId}/members/${userId}/channel`, { channel_type: channelType, channel_config: channelConfig })
    const member = members.value.find(m => m.user_id === userId)
    if (member) member.channel_type = channelType
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
    unreadCount,
    corridorHexes,
    connections,
    topologyNodes,
    topologyEdges,
    setChatVisible,
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
    sendSystemMessage,
    connectSSE,
    disconnectSSE,
    sendMessage,
    fetchTopology,
    fetchCorridorHexes,
    fetchConnections,
    createCorridorHex,
    deleteCorridorHex,
    createConnection,
    updateConnection,
    deleteConnection,
    placeHumanHex,
    removeHumanHex,
    updateHumanChannel,
  }
})
