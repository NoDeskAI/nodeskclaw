<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Settings, Maximize2, Minimize2, ZoomIn, ZoomOut, RotateCcw, MessageSquare, Plus, Keyboard, ChevronDown } from 'lucide-vue-next'
import { useWorkspaceStore } from '@/stores/workspace'
import { useViewTransition } from '@/composables/useViewTransition'
import Workspace3D from '@/components/hex3d/Workspace3D.vue'
import Workspace2D from '@/components/hex2d/Workspace2D.vue'
import ModeToggle from '@/components/shared/ModeToggle.vue'
import ChatDrawer from '@/components/chat/ChatDrawer.vue'
import BlackboardOverlay from '@/components/blackboard/BlackboardOverlay.vue'

const route = useRoute()
const router = useRouter()
const store = useWorkspaceStore()

const workspaceId = computed(() => route.params.id as string)
const ws = computed(() => store.currentWorkspace)
const agents = computed(() => ws.value?.agents || [])

const { activeMode, isTransitioning, transitionTo2D, transitionTo3D } = useViewTransition()

const chatOpen = ref(false)
const bbOpen = ref(false)
const isFullscreen = ref(false)
const selectedAgentId = ref<string | null>(null)
const showShortcutHints = ref(localStorage.getItem('workspace-shortcut-hints') !== 'hidden')

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

function onAgentClick(id: string) {
  selectedAgentId.value = selectedAgentId.value === id ? null : id
}

function onAgentDblClick(_id: string) {
  chatOpen.value = true
}

function onBlackboardClick() {
  bbOpen.value = true
}

function onAddAgentClick() {
  router.push(`/workspace/${workspaceId.value}/add-agent`)
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
    e.preventDefault()
    return
  }

  const delta = HEX_DELTAS[e.key]
  if (delta) {
    e.preventDefault()
    if (selectedAgentId.value) {
      moveSelectedAgent(delta[0], delta[1])
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
          @click="onAddAgentClick"
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
          class="p-1.5 rounded-lg hover:bg-muted transition-colors"
          :class="{ 'bg-primary/10 text-primary': chatOpen }"
          title="Group Chat"
          @click="chatOpen = !chatOpen"
        >
          <MessageSquare class="w-4 h-4" />
        </button>
        <button
          class="p-1.5 rounded-lg hover:bg-muted transition-colors"
          @click="router.push(`/workspace/${workspaceId}/settings`)"
        >
          <Settings class="w-4 h-4" />
        </button>
      </div>
    </div>

    <!-- 3D / 2D Scene -->
    <div class="flex-1 relative min-h-0">
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
          @agent-click="onAgentClick"
          @agent-dblclick="onAgentDblClick"
          @blackboard-click="onBlackboardClick"
          @add-agent-click="onAddAgentClick"
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
          @agent-click="onAgentClick"
          @agent-dblclick="onAgentDblClick"
          @blackboard-click="onBlackboardClick"
          @add-agent-click="onAddAgentClick"
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
                <span class="text-foreground/70">选中 Agent</span>
              </div>
              <div class="flex justify-between gap-4">
                <span>双击</span>
                <span class="text-foreground/70">打开对话</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Chat Drawer -->
    <ChatDrawer
      :open="chatOpen"
      :workspace-id="workspaceId"
      :workspace-name="ws?.name || 'Workspace'"
      @close="chatOpen = false"
    />

    <!-- Blackboard Overlay -->
    <BlackboardOverlay
      :open="bbOpen"
      :workspace-id="workspaceId"
      @close="bbOpen = false"
    />
  </div>
</template>
