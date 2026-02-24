<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Settings, Maximize2, Minimize2, ZoomIn, ZoomOut, RotateCcw, MessageSquare, Plus, Keyboard, ChevronDown, X } from 'lucide-vue-next'
import { useWorkspaceStore } from '@/stores/workspace'
import { useViewTransition } from '@/composables/useViewTransition'
import Workspace3D from '@/components/hex3d/Workspace3D.vue'
import Workspace2D from '@/components/hex2d/Workspace2D.vue'
import ModeToggle from '@/components/shared/ModeToggle.vue'
import ChatPanel from '@/components/chat/ChatPanel.vue'
import BlackboardOverlay from '@/components/blackboard/BlackboardOverlay.vue'
import HexActionDrawer from '@/components/workspace/HexActionDrawer.vue'
import { axialToWorld } from '@/composables/useHexLayout'

const route = useRoute()
const router = useRouter()
const store = useWorkspaceStore()

const workspaceId = computed(() => route.params.id as string)
const ws = computed(() => store.currentWorkspace)
const agents = computed(() => ws.value?.agents || [])

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
  type: 'empty' | 'agent' | 'blackboard'
  agentId?: string
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
  await store.fetchWorkspace(workspaceId.value)
  await store.fetchBlackboard(workspaceId.value)

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

function toggleMode() {
  if (isTransitioning.value) return
  if (activeMode.value === '3d') {
    transitionTo2D(threeRef.value, svgRef.value)
  } else {
    transitionTo3D(threeRef.value, svgRef.value)
  }
}

let clickHandled = false

function onHexClick(payload: { q: number, r: number, type: 'empty' | 'agent' | 'blackboard', agentId?: string }) {
  clickHandled = true

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
    case 'edit-blackboard':
      bbOpen.value = true
      hexDrawerOpen.value = false
      break
  }
}

function closeHexDrawer() {
  selectedHex.value = null
  hexDrawerOpen.value = false
  selectedAgentId.value = null
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

const HEX_DELTAS: Record<string, [number, number]> = {
  ArrowRight: [1, 0],
  ArrowLeft: [-1, 0],
  ArrowUp: [0, -1],
  ArrowDown: [0, 1],
}

const ALL_HEX_DIRS: [number, number][] = [
  [1, 0], [-1, 0], [0, -1], [0, 1], [1, -1], [-1, 1],
]

function resolveHexDelta(key: string): [number, number] | null {
  if (activeMode.value === '2d') return HEX_DELTAS[key] || null

  const dirs = workspace3dRef.value?.getCameraXZDirections()
  if (!dirs) return HEX_DELTAS[key] || null

  let sx = 0, sz = 0
  if (key === 'ArrowRight') { sx = dirs.right.x; sz = dirs.right.z }
  else if (key === 'ArrowLeft') { sx = -dirs.right.x; sz = -dirs.right.z }
  else if (key === 'ArrowUp') { sx = dirs.forward.x; sz = dirs.forward.z }
  else if (key === 'ArrowDown') { sx = -dirs.forward.x; sz = -dirs.forward.z }
  else return null

  let bestDot = -Infinity
  let best: [number, number] = [1, 0]
  for (const [dq, dr] of ALL_HEX_DIRS) {
    const w = axialToWorld(dq, dr)
    const dot = sx * w.x + sz * w.y
    if (dot > bestDot) { bestDot = dot; best = [dq, dr] }
  }
  return best
}

async function moveSelectedAgent(dq: number, dr: number) {
  if (!selectedAgentId.value) return
  const agent = agents.value.find((a) => a.instance_id === selectedAgentId.value)
  if (!agent) return

  const targetQ = agent.hex_q + dq
  const targetR = agent.hex_r + dr

  if (targetQ === 0 && targetR === 0) return

  const occupied = agents.value.some(
    (a) => a.instance_id !== selectedAgentId.value && a.hex_q === targetQ && a.hex_r === targetR,
  )
  if (occupied) return

  await store.updateAgent(workspaceId.value, selectedAgentId.value, {
    hex_q: targetQ,
    hex_r: targetR,
  })
}

function panCanvas(key: string) {
  const dx = key === 'ArrowRight' ? 1 : key === 'ArrowLeft' ? -1 : 0
  const dy = key === 'ArrowDown' ? 1 : key === 'ArrowUp' ? -1 : 0
  if (activeMode.value === '3d') {
    workspace3dRef.value?.panBy(dx, dy)
  } else {
    workspace2dRef.value?.panBy(dx, dy)
  }
}

function handleKeydown(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement)?.tagName?.toLowerCase()
  if (tag === 'input' || tag === 'textarea' || (e.target as HTMLElement)?.isContentEditable) return

  if (e.key === 'Escape') {
    selectedAgentId.value = null
    selectedHex.value = null
    hexDrawerOpen.value = false
    e.preventDefault()
    return
  }

  if (HEX_DELTAS[e.key]) {
    e.preventDefault()
    if (selectedAgentId.value) {
      const hexDelta = resolveHexDelta(e.key)
      if (hexDelta) moveSelectedAgent(hexDelta[0], hexDelta[1])
    } else {
      panCanvas(e.key)
    }
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
            {{ ws.icon === 'bot' ? '🤖' : ws.icon }}
          </div>
          <span class="font-semibold text-sm">{{ ws.name }}</span>
        </div>
        <button
          class="flex items-center gap-1 px-2.5 py-1 rounded-lg border border-dashed border-border text-xs text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors"
          @click="router.push(`/workspace/${workspaceId}/add-agent`)"
        >
          <Plus class="w-3.5 h-3.5" />
          添加 Agent
        </button>
      </div>

      <div class="flex items-center gap-2">
        <div class="flex items-center gap-0.5 mr-1">
          <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" title="放大 (+)" @click="handleZoomIn">
            <ZoomIn class="w-4 h-4" />
          </button>
          <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" title="缩小 (-)" @click="handleZoomOut">
            <ZoomOut class="w-4 h-4" />
          </button>
          <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" title="重置视角 (0)" @click="handleResetView">
            <RotateCcw class="w-4 h-4" />
          </button>
        </div>

        <div class="w-px h-5 bg-border" />

        <ModeToggle :mode="activeMode" @toggle="toggleMode" />
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
            :auto-summary="store.blackboard?.auto_summary || ''"
            :manual-notes="store.blackboard?.manual_notes || ''"
            :selected-agent-id="selectedAgentId"
            :selected-hex="selectedHexPos"
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
            :auto-summary="store.blackboard?.auto_summary || ''"
            :manual-notes="store.blackboard?.manual_notes || ''"
            :selected-agent-id="selectedAgentId"
            :selected-hex="selectedHexPos"
            @hex-click="onHexClick"
            @agent-dblclick="onAgentDblClick"
          />
        </div>

        <!-- Shortcut Hints Panel -->
        <div class="absolute right-3 bottom-3 z-10">
          <button
            v-if="!showShortcutHints"
            class="p-2 rounded-lg bg-background/70 backdrop-blur-sm border border-border/50 text-muted-foreground hover:text-foreground transition-colors"
            title="显示快捷键"
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
              <span>快捷键</span>
              <ChevronDown class="w-3 h-3 ml-auto" />
            </button>
            <div class="border-t border-border/50 px-3 py-2 space-y-1 text-muted-foreground">
              <div class="flex justify-between gap-4">
                <span>方向键</span>
                <span class="text-foreground/70">{{ selectedAgentId ? '移动 Agent' : '平移画布' }}</span>
              </div>
              <div class="flex justify-between gap-4">
                <span>+ / -</span>
                <span class="text-foreground/70">缩放</span>
              </div>
              <div class="flex justify-between gap-4">
                <span>0</span>
                <span class="text-foreground/70">重置视角</span>
              </div>
              <div class="flex justify-between gap-4">
                <span>Esc</span>
                <span class="text-foreground/70">取消选中</span>
              </div>
              <div class="border-t border-border/30 pt-1 mt-1">
                <div class="flex justify-between gap-4">
                  <span>单击</span>
                  <span class="text-foreground/70">打开操作面板</span>
                </div>
                <div class="flex justify-between gap-4">
                  <span>双击</span>
                  <span class="text-foreground/70">快速打开对话</span>
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
              <span class="text-xs text-muted-foreground">Group Chat</span>
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
      :chat-sidebar-open="chatOpen"
      @close="closeHexDrawer"
      @action="onHexAction"
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
  width: 0 !important;
  opacity: 0;
}
</style>
