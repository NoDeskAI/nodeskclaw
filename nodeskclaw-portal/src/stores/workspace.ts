import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'
import { useAuthStore } from '@/stores/auth'

export interface AgentBrief {
  instance_id: string
  name: string
  display_name: string | null
  label: string | null
  slug: string | null
  status: string
  hex_q: number
  hex_r: number
  sse_connected: boolean
  theme_color: string | null
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

export interface WorkspaceTemplateItem {
  id: string
  name: string
  description: string
  is_preset: boolean
  org_id: string | null
  visibility: string
  created_by: string | null
  created_at: string | null
}

export interface TaskInfo {
  id: string
  workspace_id: string
  title: string
  description: string | null
  status: string
  priority: string
  assignee_instance_id: string | null
  assignee_name: string | null
  created_by_instance_id: string | null
  estimated_value: number | null
  actual_value: number | null
  token_cost: number | null
  blocker_reason: string | null
  completed_at: string | null
  archived_at: string | null
  created_at: string
  updated_at: string
}

export interface ObjectiveInfo {
  id: string
  workspace_id: string
  title: string
  description: string | null
  progress: number
  obj_type: string
  parent_id: string | null
  children: ObjectiveInfo[]
  created_by: string | null
  created_at: string
  updated_at: string
}

export interface BlackboardInfo {
  id: string
  workspace_id: string
  content: string
  tasks: TaskInfo[]
  objectives: ObjectiveInfo[]
  updated_at: string
}

export interface WorkspaceMemberInfo {
  user_id: string
  user_name: string
  user_email: string | null
  user_avatar_url: string | null
  role: string
  is_admin: boolean
  permissions: string[]
  created_at: string
}

export interface HumanHexInfo {
  id: string
  workspace_id: string
  user_id: string
  hex_q: number
  hex_r: number
  display_name: string | null
  display_color: string
  channel_type: string | null
  channel_config: Record<string, unknown> | null
  created_at: string
}

export interface CorridorHexInfo {
  id: string
  workspace_id: string
  hex_q: number
  hex_r: number
  display_name: string
  created_by: string | null
  created_at: string
}

export interface ConnectionInfo {
  id: string
  workspace_id: string
  hex_a_q: number
  hex_a_r: number
  hex_b_q: number
  hex_b_r: number
  auto_created: boolean
  created_by: string | null
  created_at: string
}

export interface TopologyNode {
  hex_q: number
  hex_r: number
  node_type: 'blackboard' | 'corridor' | 'agent' | 'human'
  entity_id: string | null
  display_name: string | null
  extra: Record<string, unknown>
}

export interface TopologyEdge {
  a_q: number
  a_r: number
  b_q: number
  b_r: number
  auto_created: boolean
  direction?: 'both' | 'a_to_b' | 'b_to_a'
}

export interface TopologyInfo {
  nodes: TopologyNode[]
  edges: TopologyEdge[]
}

export interface HexDecoration {
  floor_asset_id: string | null
  furniture: string[]
}

export interface DecorationConfig {
  hexes: Record<string, HexDecoration>
}

export interface MessageFlowPair {
  sender_hex_key: string
  receiver_hex_key: string
  count: number
}

export interface HeatmapEntry {
  node_id: string
  message_count: number
}

export interface FileAttachment {
  id: string
  name: string
  size: number
  content_type: string
}

export interface GroupChatMessage {
  id: string
  sender_type: 'user' | 'agent' | 'system'
  sender_id: string
  sender_name: string
  content: string
  message_type: string
  created_at: string
  streaming?: boolean
  attachments?: FileAttachment[]
  trace_id?: string
  causation_id?: string
  intent?: string
  priority?: string
  envelope_id?: string
}

export interface ScheduleInfo {
  id: string
  workspace_id: string
  name: string
  cron_expr: string
  message_template: string
  is_active: boolean
  created_at: string | null
}

export type ChatSSECallback = (event: string, data: Record<string, unknown>) => void

export const WORKSPACE_PERMISSIONS = [
  'manage_settings',
  'manage_agents',
  'manage_members',
  'edit_blackboard',
  'send_chat',
  'edit_topology',
  'delete_workspace',
] as const

export type WorkspacePermission = typeof WORKSPACE_PERMISSIONS[number]

export const PERMISSION_PRESETS: Record<string, { is_admin: boolean; permissions: string[] }> = {
  administrator: { is_admin: true, permissions: [] },
  collaborator: { is_admin: false, permissions: ['manage_agents', 'edit_blackboard', 'send_chat', 'edit_topology'] },
  observer: { is_admin: false, permissions: ['send_chat'] },
}

export const useWorkspaceStore = defineStore('workspace', () => {
  const workspaces = ref<WorkspaceListItem[]>([])
  const currentWorkspace = ref<WorkspaceInfo | null>(null)
  const blackboard = ref<BlackboardInfo | null>(null)
  const schedules = ref<ScheduleInfo[]>([])
  const members = ref<WorkspaceMemberInfo[]>([])
  const loading = ref(false)

  const corridorHexes = ref<CorridorHexInfo[]>([])
  const connections = ref<ConnectionInfo[]>([])
  const topology = ref<TopologyInfo | null>(null)
  const messageFlowStats = ref<MessageFlowPair[]>([])
  const heatmap = ref<HeatmapEntry[]>([])

  const decoration = ref<DecorationConfig | null>(null)

  const myPermissions = ref<string[]>([])
  const isWorkspaceAdmin = ref(false)
  const isOrgAdmin = ref(false)
  const fileUploadEnabled = ref(false)

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

  async function fetchSystemCapabilities() {
    try {
      const res = await api.get('/system/capabilities')
      fileUploadEnabled.value = !!res.data?.file_upload_enabled
    } catch {
      fileUploadEnabled.value = false
    }
  }

  async function uploadFile(workspaceId: string, file: File): Promise<FileAttachment | null> {
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await api.post(`/workspaces/${workspaceId}/files/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return res.data.data as FileAttachment
    } catch (e) {
      console.error('uploadFile error:', e)
      return null
    }
  }

  async function getFileUrl(workspaceId: string, fileId: string): Promise<string | null> {
    try {
      const res = await api.get(`/workspaces/${workspaceId}/files/${fileId}/url`)
      return res.data.data?.url || null
    } catch (e) {
      console.error('getFileUrl error:', e)
      return null
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

  async function createWorkspace(data: { name: string; description?: string; color?: string; icon?: string; template_id?: string }) {
    const res = await api.post('/workspaces', data)
    const ws = res.data.data
    workspaces.value.unshift(ws)
    return ws as WorkspaceInfo
  }

  async function fetchWorkspaceTemplates(visibility?: string) {
    const params: Record<string, string> = {}
    if (visibility) params.visibility = visibility
    const res = await api.get('/workspaces/templates', { params })
    return res.data.data as WorkspaceTemplateItem[]
  }

  async function saveAsTemplate(data: { name: string; description?: string; workspace_id: string; visibility?: string }) {
    const res = await api.post('/workspaces/templates', data)
    return res.data.data
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

  async function addAgent(workspaceId: string, instanceId: string, displayName?: string, hexQ?: number, hexR?: number, installGeneSlugs?: string[]) {
    const body: Record<string, unknown> = { instance_id: instanceId }
    if (displayName) body.display_name = displayName
    if (hexQ !== undefined) { body.hex_q = hexQ; body.hex_r = hexR ?? 0 }
    if (installGeneSlugs?.length) body.install_gene_slugs = installGeneSlugs
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

  async function updateAgentThemeColor(workspaceId: string, instanceId: string, color: string) {
    await updateAgent(workspaceId, instanceId, { theme_color: color })
  }

  // ── Blackboard ────────────────────────────────────

  async function fetchBlackboard(workspaceId: string) {
    try {
      const res = await api.get(`/workspaces/${workspaceId}/blackboard`)
      blackboard.value = res.data.data
      fetchSchedules(workspaceId)
    } catch (e) {
      console.error('fetchBlackboard error:', e)
    }
  }

  async function updateBlackboard(workspaceId: string, content: string) {
    const res = await api.put(`/workspaces/${workspaceId}/blackboard`, { content })
    blackboard.value = res.data.data
  }

  async function fetchTasks(workspaceId: string, status?: string, excludeArchived = true) {
    const params = new URLSearchParams()
    if (status) params.set('status', status)
    if (!excludeArchived) params.set('exclude_archived', 'false')
    const res = await api.get(`/workspaces/${workspaceId}/blackboard/tasks?${params.toString()}`)
    return (res.data.data || []) as TaskInfo[]
  }

  async function createTask(workspaceId: string, data: { title: string; description?: string; priority?: string; assignee_id?: string; estimated_value?: number }) {
    const res = await api.post(`/workspaces/${workspaceId}/blackboard/tasks`, data)
    return res.data.data as TaskInfo
  }

  async function updateTask(workspaceId: string, taskId: string, data: Record<string, unknown>) {
    const res = await api.put(`/workspaces/${workspaceId}/blackboard/tasks/${taskId}`, data)
    return res.data.data as TaskInfo
  }

  async function archiveTask(workspaceId: string, taskId: string) {
    const res = await api.post(`/workspaces/${workspaceId}/blackboard/tasks/${taskId}/archive`)
    return res.data.data as TaskInfo
  }

  async function fetchObjectives(workspaceId: string) {
    const res = await api.get(`/workspaces/${workspaceId}/blackboard/objectives`)
    return (res.data.data || []) as ObjectiveInfo[]
  }

  async function createObjective(workspaceId: string, data: { title: string; description?: string }) {
    const res = await api.post(`/workspaces/${workspaceId}/blackboard/objectives`, data)
    return res.data.data as ObjectiveInfo
  }

  async function updateObjective(workspaceId: string, objectiveId: string, data: Record<string, unknown>) {
    const res = await api.put(`/workspaces/${workspaceId}/blackboard/objectives/${objectiveId}`, data)
    return res.data.data as ObjectiveInfo
  }

  // ── Schedules ───────────────────────────────────────

  async function fetchSchedules(workspaceId: string) {
    try {
      const res = await api.get(`/workspaces/${workspaceId}/schedules`)
      schedules.value = (res.data.data?.schedules || []) as ScheduleInfo[]
    } catch (e) {
      console.error('fetchSchedules error:', e)
    }
  }

  async function toggleScheduleActive(workspaceId: string, scheduleId: string, isActive: boolean) {
    await api.put(`/workspaces/${workspaceId}/schedules/${scheduleId}`, { is_active: isActive })
    const idx = schedules.value.findIndex(s => s.id === scheduleId)
    if (idx >= 0) schedules.value[idx].is_active = isActive
  }

  // ── Performance ──────────────────────────────────────

  async function fetchPerformance(workspaceId: string) {
    const res = await api.get(`/workspaces/${workspaceId}/performance`)
    return res.data.data as Record<string, unknown>
  }

  async function collectPerformance(workspaceId: string) {
    const res = await api.post(`/workspaces/${workspaceId}/performance/collect`)
    return res.data.data as Record<string, unknown>
  }

  async function attributeTokens(workspaceId: string) {
    const res = await api.post(`/workspaces/${workspaceId}/performance/attribute-tokens`)
    return res.data.data as Record<string, unknown>
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
        attachments: (m.attachments as FileAttachment[]) || undefined,
      }))
    } catch (e) {
      console.error('fetchChatHistory error:', e)
    }
  }

  async function sendWorkspaceMessage(
    workspaceId: string,
    message: string,
    mentions?: string[],
    fileIds?: string[],
    attachments?: FileAttachment[],
  ) {
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
      attachments: attachments || undefined,
    }
    chatMessages.value.push(userMsg)

    try {
      const body: Record<string, unknown> = { message }
      if (mentions && mentions.length > 0) body.mentions = mentions
      if (fileIds && fileIds.length > 0) body.file_ids = fileIds
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
        id: (data.envelope_id as string) || `stream-${instanceId}-${Date.now()}`,
        sender_type: 'agent',
        sender_id: instanceId,
        sender_name: agentName,
        content,
        message_type: 'chat',
        created_at: new Date().toISOString(),
        streaming: true,
        trace_id: data.trace_id as string | undefined,
        causation_id: data.causation_id as string | undefined,
        envelope_id: data.envelope_id as string | undefined,
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
      id: (data.envelope_id as string) || `collab-${instanceId}-${Date.now()}`,
      sender_type: 'agent',
      sender_id: instanceId,
      sender_name: agentName,
      content,
      message_type: 'collaboration',
      created_at: new Date().toISOString(),
      trace_id: data.trace_id as string | undefined,
      causation_id: data.causation_id as string | undefined,
      intent: data.intent as string | undefined,
      priority: data.priority as string | undefined,
      envelope_id: data.envelope_id as string | undefined,
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
      content: content || `${agentName} 已加入办公室`,
      message_type: 'system',
      created_at: new Date().toISOString(),
    })
    _incrementUnread()
  }

  // ── SSE ───────────────────────────────────────────

  let eventSource: EventSource | null = null
  let externalCallback: ChatSSECallback | null = null
  let _reconnectAttempts = 0
  let _reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let _lastEventId = ''
  const _recentMessageIds = new Set<string>()
  const _MAX_DEDUP_IDS = 1000

  function _isDuplicateMessage(id: string): boolean {
    if (!id) return false
    if (_recentMessageIds.has(id)) return true
    _recentMessageIds.add(id)
    if (_recentMessageIds.size > _MAX_DEDUP_IDS) {
      const first = _recentMessageIds.values().next().value
      if (first) _recentMessageIds.delete(first)
    }
    return false
  }

  function _getReconnectDelay(): number {
    const base = 1000
    const max = 30000
    const delay = Math.min(base * Math.pow(2, _reconnectAttempts), max)
    return delay + Math.random() * 500
  }

  async function connectSSE(workspaceId: string, onEvent?: ChatSSECallback) {
    disconnectSSE()
    externalCallback = onEvent || null

    let token = ''
    try {
      const { data } = await api.post('/workspaces/sse-token')
      token = data?.data?.sse_token || ''
    } catch { /* ignore */ }
    if (!token) token = localStorage.getItem('portal_token') || ''

    let sseUrl = `/api/v1/workspaces/${workspaceId}/events?token=${token}`
    if (_lastEventId) {
      sseUrl += `&after=${encodeURIComponent(_lastEventId)}`
    }
    eventSource = new EventSource(sseUrl)

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

    eventSource.addEventListener('agent:status_snapshot', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        if (currentWorkspace.value && Array.isArray(data.agents)) {
          for (const item of data.agents) {
            const agent = currentWorkspace.value.agents.find(
              (a: { instance_id: string }) => a.instance_id === item.instance_id,
            )
            if (agent) agent.sse_connected = item.sse_connected
          }
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

    for (const evtName of ['task:created', 'task:updated', 'task:archived', 'task:status_changed']) {
      eventSource.addEventListener(evtName, (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data)
          externalCallback?.(evtName, data)
        } catch { /* ignore */ }
      })
    }

    for (const evtName of ['objective:created', 'objective:updated']) {
      eventSource.addEventListener(evtName, (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data)
          externalCallback?.(evtName, data)
        } catch { /* ignore */ }
      })
    }

    for (const evtName of ['post:created', 'post:updated', 'post:deleted', 'post:pinned', 'reply:created', 'file:created', 'file:uploaded', 'file:deleted']) {
      eventSource.addEventListener(evtName, (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data)
          externalCallback?.(evtName, data)
        } catch { /* ignore */ }
      })
    }

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

    const geneEvents = [
      'gene:install_start', 'gene:learn_start', 'gene:learn_decided',
      'gene:installed', 'gene:learn_failed', 'gene:variant_published',
      'agent:skill_learned',
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

    const topologyEvents = [
      'corridor:hex_placed', 'corridor:hex_updated', 'corridor:hex_removed',
      'connection:created', 'connection:removed',
      'human:hex_placed', 'human:hex_removed', 'human:channel_updated',
    ]
    for (const eventName of topologyEvents) {
      eventSource.addEventListener(eventName, (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data)
          externalCallback?.(eventName, data)
        } catch { /* ignore */ }
        fetchTopology(workspaceId)
      })
    }

    const humanNotifyEvents = [
      'human:message_delivered', 'human:message_received',
    ]
    for (const eventName of humanNotifyEvents) {
      eventSource.addEventListener(eventName, (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data)
          externalCallback?.(eventName, data)
        } catch { /* ignore */ }
      })
    }

    eventSource.onerror = () => {
      if (eventSource?.readyState === EventSource.CLOSED) {
        _reconnectAttempts++
        const delay = _getReconnectDelay()
        _reconnectTimer = setTimeout(() => {
          connectSSE(workspaceId, externalCallback || undefined)
        }, delay)
      }
    }

    _reconnectAttempts = 0
  }

  function disconnectSSE() {
    if (_reconnectTimer) {
      clearTimeout(_reconnectTimer)
      _reconnectTimer = null
    }
    _reconnectAttempts = 0
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

  // ── Corridor & Topology ──────────────────────────────

  async function fetchTopology(workspaceId: string) {
    try {
      const res = await api.get(`/workspaces/${workspaceId}/topology`)
      topology.value = res.data.data
    } catch (e) {
      console.error('fetchTopology error:', e)
    }
    fetchMessageFlowStats(workspaceId)
    fetchHeatmap(workspaceId)
  }

  async function fetchMessageFlowStats(workspaceId: string) {
    try {
      const res = await api.get(`/workspaces/${workspaceId}/topology/message-flow`)
      messageFlowStats.value = res.data.data || []
    } catch {
      messageFlowStats.value = []
    }
  }

  async function fetchHeatmap(workspaceId: string) {
    try {
      const res = await api.get(`/workspaces/${workspaceId}/messages/heatmap`)
      heatmap.value = res.data.data || []
    } catch {
      heatmap.value = []
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

  async function createCorridorHex(workspaceId: string, hexQ: number, hexR: number, displayName = '') {
    const res = await api.post(`/workspaces/${workspaceId}/corridor-hexes`, {
      hex_q: hexQ, hex_r: hexR, display_name: displayName,
    })
    const ch = res.data.data
    corridorHexes.value.push(ch)
    await fetchTopology(workspaceId)
    return ch as CorridorHexInfo
  }

  async function moveCorridorHex(workspaceId: string, hexId: string, hexQ: number, hexR: number) {
    await api.put(`/workspaces/${workspaceId}/corridor-hexes/${hexId}`, { hex_q: hexQ, hex_r: hexR })
    const idx = corridorHexes.value.findIndex(c => c.id === hexId)
    if (idx >= 0) { corridorHexes.value[idx].hex_q = hexQ; corridorHexes.value[idx].hex_r = hexR }
    await fetchTopology(workspaceId)
  }

  async function renameCorridorHex(workspaceId: string, hexId: string, displayName: string) {
    await api.put(`/workspaces/${workspaceId}/corridor-hexes/${hexId}`, { display_name: displayName })
    const idx = corridorHexes.value.findIndex(c => c.id === hexId)
    if (idx >= 0) corridorHexes.value[idx].display_name = displayName
    await fetchTopology(workspaceId)
  }

  async function deleteCorridorHex(workspaceId: string, hexId: string) {
    await api.delete(`/workspaces/${workspaceId}/corridor-hexes/${hexId}`)
    corridorHexes.value = corridorHexes.value.filter(c => c.id !== hexId)
    await fetchTopology(workspaceId)
  }

  async function fetchConnections(workspaceId: string) {
    try {
      const res = await api.get(`/workspaces/${workspaceId}/connections`)
      connections.value = res.data.data || []
    } catch (e) {
      console.error('fetchConnections error:', e)
    }
  }

  async function createConnection(workspaceId: string, aQ: number, aR: number, bQ: number, bR: number) {
    const res = await api.post(`/workspaces/${workspaceId}/connections`, {
      hex_a_q: aQ, hex_a_r: aR, hex_b_q: bQ, hex_b_r: bR,
    })
    const conn = res.data.data
    connections.value.push(conn)
    await fetchTopology(workspaceId)
    return conn as ConnectionInfo
  }

  async function deleteConnection(workspaceId: string, connId: string) {
    await api.delete(`/workspaces/${workspaceId}/connections/${connId}`)
    connections.value = connections.value.filter(c => c.id !== connId)
    await fetchTopology(workspaceId)
  }

  const humanHexes = ref<HumanHexInfo[]>([])

  async function fetchHumanHexes(workspaceId: string) {
    await fetchTopology(workspaceId)
    if (topology.value) {
      humanHexes.value = topology.value.nodes
        .filter((n: TopologyNode) => n.node_type === 'human')
        .map((n: TopologyNode) => ({
          id: n.entity_id || '',
          workspace_id: workspaceId,
          user_id: (n.extra?.user_id as string) || '',
          hex_q: n.hex_q,
          hex_r: n.hex_r,
          display_name: n.display_name || null,
          display_color: (n.extra?.display_color as string) || '#f59e0b',
          channel_type: (n.extra?.channel_type as string) || null,
          channel_config: (n.extra?.channel_config as Record<string, unknown>) || null,
          created_at: '',
        }))
    }
  }

  async function createHumanHex(workspaceId: string, userId: string, hexQ: number, hexR: number, displayColor?: string, displayName?: string) {
    const payload: Record<string, unknown> = { user_id: userId, hex_q: hexQ, hex_r: hexR }
    if (displayColor) payload.display_color = displayColor
    if (displayName) payload.display_name = displayName
    await api.post(`/workspaces/${workspaceId}/human-hexes`, payload)
    await fetchTopology(workspaceId)
  }

  async function moveHumanHex(workspaceId: string, hexId: string, hexQ: number, hexR: number) {
    await api.put(`/workspaces/${workspaceId}/human-hexes/${hexId}`, { hex_q: hexQ, hex_r: hexR })
    await fetchTopology(workspaceId)
  }

  async function updateHumanHexColor(workspaceId: string, hexId: string, color: string) {
    await api.put(`/workspaces/${workspaceId}/human-hexes/${hexId}`, { display_color: color })
    await fetchTopology(workspaceId)
  }

  async function deleteHumanHex(workspaceId: string, hexId: string) {
    await api.delete(`/workspaces/${workspaceId}/human-hexes/${hexId}`)
    await fetchTopology(workspaceId)
  }

  async function renameHumanHex(workspaceId: string, hexId: string, displayName: string) {
    await api.put(`/workspaces/${workspaceId}/human-hexes/${hexId}`, { display_name: displayName })
    await fetchTopology(workspaceId)
  }

  async function updateHumanHexChannel(workspaceId: string, hexId: string, channelType: string, channelConfig: Record<string, unknown>) {
    await api.put(`/workspaces/${workspaceId}/human-hexes/${hexId}`, {
      channel_type: channelType, channel_config: channelConfig,
    })
    await fetchTopology(workspaceId)
  }

  // ── Decoration ─────────────────────────────────────

  async function fetchDecoration(workspaceId: string) {
    try {
      const res = await api.get(`/workspaces/${workspaceId}/decoration`)
      decoration.value = res.data.data
    } catch (e) {
      console.error('fetchDecoration error:', e)
      decoration.value = null
    }
  }

  async function saveDecoration(workspaceId: string, hexes: Record<string, HexDecoration>) {
    try {
      const res = await api.put(`/workspaces/${workspaceId}/decoration`, { hexes })
      decoration.value = res.data.data
    } catch (e) {
      console.error('saveDecoration error:', e)
      throw e
    }
  }

  async function fetchMyPermissions(workspaceId: string) {
    try {
      const res = await api.get(`/workspaces/${workspaceId}/my-permissions`)
      const data = res.data.data
      myPermissions.value = data.permissions || []
      isWorkspaceAdmin.value = data.is_admin || false
      isOrgAdmin.value = data.is_org_admin || false
    } catch (e) {
      console.error('fetchMyPermissions error:', e)
      myPermissions.value = []
      isWorkspaceAdmin.value = false
      isOrgAdmin.value = false
    }
  }

  function hasPermission(perm: string): boolean {
    if (isWorkspaceAdmin.value || isOrgAdmin.value) return true
    return myPermissions.value.includes(perm)
  }

  async function addMember(workspaceId: string, userId: string, permissions: string[] = [], isAdmin = false) {
    await api.post(`/workspaces/${workspaceId}/members`, {
      user_id: userId,
      permissions,
      is_admin: isAdmin,
    })
    await fetchMembers(workspaceId)
  }

  async function updateMember(workspaceId: string, userId: string, permissions?: string[], isAdmin?: boolean) {
    const body: Record<string, unknown> = {}
    if (permissions !== undefined) body.permissions = permissions
    if (isAdmin !== undefined) body.is_admin = isAdmin
    await api.put(`/workspaces/${workspaceId}/members/${userId}`, body)
    await fetchMembers(workspaceId)
  }

  async function removeMember(workspaceId: string, userId: string) {
    await api.delete(`/workspaces/${workspaceId}/members/${userId}`)
    await fetchMembers(workspaceId)
  }

  async function searchOrgUsers(workspaceId: string, query: string) {
    const res = await api.get(`/workspaces/${workspaceId}/search-users`, { params: { q: query } })
    return res.data.data || []
  }

  function resetCurrentState() {
    currentWorkspace.value = null
    blackboard.value = null
    schedules.value = []
    topology.value = null
    decoration.value = null
    members.value = []
    chatMessages.value = []
    corridorHexes.value = []
    connections.value = []
    heatmap.value = []
    typingAgents.value.clear()
    unreadCount.value = 0
    myPermissions.value = []
    isWorkspaceAdmin.value = false
    isOrgAdmin.value = false
  }

  return {
    workspaces,
    currentWorkspace,
    blackboard,
    schedules,
    members,
    loading,
    chatMessages,
    chatLoading,
    typingAgents,
    unreadCount,
    corridorHexes,
    connections,
    topology,
    topologyNodes: computed(() => topology.value?.nodes || []),
    topologyEdges: computed(() => topology.value?.edges || []),
    messageFlowStats,
    heatmap,
    decoration,
    myPermissions,
    isWorkspaceAdmin,
    isOrgAdmin,
    resetCurrentState,
    setChatVisible,
    fileUploadEnabled,
    fetchSystemCapabilities,
    uploadFile,
    getFileUrl,
    fetchWorkspaces,
    fetchWorkspace,
    createWorkspace,
    fetchWorkspaceTemplates,
    saveAsTemplate,
    updateWorkspace,
    deleteWorkspace,
    addAgent,
    removeAgent,
    updateAgent,
    updateAgentThemeColor,
    fetchBlackboard,
    updateBlackboard,
    fetchTasks,
    createTask,
    updateTask,
    archiveTask,
    fetchObjectives,
    createObjective,
    updateObjective,
    fetchSchedules,
    toggleScheduleActive,
    fetchPerformance,
    collectPerformance,
    attributeTokens,
    fetchMembers,
    fetchChatHistory,
    sendWorkspaceMessage,
    sendSystemMessage,
    connectSSE,
    disconnectSSE,
    sendMessage,
    fetchTopology,
    fetchHeatmap,
    fetchCorridorHexes,
    createCorridorHex,
    moveCorridorHex,
    renameCorridorHex,
    deleteCorridorHex,
    fetchConnections,
    createConnection,
    deleteConnection,
    humanHexes,
    fetchHumanHexes,
    createHumanHex,
    moveHumanHex,
    updateHumanHexColor,
    renameHumanHex,
    deleteHumanHex,
    updateHumanHexChannel,
    fetchDecoration,
    saveDecoration,
    fetchMyPermissions,
    hasPermission,
    addMember,
    updateMember,
    removeMember,
    searchOrgUsers,
  }
})
