<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Settings, Maximize2, Minimize2, ZoomIn, ZoomOut, RotateCcw } from 'lucide-vue-next'
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
const chatAgentId = ref('')
const chatAgentName = ref('')
const bbOpen = ref(false)
const isFullscreen = ref(false)

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

  store.connectSSE(workspaceId.value, (event, data) => {
    if (event === 'context:published') {
      store.fetchContext(workspaceId.value)
    }
  })
})

onUnmounted(() => {
  store.disconnectSSE()
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
  const agent = agents.value.find((a) => a.instance_id === id)
  if (agent) {
    chatAgentId.value = agent.instance_id
    chatAgentName.value = agent.display_name || agent.name
    chatOpen.value = true
  }
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
      </div>

      <div class="flex items-center gap-2">
        <div class="flex items-center gap-0.5 mr-1">
          <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" title="放大" @click="handleZoomIn">
            <ZoomIn class="w-4 h-4" />
          </button>
          <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" title="缩小" @click="handleZoomOut">
            <ZoomOut class="w-4 h-4" />
          </button>
          <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" title="重置视角" @click="handleResetView">
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
          @agent-click="onAgentClick"
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
          @agent-click="onAgentClick"
          @blackboard-click="onBlackboardClick"
          @add-agent-click="onAddAgentClick"
        />
      </div>
    </div>

    <!-- Chat Drawer -->
    <ChatDrawer
      :open="chatOpen"
      :workspace-id="workspaceId"
      :agent-id="chatAgentId"
      :agent-name="chatAgentName"
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
