<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, Settings, Maximize2, Minimize2, ZoomIn, ZoomOut, RotateCcw, MessageSquare, Plus, Keyboard, ChevronDown, X, Bot, ListChecks, AlertTriangle, Wifi, User, Users, MapPin } from 'lucide-vue-next'
import { useWorkspaceStore } from '@/stores/workspace'
import { useViewTransition } from '@/composables/useViewTransition'
import Workspace3D from '@/components/hex3d/Workspace3D.vue'
import Workspace2D from '@/components/hex2d/Workspace2D.vue'
import ModeToggle from '@/components/shared/ModeToggle.vue'
import ChatPanel from '@/components/chat/ChatPanel.vue'
import LocaleSelect from '@/components/shared/LocaleSelect.vue'
import BlackboardOverlay from '@/components/blackboard/BlackboardOverlay.vue'
import HexActionDrawer from '@/components/workspace/HexActionDrawer.vue'
import { useToast } from '@/composables/useToast'
import { axialToWorld } from '@/composables/useHexLayout'
import { getCurrentLocale, setCurrentLocale } from '@/i18n'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useWorkspaceStore()

const locale = ref(getCurrentLocale())
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

const { activeMode, isTransitioning, transitionTo2D, transitionTo3D } = useViewTransition()

const chatOpen = ref(false)
watch(chatOpen, (v) => store.setChatVisible(v))
const bbOpen = ref(false)
const isFullscreen = ref(false)
const selectedAgentId = ref<string | null>(null)
const showShortcutHints = ref(localStorage.getItem('workspace-shortcut-hints') !== 'hidden')

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
}

onMounted(async () => {
  store.resetCurrentState()

  await store.fetchWorkspace(workspaceId.value)
  await store.fetchBlackboard(workspaceId.value)
  await store.fetchTopology(workspaceId.value)
  await store.fetchMembers(workspaceId.value)

  store.connectSSE(workspaceId.value)
  window.addEventListener('keydown', handleKeydown)

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
})

onUnmounted(() => {
  store.disconnectSSE()
  window.removeEventListener('keydown', handleKeydown)
})

watch(workspaceId, async (newId, oldId) => {
  if (newId && newId !== oldId) {
    store.resetCurrentState()
    await store.fetchWorkspace(newId)
    await store.fetchBlackboard(newId)
    await store.fetchTopology(newId)
    store.connectSSE(newId)
  }
})

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
  chatOpen.value = true
}

function onHexAction(action: string) {
  switch (action) {
    case 'add-agent': {
      const q = selectedHex.value?.q
      const r = selectedHex.value?.r
      const query: Record<string, string> = {}
      if (q !== undefined && r !== undefined) { query.hex_q = String(q); query.hex_r = String(r) }
      router.push({ path: `/workspace/${workspaceId.value}/add-agent`, query })
      break
    }
    case 'open-chat':
      chatOpen.value = true
      hexDrawerOpen.value = false
      break
    case 'view-detail':
      if (selectedHex.value?.agentId) {
        router.push(`/instances/${selectedHex.value.agentId}`)
      }
      hexDrawerOpen.value = false
      break
    case 'remove-agent':
      if (selectedHex.value?.agentId) {
        store.removeAgent(workspaceId.value, selectedHex.value.agentId)
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
    case 'remove-corridor':
      if (selectedHex.value?.entityId) {
        store.deleteCorridorHex(workspaceId.value, selectedHex.value.entityId)
        selectedHex.value = null
        hexDrawerOpen.value = false
      }
      break
    case 'view-channel':
      openChannelConfig()
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
        store.deleteHumanHex(workspaceId.value, selectedHex.value.entityId)
        selectedHex.value = null
        hexDrawerOpen.value = false
      }
      break
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

const showMemberPicker = ref(false)
const pendingHumanHex = ref<{ q: number; r: number } | null>(null)

const availableMembers = computed(() => store.members)

async function pickMember(userId: string) {
  const hex = pendingHumanHex.value
  if (!hex) return
  showMemberPicker.value = false
  await store.createHumanHex(workspaceId.value, userId, hex.q, hex.r)
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

const showChannelDialog = ref(false)
const channelHexId = ref('')
const channelMode = ref<'webhook' | 'websocket'>('webhook')
const channelChatId = ref('')
const channelAppId = ref('')
const channelAppSecret = ref('')
const channelSaving = ref(false)

function openChannelConfig() {
  channelHexId.value = selectedHex.value?.entityId || ''
  const node = store.topologyNodes.find((n: any) => n.entity_id === channelHexId.value)
  const cfg = node?.extra?.channel_config as Record<string, string> | undefined
  if (cfg) {
    channelMode.value = (cfg.mode === 'websocket' ? 'websocket' : 'webhook')
    channelChatId.value = cfg.chat_id || ''
    channelAppId.value = cfg.app_id || ''
    channelAppSecret.value = cfg.app_secret || ''
  } else {
    channelMode.value = 'webhook'
    channelChatId.value = ''
    channelAppId.value = ''
    channelAppSecret.value = ''
  }
  showChannelDialog.value = true
}

async function saveChannelConfig() {
  const hexId = channelHexId.value
  if (!hexId) return
  channelSaving.value = true
  try {
    const config: Record<string, string> = {
      chat_id: channelChatId.value,
      mode: channelMode.value,
    }
    if (channelMode.value === 'websocket') {
      config.app_id = channelAppId.value
      config.app_secret = channelAppSecret.value
    }
    await store.updateHumanHexChannel(workspaceId.value, hexId, 'feishu', config)
    showChannelDialog.value = false
  } finally {
    channelSaving.value = false
  }
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

type MovingHexSource = {
  type: 'agent' | 'corridor' | 'human'
  id: string
  q: number
  r: number
}
const isMovingHex = ref(false)
const movingHexSource = ref<MovingHexSource | null>(null)

function enterMoveMode() {
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

function handleKeydown(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement)?.tagName?.toLowerCase()
  if (tag === 'input' || tag === 'textarea' || (e.target as HTMLElement)?.isContentEditable) return

  if (e.key === 'Escape') {
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
  <div class="flex flex-col h-screen overflow-hidden bg-background">
    <!-- Toolbar -->
    <div class="flex items-center justify-between px-4 py-2 border-b border-border bg-background/80 backdrop-blur-sm shrink-0 z-10">
      <div class="flex items-center gap-3">
        <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" @click="goBack">
          <ArrowLeft class="w-4 h-4" />
        </button>
        <div
          v-if="ws"
          class="flex items-center gap-2"
        >
          <div
            class="w-6 h-6 rounded flex items-center justify-center text-xs"
            :style="{ backgroundColor: ws.color + '22', color: ws.color }"
          >
            <Bot v-if="ws.icon === 'bot'" class="w-3.5 h-3.5" />
            <template v-else>{{ ws.icon }}</template>
          </div>
          <span class="font-semibold text-sm">{{ ws.name }}</span>
        </div>
        <button
          class="flex items-center gap-1 px-2.5 py-1 rounded-lg border border-dashed border-border text-xs text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors"
          @click="router.push(`/workspace/${workspaceId}/add-agent`)"
        >
          <Plus class="w-3.5 h-3.5" />
          {{ t('workspaceView.addAgent') }}
        </button>

        <div class="w-px h-5 bg-border" />

        <div class="flex items-center gap-3 text-xs text-muted-foreground">
          <span class="flex items-center gap-1">
            <ListChecks class="w-3.5 h-3.5" />
            {{ t('workspaceView.bbTasks') }} {{ bbTaskCount }}
          </span>
          <span class="flex items-center gap-1" :class="bbBlockedCount > 0 ? 'text-amber-500' : ''">
            <AlertTriangle class="w-3.5 h-3.5" />
            {{ t('workspaceView.bbBlocked') }} {{ bbBlockedCount }}
          </span>
          <span class="flex items-center gap-1" :class="bbOnlineCount > 0 ? 'text-green-500' : ''">
            <Wifi class="w-3.5 h-3.5" />
            {{ t('workspaceView.bbOnline') }} {{ bbOnlineCount }}
          </span>
          <span class="flex items-center gap-1">
            <Users class="w-3.5 h-3.5" />
            {{ t('workspaceView.bbHumans') }} {{ humanCount }}
          </span>
          <span class="flex items-center gap-1">
            <MapPin class="w-3.5 h-3.5" />
            {{ t('workspaceView.bbHumanSeats') }} {{ humanSeatCount }}
          </span>
        </div>
      </div>

      <div class="flex items-center gap-2">
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
          class="p-1.5 rounded-lg hover:bg-muted transition-colors"
          @click="router.push(`/workspace/${workspaceId}/settings`)"
        >
          <Settings class="w-4 h-4" />
        </button>
      </div>
    </div>

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
            :is-moving-hex="isMovingHex"
            :moving-hex-source="movingHexSource"
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
            :topology-nodes="store.topologyNodes"
            :is-moving-hex="isMovingHex"
            :moving-hex-source="movingHexSource"
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
          class="w-[400px] border-l border-border flex flex-col shrink-0 bg-card"
        >
          <div class="flex items-center justify-between px-4 py-2 border-b border-border shrink-0">
            <div class="flex items-center gap-2">
              <MessageSquare class="w-4 h-4 text-primary" />
              <span class="text-sm font-medium">{{ ws?.name || 'Workspace' }}</span>
              <span class="text-xs text-muted-foreground">{{ t('workspaceView.groupChat') }}</span>
            </div>
            <button
              class="p-1 rounded hover:bg-muted transition-colors"
              @click="chatOpen = false"
            >
              <X class="w-4 h-4" />
            </button>
          </div>
          <ChatPanel
            :workspace-id="workspaceId"
            class="flex-1 min-h-0"
          />
        </div>
      </Transition>
    </div>

    <!-- Blackboard Overlay -->
    <BlackboardOverlay
      :open="bbOpen"
      :workspace-id="workspaceId"
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
                @click="showMemberPicker = false; router.push(`/workspace/${workspaceId}/settings`)"
              >
                {{ t('hexAction.goToSettings') }}
              </button>
            </div>
            <div v-else class="flex flex-col gap-1 max-h-60 overflow-y-auto">
              <button
                v-for="member in availableMembers"
                :key="member.user_id"
                class="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-muted transition-colors text-left"
                @click="pickMember(member.user_id)"
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

    <!-- Channel Config Dialog -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showChannelDialog" class="fixed inset-0 z-50 flex items-center justify-center">
          <div class="absolute inset-0 bg-black/50" @click="showChannelDialog = false" />
          <div class="relative bg-card border border-border rounded-xl p-6 w-full max-w-md shadow-lg space-y-4">
            <h3 class="text-sm font-semibold">{{ t('channel.configTitle') }}</h3>

            <div class="space-y-3">
              <label class="block text-xs text-muted-foreground">{{ t('channel.mode') }}</label>
              <div class="flex gap-2">
                <button
                  class="flex-1 px-3 py-2 rounded-lg border text-sm transition-colors"
                  :class="channelMode === 'webhook' ? 'border-primary bg-primary/10 text-primary' : 'border-border text-muted-foreground hover:bg-muted'"
                  @click="channelMode = 'webhook'"
                >
                  Webhook
                </button>
                <button
                  class="flex-1 px-3 py-2 rounded-lg border text-sm transition-colors"
                  :class="channelMode === 'websocket' ? 'border-primary bg-primary/10 text-primary' : 'border-border text-muted-foreground hover:bg-muted'"
                  @click="channelMode = 'websocket'"
                >
                  WebSocket
                </button>
              </div>

              <div>
                <label class="block text-xs text-muted-foreground mb-1">{{ t('channel.chatId') }}</label>
                <input
                  v-model="channelChatId"
                  type="text"
                  class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                  placeholder="oc_xxxxx"
                />
              </div>

              <template v-if="channelMode === 'websocket'">
                <div>
                  <label class="block text-xs text-muted-foreground mb-1">{{ t('channel.appId') }}</label>
                  <input
                    v-model="channelAppId"
                    type="text"
                    class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                    placeholder="cli_xxxxx"
                  />
                </div>
                <div>
                  <label class="block text-xs text-muted-foreground mb-1">{{ t('channel.appSecret') }}</label>
                  <input
                    v-model="channelAppSecret"
                    type="password"
                    class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
              </template>

              <p class="text-xs text-muted-foreground">
                {{ channelMode === 'webhook' ? t('channel.webhookHint') : t('channel.websocketHint') }}
              </p>
            </div>

            <div class="flex justify-end gap-3 pt-2">
              <button
                class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-muted transition-colors"
                @click="showChannelDialog = false"
              >
                {{ t('common.cancel') }}
              </button>
              <button
                class="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors disabled:opacity-50"
                :disabled="channelSaving || !channelChatId"
                @click="saveChannelConfig"
              >
                {{ channelSaving ? t('common.saving') : t('common.save') }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
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
  width: 0 !important;
  opacity: 0;
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
