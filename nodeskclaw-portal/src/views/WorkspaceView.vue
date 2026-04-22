<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, Settings, Maximize2, Minimize2, ZoomIn, ZoomOut, RotateCcw, RefreshCw, MessageSquare, Plus, Keyboard, ChevronDown, X, Bot, ListChecks, AlertTriangle, Wifi, User, Users, MapPin, Focus, Minimize } from 'lucide-vue-next'
import { useWorkspaceStore } from '@/stores/workspace'
import { useAuthStore } from '@/stores/auth'
import { useViewTransition } from '@/composables/useViewTransition'
import Workspace3D from '@/components/hex3d/Workspace3D.vue'
import Workspace2D from '@/components/hex2d/Workspace2D.vue'
import ModeToggle from '@/components/shared/ModeToggle.vue'
import ChatPanel from '@/components/chat/ChatPanel.vue'
import LocaleSelect from '@/components/shared/LocaleSelect.vue'
import BlackboardOverlay from '@/components/blackboard/BlackboardOverlay.vue'
import HexActionDrawer from '@/components/workspace/HexActionDrawer.vue'
import AgentCollaborationPanel from '@/components/workspace/AgentCollaborationPanel.vue'
import AgentDetailDialog from '@/components/workspace/AgentDetailDialog.vue'
import CollaborationTimeline from '@/components/workspace/CollaborationTimeline.vue'
import AddAgentDialog from '@/components/workspace/AddAgentDialog.vue'
import WorkspaceSettings from '@/views/WorkspaceSettings.vue'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import { axialToWorld } from '@/composables/useHexLayout'
import { getCurrentLocale, setCurrentLocale } from '@/i18n'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useWorkspaceStore()
const authStore = useAuthStore()

const locale = ref(getCurrentLocale())
const showSettingsDialog = ref(false)
function onLocaleChange(value: string) {
  locale.value = setCurrentLocale(value)
}

const workspaceId = computed(() => route.params.id as string)
const ws = computed(() => store.currentWorkspace)
const agents = computed(() => ws.value?.agents || [])

const bbTaskCount = computed(() => 0)
const bbBlockedCount = computed(() => 0)
const bbOnlineCount = computed(() => agents.value.filter(a => a.sse_connected).length)
const humanCount = computed(() => store.members.length)
const humanSeatCount = computed(() =>
  store.topologyNodes.filter((n: any) => n.node_type === 'human').length,
)

const enrichedTopologyNodes = computed(() =>
  store.topologyNodes.map((n: any) => {
    if (n.node_type !== 'human' || n.display_name) return n
    const userId = n.extra?.user_id as string | undefined
    if (!userId) return n
    const member = store.members.find((m: any) => m.user_id === userId)
    return member ? { ...n, display_name: member.user_name } : n
  }),
)

const { activeMode, isTransitioning, transitionTo2D, transitionTo3D } = useViewTransition()

const CHAT_OPEN_KEY = 'workspace-chat-open'
const chatOpen = ref(localStorage.getItem(CHAT_OPEN_KEY) === 'true')
const chatSidebarTab = ref<'blackboard' | 'collab-flow'>('blackboard')
const collabTimelineRef = ref<InstanceType<typeof CollaborationTimeline> | null>(null)
const collabPanelOpen = ref(false)
const collabPanelAgent = ref<{ instanceId: string; name: string } | null>(null)
const collabPanelRef = ref<InstanceType<typeof AgentCollaborationPanel> | null>(null)
const bbOpen = ref(false)
const isFullscreen = ref(false)
const focusMode = ref(false)
const selectedAgentId = ref<string | null>(null)
const showShortcutHints = ref(localStorage.getItem('workspace-shortcut-hints') !== 'hidden')
const agentDetailVisible = ref(false)
const agentDetailId = ref<string | null>(null)

function openAgentDetailPage() {
  if (!agentDetailId.value) return
  const r = router.resolve(`/instances/${agentDetailId.value}`)
  window.open(r.href, '_blank')
}

const CHAT_MIN_RATIO = 0.191
const CHAT_MAX_RATIO = 0.618
const CHAT_STORAGE_KEY = 'workspace-chat-width'

function clampChatWidth(px: number): number {
  const vw = window.innerWidth
  return Math.round(Math.min(Math.max(px, vw * CHAT_MIN_RATIO), vw * CHAT_MAX_RATIO))
}

const chatWidth = ref(clampChatWidth(
  Number(localStorage.getItem(CHAT_STORAGE_KEY)) || 400,
))

const isDraggingChat = ref(false)

function onResizeHandlePointerDown(e: PointerEvent) {
  e.preventDefault()
  isDraggingChat.value = true
  const onMove = (ev: PointerEvent) => {
    chatWidth.value = clampChatWidth(window.innerWidth - ev.clientX)
  }
  const onUp = () => {
    isDraggingChat.value = false
    localStorage.setItem(CHAT_STORAGE_KEY, String(chatWidth.value))
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}

function onWindowResize() {
  if (chatOpen.value) {
    chatWidth.value = clampChatWidth(chatWidth.value)
  }
}

function toggleFocusMode() {
  focusMode.value = !focusMode.value
}

watch(chatOpen, (v) => {
  store.setChatVisible(v)
  localStorage.setItem(CHAT_OPEN_KEY, String(v))
}, { immediate: true })

interface SelectedHex {
  q: number
  r: number
  type: 'empty' | 'agent' | 'blackboard' | 'corridor' | 'human'
  agentId?: string
  entityId?: string
}
const selectedHex = ref<SelectedHex | null>(null)
const hexDrawerOpen = ref(false)

const selectedHexPos = computed(() =>
  selectedHex.value ? { q: selectedHex.value.q, r: selectedHex.value.r } : null,
)

const hexAgentInfo = computed(() => {
  if (selectedHex.value?.type !== 'agent' || !selectedHex.value.agentId) return undefined
  const agent = agents.value.find((a) => a.instance_id === selectedHex.value!.agentId)
  return agent ? { id: agent.instance_id, name: agent.display_name || agent.name } : undefined
})

const hexEntityName = computed(() => {
  if (!selectedHex.value?.entityId) return ''
  if (selectedHex.value.type === 'corridor') {
    const node = store.topologyNodes.find((n: any) => n.entity_id === selectedHex.value!.entityId)
    return node?.display_name || ''
  }
  if (selectedHex.value.type === 'human') {
    const node = store.topologyNodes.find((n: any) => n.entity_id === selectedHex.value!.entityId)
    const userId = node?.extra?.user_id as string | undefined
    if (userId) {
      const member = store.members.find((m: any) => m.user_id === userId)
      return member?.user_name || ''
    }
    return ''
  }
  return ''
})

function toggleShortcutHints() {
  showShortcutHints.value = !showShortcutHints.value
  localStorage.setItem('workspace-shortcut-hints', showShortcutHints.value ? 'visible' : 'hidden')
}

const threeRef = ref<HTMLElement | null>(null)
const svgRef = ref<HTMLElement | null>(null)
const workspace3dRef = ref<InstanceType<typeof Workspace3D> | null>(null)
const workspace2dRef = ref<InstanceType<typeof Workspace2D> | null>(null)

interface PerfSummary {
  totalTasks: number
  completedTasks: number
  totalTokenCost: number
  totalValueCreated: number
}
const perfSummary = ref<PerfSummary | null>(null)
const perfLoading = ref(true)
let workspaceBootstrapGeneration = 0

async function loadPerfSummary(wsId: string) {
  perfLoading.value = true
  try {
    const data = await store.fetchPerformance(wsId)
    if (data) {
      perfSummary.value = {
        totalTasks: Number(data.total_tasks) || 0,
        completedTasks: Number(data.completed_tasks) || 0,
        totalTokenCost: Number(data.total_token_cost) || 0,
        totalValueCreated: Number(data.total_value_created) || 0,
      }
    }
  } catch {
    perfSummary.value = null
  } finally {
    perfLoading.value = false
  }
}

async function refreshWorkspaceData(wsId: string) {
  await Promise.all([
    store.fetchWorkspace(wsId),
    store.fetchTopology(wsId),
    store.fetchBlackboard(wsId),
    loadPerfSummary(wsId),
  ])
}

async function bootstrapWorkspaceCritical(wsId: string): Promise<number | null> {
  const generation = ++workspaceBootstrapGeneration
  await Promise.all([
    store.fetchWorkspace(wsId),
    store.fetchMyPermissions(wsId),
    store.fetchBlackboard(wsId),
    store.fetchTopology(wsId),
  ])
  if (generation !== workspaceBootstrapGeneration) return null
  await nextTick()
  if (generation !== workspaceBootstrapGeneration) return null
  return generation
}

async function bootstrapWorkspaceDeferred(wsId: string, generation: number) {
  await Promise.allSettled([
    store.fetchMembers(wsId),
    loadPerfSummary(wsId),
  ])
  if (generation !== workspaceBootstrapGeneration) return
  store.connectSSE(wsId, onSSEEvent)
}

function handleZoomIn() {
  if (activeMode.value === '3d') workspace3dRef.value?.zoomIn()
  else workspace2dRef.value?.zoomIn()
}

function handleZoomOut() {
  if (activeMode.value === '3d') workspace3dRef.value?.zoomOut()
  else workspace2dRef.value?.zoomOut()
}

function handleResetView() {
  if (activeMode.value === '3d') workspace3dRef.value?.resetView()
  else workspace2dRef.value?.resetView()

  const wsId = workspaceId.value
  refreshWorkspaceData(wsId).then(() => {
    if (activeMode.value === '2d') workspace2dRef.value?.flashRefresh()
  })
}

onMounted(async () => {
  store.resetCurrentState()

  const wsId = workspaceId.value
  const generation = await bootstrapWorkspaceCritical(wsId)
  if (generation === null) return

  window.addEventListener('keydown', handleKeydown)
  window.addEventListener('resize', onWindowResize)

  const focusAgentId = route.query.focus_agent as string | undefined
  if (focusAgentId) {
    router.replace({ query: { ...route.query, focus_agent: undefined } })
    await nextTick()
    const agent = agents.value.find(a => a.instance_id === focusAgentId)
    if (agent) {
      const { x, y } = axialToWorld(agent.hex_q, agent.hex_r)
      workspace3dRef.value?.focusOnPosition(x, y)
    }
  }

  void bootstrapWorkspaceDeferred(wsId, generation)
})

onUnmounted(() => {
  store.disconnectSSE()
  window.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('resize', onWindowResize)
})

watch(workspaceId, async (newId, oldId) => {
  if (newId && newId !== oldId) {
    store.resetCurrentState()
    const generation = await bootstrapWorkspaceCritical(newId)
    if (generation === null) return
    void bootstrapWorkspaceDeferred(newId, generation)
  }
})

function onSSEEvent(event: string, data: Record<string, unknown>) {
  if (event === 'agent:skill_learned') {
    const currentUserId = authStore.user?.id
    const audienceUserIds = Array.isArray(data.audience_user_ids)
      ? data.audience_user_ids.filter((id): id is string => typeof id === 'string')
      : []
    if (!currentUserId || !audienceUserIds.includes(currentUserId)) return

    const agentName = typeof data.agent_name === 'string' ? data.agent_name : ''
    const geneName = typeof data.gene_name === 'string' ? data.gene_name : ''
    const summary = typeof data.summary === 'string' ? data.summary.trim() : ''
    if (!agentName || !geneName) return

    toast.info(
      summary
        ? t('workspaceView.skillLearnedToastWithSummary', { agentName, geneName, summary })
        : t('workspaceView.skillLearnedToast', { agentName, geneName }),
    )
    return
  }

  if (['task:created', 'task:updated', 'task:archived', 'task:status_changed'].includes(event)) {
    loadPerfSummary(workspaceId.value)
    return
  }

  if (event === 'schedule:consecutive_failures') {
    const name = typeof data.name === 'string' ? data.name : ''
    const count = typeof data.consecutive_failures === 'number' ? data.consecutive_failures : 0
    if (name && count) {
      toast.warning(t('blackboard.scheduleConsecutiveFailureAlert', { name, count }))
    }
    return
  }

  if (event === 'agent:collaboration') {
    const instanceId = data.instance_id as string
    const target = data.target as string
    if (instanceId && target) {
      if (activeMode.value === '2d') {
        workspace2dRef.value?.triggerMessageFlow(instanceId, target)
      } else {
        workspace3dRef.value?.triggerMessageFlow(instanceId, target)
      }
    }
    if (collabPanelOpen.value && collabPanelRef.value) {
      collabPanelRef.value.addLiveMessage(data)
    }
    if (chatSidebarTab.value === 'collab-flow' && collabTimelineRef.value) {
      collabTimelineRef.value.addLiveMessage(data)
    }
  }
}

function onReplayFlow(sourceInstanceId: string, target: string) {
  if (activeMode.value === '2d') {
    workspace2dRef.value?.triggerMessageFlow(sourceInstanceId, target)
  } else {
    workspace3dRef.value?.triggerMessageFlow(sourceInstanceId, target)
  }
}

function toggleMode() {
  if (isTransitioning.value) return
  if (activeMode.value === '3d') {
    transitionTo2D(threeRef.value, svgRef.value)
  } else {
    transitionTo3D(threeRef.value, svgRef.value)
  }
}

let clickHandled = false

function onHexClick(payload: { q: number, r: number, type: 'empty' | 'agent' | 'blackboard' | 'corridor' | 'human', agentId?: string, entityId?: string }) {
  clickHandled = true

  if (isPickingHexForAgent.value) {
    if (payload.type === 'empty') {
      cancelPickHexMode()
      openAddAgentDialog(payload.q, payload.r)
    }
    return
  }

  if (isMovingHex.value) {
    if (payload.type === 'empty') {
      moveHexTo(payload.q, payload.r)
    }
    return
  }

  if (selectedHex.value &&
    selectedHex.value.q === payload.q &&
    selectedHex.value.r === payload.r) {
    selectedHex.value = null
    hexDrawerOpen.value = false
    if (payload.type !== 'agent') selectedAgentId.value = null
    return
  }

  selectedHex.value = payload
  hexDrawerOpen.value = true

  if (payload.type === 'agent' && payload.agentId) {
    selectedAgentId.value = payload.agentId
  } else {
    selectedAgentId.value = null
  }
}

function onAgentDblClick(_id: string) {
  clickHandled = true
  collabPanelOpen.value = false
  chatOpen.value = true
}

async function onHexAction(action: string) {
  switch (action) {
    case 'add-agent': {
      const q = selectedHex.value?.q
      const r = selectedHex.value?.r
      hexDrawerOpen.value = false
      openAddAgentDialog(q, r)
      break
    }
    case 'open-chat':
      collabPanelOpen.value = false
      chatOpen.value = true
      hexDrawerOpen.value = false
      break
    case 'view-collaboration':
      if (selectedHex.value?.agentId) {
        const agent = agents.value.find(a => a.instance_id === selectedHex.value!.agentId)
        if (agent) {
          collabPanelAgent.value = { instanceId: agent.instance_id, name: agent.display_name || agent.name }
          chatOpen.value = false
          collabPanelOpen.value = true
        }
      }
      hexDrawerOpen.value = false
      break
    case 'view-detail':
      if (selectedHex.value?.agentId) {
        agentDetailId.value = selectedHex.value.agentId
        agentDetailVisible.value = true
      }
      hexDrawerOpen.value = false
      break
    case 'remove-agent':
      if (selectedHex.value?.agentId) {
        try {
          await store.removeAgent(workspaceId.value, selectedHex.value.agentId)
          toast.success(t('hexAction.agentRemoved'))
        } catch {
          toast.error(t('hexAction.removeFailed'))
        }
        selectedHex.value = null
        hexDrawerOpen.value = false
        selectedAgentId.value = null
      }
      break
    case 'view-blackboard':
      bbOpen.value = true
      hexDrawerOpen.value = false
      break
    case 'place-corridor': {
      const q = selectedHex.value?.q
      const r = selectedHex.value?.r
      if (q !== undefined && r !== undefined) {
        store.createCorridorHex(workspaceId.value, q, r)
      }
      hexDrawerOpen.value = false
      break
    }
    case 'place-human': {
      const q = selectedHex.value?.q
      const r = selectedHex.value?.r
      if (q !== undefined && r !== undefined) {
        if (availableMembers.value.length === 0) {
          toast.info(t('hexAction.noAvailableMembers'))
        } else {
          pendingHumanHex.value = { q, r }
          showMemberPicker.value = true
        }
      }
      hexDrawerOpen.value = false
      break
    }
    case 'move-hex':
      enterMoveMode()
      break
    case 'rename-corridor':
      openRenameDialog()
      break
    case 'rename-agent':
      openRenameAgentDialog()
      break
    case 'remove-corridor':
      if (selectedHex.value?.entityId) {
        try {
          await store.deleteCorridorHex(workspaceId.value, selectedHex.value.entityId)
          toast.success(t('hexAction.corridorRemoved'))
        } catch {
          toast.error(t('hexAction.removeFailed'))
        }
        selectedHex.value = null
        hexDrawerOpen.value = false
      }
      break
    case 'change-agent-color':
      if (selectedAgentId.value) {
        pendingAgentColorId.value = selectedAgentId.value
        showAgentColorPicker.value = true
      }
      hexDrawerOpen.value = false
      break
    case 'change-color':
      if (selectedHex.value?.entityId) {
        pendingColorHexId.value = selectedHex.value.entityId
        showColorPicker.value = true
      }
      hexDrawerOpen.value = false
      break
    case 'remove-human':
      if (selectedHex.value?.entityId) {
        try {
          await store.deleteHumanHex(workspaceId.value, selectedHex.value.entityId)
          toast.success(t('hexAction.humanRemoved'))
        } catch {
          toast.error(t('hexAction.removeFailed'))
        }
        selectedHex.value = null
        hexDrawerOpen.value = false
      }
      break
    case 'rename-human':
      openRenameHumanDialog()
      break
    case 'focus-hex': {
      const q = selectedHex.value?.q
      const r = selectedHex.value?.r
      if (q !== undefined && r !== undefined) {
        if (activeMode.value === '3d') {
          const { x, y } = axialToWorld(q, r)
          workspace3dRef.value?.focusOnPosition(x, y)
        } else {
          workspace2dRef.value?.focusOnHex(q, r)
        }
      }
      hexDrawerOpen.value = false
      break
    }
  }
}

function closeHexDrawer() {
  selectedHex.value = null
  hexDrawerOpen.value = false
  selectedAgentId.value = null
}

const showRenameDialog = ref(false)
const renameValue = ref('')
const renameSaving = ref(false)
const renameHexId = ref('')

function openRenameDialog() {
  renameHexId.value = selectedHex.value?.entityId || ''
  renameValue.value = hexEntityName.value
  showRenameDialog.value = true
  hexDrawerOpen.value = false
}

async function handleRenameCorridor() {
  const name = renameValue.value.trim()
  if (!renameHexId.value) return
  renameSaving.value = true
  try {
    await store.renameCorridorHex(workspaceId.value, renameHexId.value, name)
    toast.success(t('hexAction.corridorRenamed'))
    showRenameDialog.value = false
  } finally {
    renameSaving.value = false
  }
}

const showRenameHumanDialog = ref(false)
const renameHumanValue = ref('')
const renameHumanSaving = ref(false)
const renameHumanHexId = ref('')

function openRenameHumanDialog() {
  renameHumanHexId.value = selectedHex.value?.entityId || ''
  const node = enrichedTopologyNodes.value.find((n: any) => n.entity_id === renameHumanHexId.value && n.node_type === 'human')
  renameHumanValue.value = node?.display_name || ''
  showRenameHumanDialog.value = true
  hexDrawerOpen.value = false
}

async function handleRenameHuman() {
  const name = renameHumanValue.value.trim()
  if (!renameHumanHexId.value) return
  renameHumanSaving.value = true
  try {
    await store.renameHumanHex(workspaceId.value, renameHumanHexId.value, name)
    toast.success(t('hexAction.humanRenamed'))
    showRenameHumanDialog.value = false
  } finally {
    renameHumanSaving.value = false
  }
}

const showRenameAgentDialog = ref(false)
const renameAgentDisplayName = ref('')
const renameAgentLabel = ref('')
const renameAgentSaving = ref(false)
const renameAgentInstanceId = ref('')
const renameAgentOriginalName = ref('')

function openRenameAgentDialog() {
  if (!selectedHex.value?.agentId) return
  const agent = agents.value.find(a => a.instance_id === selectedHex.value!.agentId)
  if (!agent) return
  renameAgentInstanceId.value = agent.instance_id
  renameAgentOriginalName.value = agent.name
  renameAgentDisplayName.value = agent.display_name || ''
  renameAgentLabel.value = agent.label || ''
  showRenameAgentDialog.value = true
  hexDrawerOpen.value = false
}

async function handleRenameAgent() {
  if (!renameAgentInstanceId.value) return
  renameAgentSaving.value = true
  try {
    await store.updateAgent(workspaceId.value, renameAgentInstanceId.value, {
      display_name: renameAgentDisplayName.value.trim(),
      label: renameAgentLabel.value.trim(),
    })
    toast.success(t('hexAction.agentRenamed'))
    showRenameAgentDialog.value = false
  } finally {
    renameAgentSaving.value = false
  }
}

const showMemberPicker = ref(false)
const pendingHumanHex = ref<{ q: number; r: number } | null>(null)

const availableMembers = computed(() => store.members)

async function pickMember(userId: string, userName?: string) {
  const hex = pendingHumanHex.value
  if (!hex) return
  showMemberPicker.value = false
  await store.createHumanHex(workspaceId.value, userId, hex.q, hex.r, undefined, userName || undefined)
  pendingHumanHex.value = null
}

const showColorPicker = ref(false)
const pendingColorHexId = ref('')
const COLOR_PRESETS = [
  '#f59e0b', '#ef4444', '#22c55e', '#3b82f6',
  '#a855f7', '#ec4899', '#06b6d4', '#f97316',
]

async function pickColor(color: string) {
  const hexId = pendingColorHexId.value
  if (!hexId) return
  showColorPicker.value = false
  await store.updateHumanHexColor(workspaceId.value, hexId, color)
  pendingColorHexId.value = ''
}

const showAgentColorPicker = ref(false)
const pendingAgentColorId = ref('')

async function pickAgentColor(color: string) {
  const agentId = pendingAgentColorId.value
  if (!agentId) return
  showAgentColorPicker.value = false
  await store.updateAgentThemeColor(workspaceId.value, agentId, color)
  pendingAgentColorId.value = ''
}

function onCanvasAreaClick() {
  nextTick(() => {
    if (!clickHandled) {
      selectedAgentId.value = null
      selectedHex.value = null
      hexDrawerOpen.value = false
    }
    clickHandled = false
  })
}

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen()
    isFullscreen.value = true
  } else {
    document.exitFullscreen()
    isFullscreen.value = false
  }
}

function goBack() {
  router.push('/')
}

const PAN_KEYS = new Set(['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'w', 'W', 'a', 'A', 's', 'S', 'd', 'D'])

function panCanvas(key: string) {
  const k = key.toLowerCase()
  const dx = (k === 'arrowright' || k === 'd') ? 1 : (k === 'arrowleft' || k === 'a') ? -1 : 0
  const dy = (k === 'arrowdown' || k === 's') ? 1 : (k === 'arrowup' || k === 'w') ? -1 : 0
  if (activeMode.value === '3d') {
    workspace3dRef.value?.panBy(dx, dy)
  } else {
    workspace2dRef.value?.panBy(dx, dy)
  }
}

// ── Move Mode ────────────────────────────────────────
const toast = useToast()
const { confirm } = useConfirm()

const restartingAll = ref(false)
const hasRestartableAgents = computed(() => agents.value.some(a => a.status === 'running' || a.status === 'learning'))

async function handleRestartAll() {
  const ok = await confirm({
    title: t('workspaceView.restartAll'),
    description: t('workspaceView.restartAllConfirm'),
    variant: 'danger',
  })
  if (!ok) return
  restartingAll.value = true
  try {
    const result = await store.restartAllInstances(workspaceId.value)
    if (result.failed > 0) {
      toast.warning(t('workspaceView.restartAllPartial', { succeeded: result.succeeded, failed: result.failed }))
    } else {
      toast.success(t('workspaceView.restartAllSuccess', { succeeded: result.succeeded }))
    }
  } catch (e: any) {
    toast.error(e?.response?.data?.detail?.message || t('workspaceView.restartAllFailed'))
  } finally {
    restartingAll.value = false
  }
}

type MovingHexSource = {
  type: 'agent' | 'corridor' | 'human'
  id: string
  q: number
  r: number
}
const isMovingHex = ref(false)
const movingHexSource = ref<MovingHexSource | null>(null)

function enterMoveMode() {
  cancelPickHexMode()
  if (!selectedHex.value) return
  const hex = selectedHex.value
  let source: MovingHexSource | null = null
  if (hex.type === 'agent' && hex.agentId) {
    source = { type: 'agent', id: hex.agentId, q: hex.q, r: hex.r }
  } else if (hex.type === 'corridor' && hex.entityId) {
    source = { type: 'corridor', id: hex.entityId, q: hex.q, r: hex.r }
  } else if (hex.type === 'human' && hex.entityId) {
    source = { type: 'human', id: hex.entityId, q: hex.q, r: hex.r }
  }
  if (!source) return
  movingHexSource.value = source
  isMovingHex.value = true
  hexDrawerOpen.value = false
}

function cancelMoveMode() {
  isMovingHex.value = false
  movingHexSource.value = null
}

async function moveHexTo(targetQ: number, targetR: number) {
  const src = movingHexSource.value
  if (!src) return
  try {
    if (src.type === 'agent') {
      await store.updateAgent(workspaceId.value, src.id, { hex_q: targetQ, hex_r: targetR })
    } else if (src.type === 'corridor') {
      await store.moveCorridorHex(workspaceId.value, src.id, targetQ, targetR)
    } else if (src.type === 'human') {
      await store.moveHumanHex(workspaceId.value, src.id, targetQ, targetR)
    }
    toast.success(t('hexAction.moveSuccess', { q: targetQ, r: targetR }))
    selectedHex.value = null
    selectedAgentId.value = null
  } finally {
    cancelMoveMode()
  }
}

const isPickingHexForAgent = ref(false)

const addAgentDialogVisible = ref(false)
const addAgentHexQ = ref<number | undefined>()
const addAgentHexR = ref<number | undefined>()

function openAddAgentDialog(hexQ?: number, hexR?: number) {
  addAgentHexQ.value = hexQ
  addAgentHexR.value = hexR
  addAgentDialogVisible.value = true
}

function onAgentAdded() {
  addAgentDialogVisible.value = false
}

function enterPickHexMode() {
  cancelMoveMode()
  isPickingHexForAgent.value = true
  selectedHex.value = null
  hexDrawerOpen.value = false
}

function cancelPickHexMode() {
  isPickingHexForAgent.value = false
}

const highlightEmptyHexes = computed(() => isMovingHex.value || isPickingHexForAgent.value)

function handleKeydown(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement)?.tagName?.toLowerCase()
  if (tag === 'input' || tag === 'textarea' || (e.target as HTMLElement)?.isContentEditable) return

  if (e.key === 'Escape') {
    if (focusMode.value) {
      focusMode.value = false
      e.preventDefault()
      return
    }
    if (isPickingHexForAgent.value) {
      cancelPickHexMode()
      e.preventDefault()
      return
    }
    if (isMovingHex.value) {
      cancelMoveMode()
    } else {
      selectedAgentId.value = null
      selectedHex.value = null
      hexDrawerOpen.value = false
    }
    e.preventDefault()
    return
  }

  if (PAN_KEYS.has(e.key)) {
    e.preventDefault()
    panCanvas(e.key)
    return
  }

  if (e.key === '+' || e.key === '=') {
    e.preventDefault()
    handleZoomIn()
    return
  }

  if (e.key === '-') {
    e.preventDefault()
    handleZoomOut()
    return
  }

  if (e.key === '0') {
    e.preventDefault()
    handleResetView()
  }
}
</script>

<template>
  <div class="flex flex-col h-screen overflow-hidden bg-background" :class="{ 'drag-no-select': isDraggingChat }">
    <!-- Toolbar -->
    <div class="flex items-center justify-between px-4 py-2 border-b border-border bg-background/80 backdrop-blur-sm shrink-0 z-10">
      <div class="flex items-center gap-3">
        <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" @click="goBack">
          <ArrowLeft class="w-4 h-4" />
        </button>
        <div
          v-if="ws"
          class="flex items-center gap-2 min-w-0"
        >
          <div
            class="w-6 h-6 rounded flex items-center justify-center text-xs shrink-0"
            :style="{ backgroundColor: ws.color + '22', color: ws.color }"
          >
            <Bot v-if="ws.icon === 'bot'" class="w-3.5 h-3.5" />
            <template v-else>{{ ws.icon }}</template>
          </div>
          <span class="font-semibold text-sm truncate max-w-[10rem] sm:max-w-[14rem] md:max-w-[20rem]">{{ ws.name }}</span>
        </div>
        <button
          v-if="store.hasPermission('manage_agents')"
          class="flex items-center gap-1 px-2.5 py-1 rounded-lg border border-dashed text-xs transition-colors"
          :class="isPickingHexForAgent
            ? 'border-primary bg-primary/10 text-primary'
            : 'border-border text-muted-foreground hover:text-foreground hover:border-foreground/30'"
          :title="t('workspaceView.addAgent')"
          @click="isPickingHexForAgent ? cancelPickHexMode() : enterPickHexMode()"
        >
          <Plus class="w-3.5 h-3.5" />
          <span class="hidden xl:inline">{{ t('workspaceView.addAgent') }}</span>
        </button>

        <div class="w-px h-5 bg-border" />

        <div class="flex items-center gap-3 text-xs text-muted-foreground">
          <span class="flex items-center gap-1">
            <ListChecks class="w-3.5 h-3.5" />
            <span class="hidden xl:inline">{{ t('workspaceView.bbTasks') }}</span> {{ bbTaskCount }}
          </span>
          <span class="flex items-center gap-1" :class="bbBlockedCount > 0 ? 'text-amber-500' : ''">
            <AlertTriangle class="w-3.5 h-3.5" />
            <span class="hidden xl:inline">{{ t('workspaceView.bbBlocked') }}</span> {{ bbBlockedCount }}
          </span>
          <span class="flex items-center gap-1" :class="bbOnlineCount > 0 ? 'text-green-500' : ''">
            <Wifi class="w-3.5 h-3.5" />
            <span class="hidden xl:inline">{{ t('workspaceView.bbOnline') }}</span> {{ bbOnlineCount }}
          </span>
          <span class="flex items-center gap-1">
            <Users class="w-3.5 h-3.5" />
            <span class="hidden xl:inline">{{ t('workspaceView.bbHumans') }}</span> {{ humanCount }}
          </span>
          <span class="flex items-center gap-1">
            <MapPin class="w-3.5 h-3.5" />
            <span class="hidden xl:inline">{{ t('workspaceView.bbHumanSeats') }}</span> {{ humanSeatCount }}
          </span>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <button
          v-if="store.hasPermission('manage_agents')"
          class="p-1.5 rounded-lg hover:bg-muted transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          :title="hasRestartableAgents ? t('workspaceView.restartAll') : t('workspaceView.restartAllNoInstances')"
          :disabled="restartingAll || !hasRestartableAgents"
          @click="handleRestartAll"
        >
          <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': restartingAll }" />
        </button>

        <div v-if="store.hasPermission('manage_agents')" class="w-px h-5 bg-border" />

        <div class="flex items-center gap-0.5 mr-1">
          <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" :title="t('workspaceView.zoomIn')" @click="handleZoomIn">
            <ZoomIn class="w-4 h-4" />
          </button>
          <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" :title="t('workspaceView.zoomOut')" @click="handleZoomOut">
            <ZoomOut class="w-4 h-4" />
          </button>
          <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" :title="t('workspaceView.resetView')" @click="handleResetView">
            <RotateCcw class="w-4 h-4" />
          </button>
        </div>

        <div class="w-px h-5 bg-border" />

        <ModeToggle :mode="activeMode" @toggle="toggleMode" />
        <LocaleSelect :model-value="locale" @update:model-value="onLocaleChange" />
        <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" @click="toggleFullscreen">
          <Minimize2 v-if="isFullscreen" class="w-4 h-4" />
          <Maximize2 v-else class="w-4 h-4" />
        </button>
        <button
          class="relative p-1.5 rounded-lg hover:bg-muted transition-colors"
          :class="{ 'bg-primary/10 text-primary': chatOpen }"
          title="Group Chat"
          @click="chatOpen = !chatOpen"
        >
          <MessageSquare class="w-4 h-4" />
          <span
            v-if="!chatOpen && store.unreadCount > 0"
            class="absolute -top-1 -right-1 min-w-[18px] h-[18px] flex items-center justify-center rounded-full bg-red-500 text-white text-[10px] font-medium px-1 leading-none"
          >
            {{ store.unreadCount > 99 ? '99+' : store.unreadCount }}
          </span>
        </button>
        <button
          v-if="store.hasPermission('manage_settings')"
          class="p-1.5 rounded-lg hover:bg-muted transition-colors"
          @click="showSettingsDialog = true"
        >
          <Settings class="w-4 h-4" />
        </button>
      </div>
    </div>

    <!-- Pick hex for agent hint bar -->
    <Transition name="slide-down">
      <div
        v-if="isPickingHexForAgent"
        class="flex items-center justify-center gap-3 px-4 py-1.5 bg-primary/10 border-b border-primary/30 shrink-0 z-10"
      >
        <span class="text-sm text-primary">{{ t('workspaceView.pickHexHint') }}</span>
        <button
          class="flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-primary/20 hover:bg-primary/30 text-primary transition-colors"
          @click="cancelPickHexMode"
        >
          <X class="w-3 h-3" />
          {{ t('hexAction.cancel') }}
        </button>
      </div>
    </Transition>

    <!-- Move mode hint bar -->
    <Transition name="slide-down">
      <div
        v-if="isMovingHex"
        class="flex items-center justify-center gap-3 px-4 py-1.5 bg-amber-500/10 border-b border-amber-500/30 shrink-0 z-10"
      >
        <span class="text-sm text-amber-400">{{ t('hexAction.moveModeHint') }}</span>
        <button
          class="flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 transition-colors"
          @click="cancelMoveMode"
        >
          <X class="w-3 h-3" />
          {{ t('hexAction.cancel') }}
        </button>
      </div>
    </Transition>

    <!-- Main: Hex Grid + Chat Sidebar -->
    <div class="flex-1 flex min-h-0">
      <!-- Hex Grid -->
      <div class="flex-1 relative min-h-0 min-w-0 overflow-hidden" @click="onCanvasAreaClick">
        <!-- 3D mode -->
        <div
          ref="threeRef"
          class="absolute inset-0"
          :class="{ 'pointer-events-none': activeMode !== '3d' }"
          :style="{ opacity: activeMode === '3d' ? 1 : 0 }"
        >
          <Workspace3D
            ref="workspace3dRef"
            v-if="activeMode === '3d' || isTransitioning"
            :agents="agents"
            :blackboard-content="store.blackboard?.content || ''"
            :selected-agent-id="selectedAgentId"
            :selected-hex="selectedHexPos"
            :topology-nodes="store.topology?.nodes"
            :topology-edges="store.topologyEdges"
            :message-flow-stats="store.messageFlowStats"
            :is-moving-hex="highlightEmptyHexes"
            :moving-hex-source="movingHexSource"
            :perf-summary="perfSummary"
            :perf-loading="perfLoading"
            @hex-click="onHexClick"
            @agent-dblclick="onAgentDblClick"
          />
        </div>

        <!-- 2D mode -->
        <div
          ref="svgRef"
          class="absolute inset-0"
          :class="{ 'pointer-events-none': activeMode !== '2d' }"
          :style="{ opacity: activeMode === '2d' ? 1 : 0 }"
        >
          <Workspace2D
            ref="workspace2dRef"
            v-if="activeMode === '2d' || isTransitioning"
            :agents="agents"
            :blackboard-content="store.blackboard?.content || ''"
            :selected-agent-id="selectedAgentId"
            :selected-hex="selectedHexPos"
            :topology-nodes="enrichedTopologyNodes"
            :topology-edges="store.topologyEdges"
            :message-flow-stats="store.messageFlowStats"
            :is-moving-hex="highlightEmptyHexes"
            :moving-hex-source="movingHexSource"
            :perf-summary="perfSummary"
            :perf-loading="perfLoading"
            @hex-click="onHexClick"
            @agent-dblclick="onAgentDblClick"
          />
        </div>

        <!-- Shortcut Hints Panel -->
        <div class="absolute right-3 bottom-3 z-10">
          <button
            v-if="!showShortcutHints"
            class="p-2 rounded-lg bg-background/70 backdrop-blur-sm border border-border/50 text-muted-foreground hover:text-foreground transition-colors"
            :title="t('workspaceView.showShortcuts')"
            @click="toggleShortcutHints"
          >
            <Keyboard class="w-4 h-4" />
          </button>
          <div
            v-else
            class="rounded-lg bg-background/70 backdrop-blur-sm border border-border/50 text-xs"
          >
            <button
              class="flex items-center gap-1.5 w-full px-3 py-1.5 text-muted-foreground hover:text-foreground transition-colors"
              @click="toggleShortcutHints"
            >
              <Keyboard class="w-3.5 h-3.5" />
              <span>{{ t('workspaceView.shortcuts') }}</span>
              <ChevronDown class="w-3 h-3 ml-auto" />
            </button>
            <div class="border-t border-border/50 px-3 py-2 space-y-1 text-muted-foreground">
              <div class="flex justify-between gap-4">
                <span>{{ t('workspaceView.arrowKeys') }}</span>
                <span class="text-foreground/70">{{ t('workspaceView.panCanvas') }}</span>
              </div>
              <div class="flex justify-between gap-4">
                <span>{{ t('workspaceView.rightDrag') }}</span>
                <span class="text-foreground/70">{{ t('workspaceView.panCanvas') }}</span>
              </div>
              <div class="flex justify-between gap-4">
                <span>+ / -</span>
                <span class="text-foreground/70">{{ t('workspaceView.zoom') }}</span>
              </div>
              <div class="flex justify-between gap-4">
                <span>0</span>
                <span class="text-foreground/70">{{ t('workspaceView.resetViewShort') }}</span>
              </div>
              <div class="flex justify-between gap-4">
                <span>Esc</span>
                <span class="text-foreground/70">{{ t('workspaceView.deselect') }}</span>
              </div>
              <div class="border-t border-border/30 pt-1 mt-1">
                <div class="flex justify-between gap-4">
                  <span>{{ t('workspaceView.singleClick') }}</span>
                  <span class="text-foreground/70">{{ t('workspaceView.openActionPanel') }}</span>
                </div>
                <div class="flex justify-between gap-4">
                  <span>{{ t('workspaceView.doubleClick') }}</span>
                  <span class="text-foreground/70">{{ t('workspaceView.quickOpenChat') }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Chat Sidebar -->
      <Transition name="chat-slide">
        <div
          v-if="chatOpen"
          class="border-l border-border flex shrink-0 bg-card relative"
          :style="{ width: chatWidth + 'px' }"
        >
          <!-- Resize handle -->
          <div
            class="absolute left-0 top-0 bottom-0 w-1 z-10 cursor-col-resize group"
            @pointerdown="onResizeHandlePointerDown"
          >
            <div
              class="absolute inset-y-0 left-0 w-1 transition-colors"
              :class="isDraggingChat ? 'bg-primary' : 'group-hover:bg-primary/50'"
            />
          </div>
          <div class="flex flex-col flex-1 min-w-0 min-h-0">
            <div class="flex items-center justify-between px-4 py-2 border-b border-border shrink-0">
              <div class="flex items-center gap-1">
                <button
                  class="px-2.5 py-1 text-xs rounded-md transition-colors"
                  :class="chatSidebarTab === 'blackboard' ? 'bg-primary/15 text-primary font-medium' : 'text-muted-foreground hover:text-foreground'"
                  @click="chatSidebarTab = 'blackboard'"
                >
                  {{ t('workspaceView.centralBlackboardChat') }}
                </button>
                <button
                  class="px-2.5 py-1 text-xs rounded-md transition-colors"
                  :class="chatSidebarTab === 'collab-flow' ? 'bg-violet-500/15 text-violet-400 font-medium' : 'text-muted-foreground hover:text-foreground'"
                  @click="chatSidebarTab = 'collab-flow'"
                >
                  {{ t('workspaceView.collabFlow') }}
                </button>
              </div>
              <div class="flex items-center gap-1">
                <button
                  v-if="chatSidebarTab === 'blackboard'"
                  class="p-1 rounded hover:bg-muted transition-colors"
                  :title="focusMode ? t('workspaceView.exitFocus') : t('workspaceView.enterFocus')"
                  @click="toggleFocusMode"
                >
                  <Minimize v-if="focusMode" class="w-4 h-4" />
                  <Focus v-else class="w-4 h-4" />
                </button>
                <button
                  class="p-1 rounded hover:bg-muted transition-colors"
                  @click="chatOpen = false"
                >
                  <X class="w-4 h-4" />
                </button>
              </div>
            </div>
            <ChatPanel
              v-if="chatSidebarTab === 'blackboard'"
              :workspace-id="workspaceId"
              :can-send="store.hasPermission('send_chat')"
              class="flex-1 min-h-0"
            />
            <CollaborationTimeline
              v-else
              ref="collabTimelineRef"
              :workspace-id="workspaceId"
              :agents="agents"
              class="flex-1 min-h-0"
              @replay-flow="onReplayFlow"
            />
          </div>
        </div>
      </Transition>

      <!-- Agent Collaboration Panel -->
      <Transition name="chat-slide">
        <div
          v-if="collabPanelOpen && collabPanelAgent"
          class="border-l border-border flex shrink-0 bg-card"
          style="width: 400px"
        >
          <AgentCollaborationPanel
            ref="collabPanelRef"
            :workspace-id="workspaceId"
            :instance-id="collabPanelAgent.instanceId"
            :agent-name="collabPanelAgent.name"
            class="flex-1 min-h-0"
            @close="collabPanelOpen = false"
          />
        </div>
      </Transition>
    </div>

    <!-- Blackboard Overlay -->
    <BlackboardOverlay
      :open="bbOpen"
      :workspace-id="workspaceId"
      :can-edit="store.hasPermission('edit_blackboard')"
      @close="bbOpen = false"
    />

    <!-- Hex Action Drawer -->
    <HexActionDrawer
      :open="hexDrawerOpen"
      :hex-type="selectedHex?.type || 'empty'"
      :hex-position="selectedHex ? { q: selectedHex.q, r: selectedHex.r } : { q: 0, r: 0 }"
      :agent-info="hexAgentInfo"
      :entity-info="selectedHex?.entityId ? { id: selectedHex.entityId, name: hexEntityName } : undefined"
      :chat-sidebar-open="chatOpen"
      :chat-sidebar-width="chatWidth"
      @close="closeHexDrawer"
      @action="onHexAction"
    />

    <!-- Rename Corridor Dialog -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showRenameDialog" class="fixed inset-0 z-50 flex items-center justify-center">
          <div class="absolute inset-0 bg-black/50" @click="showRenameDialog = false" />
          <div class="relative bg-card border border-border rounded-xl p-6 w-full max-w-sm shadow-lg space-y-4">
            <h3 class="text-sm font-semibold">{{ t('hexAction.renameCorridorTitle') }}</h3>
            <input
              v-model="renameValue"
              type="text"
              class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              :placeholder="t('hexAction.corridorNamePlaceholder')"
              @keydown.enter="handleRenameCorridor"
            />
            <div class="flex justify-end gap-3">
              <button
                class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-muted transition-colors"
                @click="showRenameDialog = false"
              >
                {{ t('common.cancel') }}
              </button>
              <button
                class="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors disabled:opacity-50"
                :disabled="renameSaving"
                @click="handleRenameCorridor"
              >
                {{ renameSaving ? t('common.saving') : t('common.save') }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Rename Human Hex Dialog -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showRenameHumanDialog" class="fixed inset-0 z-50 flex items-center justify-center">
          <div class="absolute inset-0 bg-black/50" @click="showRenameHumanDialog = false" />
          <div class="relative bg-card border border-border rounded-xl p-6 w-full max-w-sm shadow-lg space-y-4">
            <h3 class="text-sm font-semibold">{{ t('hexAction.renameHumanTitle') }}</h3>
            <input
              v-model="renameHumanValue"
              type="text"
              class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              :placeholder="t('hexAction.humanNamePlaceholder')"
              @keydown.enter="handleRenameHuman"
            />
            <div class="flex justify-end gap-3">
              <button
                class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-muted transition-colors"
                @click="showRenameHumanDialog = false"
              >
                {{ t('common.cancel') }}
              </button>
              <button
                class="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors disabled:opacity-50"
                :disabled="renameHumanSaving"
                @click="handleRenameHuman"
              >
                {{ renameHumanSaving ? t('common.saving') : t('common.save') }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Rename Agent Dialog -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showRenameAgentDialog" class="fixed inset-0 z-50 flex items-center justify-center">
          <div class="absolute inset-0 bg-black/50" @click="showRenameAgentDialog = false" />
          <div class="relative bg-card border border-border rounded-xl p-6 w-full max-w-sm shadow-lg space-y-4">
            <h3 class="text-sm font-semibold">{{ t('hexAction.renameAgentTitle') }}</h3>
            <div class="space-y-3">
              <div>
                <label class="block text-xs text-muted-foreground mb-1">{{ t('hexAction.agentDisplayNameLabel') }}</label>
                <input
                  v-model="renameAgentDisplayName"
                  type="text"
                  class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                  :placeholder="renameAgentOriginalName"
                  @keydown.enter="handleRenameAgent"
                />
              </div>
              <div>
                <label class="block text-xs text-muted-foreground mb-1">{{ t('hexAction.agentLabelFieldLabel') }}</label>
                <input
                  v-model="renameAgentLabel"
                  type="text"
                  class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                  :placeholder="t('hexAction.agentLabelPlaceholder')"
                  @keydown.enter="handleRenameAgent"
                />
              </div>
            </div>
            <div class="flex justify-end gap-3">
              <button
                class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-muted transition-colors"
                @click="showRenameAgentDialog = false"
              >
                {{ t('common.cancel') }}
              </button>
              <button
                class="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors disabled:opacity-50"
                :disabled="renameAgentSaving"
                @click="handleRenameAgent"
              >
                {{ renameAgentSaving ? t('common.saving') : t('common.save') }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Member Picker Dialog -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showMemberPicker" class="fixed inset-0 z-50 flex items-center justify-center">
          <div class="absolute inset-0 bg-black/50" @click="showMemberPicker = false" />
          <div class="relative bg-card border border-border rounded-xl p-6 w-full max-w-sm shadow-lg space-y-4">
            <h3 class="text-sm font-semibold">{{ t('hexAction.selectMember') }}</h3>
            <div v-if="availableMembers.length === 0" class="text-center py-4 space-y-3">
              <p class="text-sm text-muted-foreground">{{ t('hexAction.noAvailableMembers') }}</p>
              <button
                class="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors"
                @click="showMemberPicker = false; showSettingsDialog = true"
              >
                {{ t('hexAction.goToSettings') }}
              </button>
            </div>
            <div v-else class="flex flex-col gap-1 max-h-60 overflow-y-auto">
              <button
                v-for="member in availableMembers"
                :key="member.user_id"
                class="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-muted transition-colors text-left"
                @click="pickMember(member.user_id, member.user_name)"
              >
                <div
                  v-if="member.user_avatar_url"
                  class="w-8 h-8 rounded-full bg-cover bg-center shrink-0"
                  :style="{ backgroundImage: `url(${member.user_avatar_url})` }"
                />
                <div v-else class="w-8 h-8 rounded-full bg-amber-500/20 flex items-center justify-center shrink-0">
                  <User class="w-4 h-4 text-amber-500" />
                </div>
                <div class="min-w-0">
                  <div class="text-sm font-medium truncate">{{ member.user_name }}</div>
                  <div v-if="member.user_email" class="text-xs text-muted-foreground truncate">{{ member.user_email }}</div>
                </div>
              </button>
            </div>
            <div class="flex justify-end pt-2">
              <button
                class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-muted transition-colors"
                @click="showMemberPicker = false"
              >
                {{ t('common.cancel') }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Color Picker Dialog -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showColorPicker" class="fixed inset-0 z-50 flex items-center justify-center">
          <div class="absolute inset-0 bg-black/50" @click="showColorPicker = false" />
          <div class="relative bg-card border border-border rounded-xl p-6 w-full max-w-xs shadow-lg space-y-4">
            <h3 class="text-sm font-semibold">{{ t('hexAction.selectColor') }}</h3>
            <div class="grid grid-cols-4 gap-3 justify-items-center">
              <button
                v-for="color in COLOR_PRESETS"
                :key="color"
                class="w-10 h-10 rounded-full border-2 border-transparent hover:border-foreground/40 transition-colors hover:scale-110"
                :style="{ backgroundColor: color }"
                @click="pickColor(color)"
              />
            </div>
            <div class="flex justify-end pt-2">
              <button
                class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-muted transition-colors"
                @click="showColorPicker = false"
              >
                {{ t('common.cancel') }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Agent Color Picker Dialog -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showAgentColorPicker" class="fixed inset-0 z-50 flex items-center justify-center">
          <div class="absolute inset-0 bg-black/50" @click="showAgentColorPicker = false" />
          <div class="relative bg-card border border-border rounded-xl p-6 w-full max-w-xs shadow-lg space-y-4">
            <h3 class="text-sm font-semibold">{{ t('hexAction.changeAgentColor') }}</h3>
            <div class="grid grid-cols-4 gap-3 justify-items-center">
              <button
                v-for="color in COLOR_PRESETS"
                :key="color"
                class="w-10 h-10 rounded-full border-2 border-transparent hover:border-foreground/40 transition-colors hover:scale-110"
                :style="{ backgroundColor: color }"
                @click="pickAgentColor(color)"
              />
            </div>
            <div class="flex justify-end pt-2">
              <button
                class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-muted transition-colors"
                @click="showAgentColorPicker = false"
              >
                {{ t('common.cancel') }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Agent Detail Dialog -->
    <AgentDetailDialog
      v-model:visible="agentDetailVisible"
      :instance-id="agentDetailId"
      @navigate="openAgentDetailPage"
      @deleted="store.fetchWorkspace(workspaceId)"
    />

    <!-- Focus Mode Dialog -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="focusMode" class="fixed inset-0 z-50 flex flex-col bg-background/95 backdrop-blur-sm">
          <div class="flex items-center justify-between px-5 py-2.5 border-b border-border shrink-0">
            <div class="flex items-center gap-2">
              <MessageSquare class="w-4 h-4 text-primary" />
              <span class="text-sm font-semibold">{{ ws?.name }}</span>
              <span class="text-xs text-muted-foreground">{{ t('workspaceView.focusMode') }}</span>
            </div>
            <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" @click="focusMode = false">
              <X class="w-4 h-4" />
            </button>
          </div>
          <div class="flex-1 flex min-h-0">
            <div class="flex-1 flex flex-col min-h-0 min-w-0 border-r border-border">
              <BlackboardOverlay :open="true" :workspace-id="workspaceId" :can-edit="store.hasPermission('edit_blackboard')" embedded @close="focusMode = false" />
            </div>
            <div class="flex-1 flex flex-col min-h-0 min-w-0">
              <ChatPanel :workspace-id="workspaceId" :can-send="store.hasPermission('send_chat')" class="flex-1 min-h-0" />
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <AddAgentDialog
      v-model:visible="addAgentDialogVisible"
      :workspace-id="workspaceId"
      :target-hex-q="addAgentHexQ"
      :target-hex-r="addAgentHexR"
      :cluster-id="store.currentWorkspace?.cluster_id"
      @added="onAgentAdded"
    />

    <WorkspaceSettings
      v-model:open="showSettingsDialog"
      :workspace-id="workspaceId"
      @deleted="router.push('/')"
    />
  </div>
</template>

<style scoped>
.chat-slide-enter-active,
.chat-slide-leave-active {
  transition: width 0.25s ease, opacity 0.25s ease;
  overflow: hidden;
}
.chat-slide-enter-from,
.chat-slide-leave-to {
  width: 0px !important;
  opacity: 0;
}
.drag-no-select {
  user-select: none;
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
.slide-down-enter-active,
.slide-down-leave-active {
  transition: transform 0.2s ease, opacity 0.2s ease;
}
.slide-down-enter-from,
.slide-down-leave-to {
  transform: translateY(-100%);
  opacity: 0;
}
</style>
