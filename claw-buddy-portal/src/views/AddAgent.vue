<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Plus, Loader2, Bot, Search, Rocket, RefreshCw, Check } from 'lucide-vue-next'
import { useWorkspaceStore } from '@/stores/workspace'
import { useToast } from '@/composables/useToast'
import api from '@/services/api'

const route = useRoute()
const router = useRouter()
const store = useWorkspaceStore()
const toast = useToast()

const workspaceId = computed(() => route.params.id as string)
const targetHexQ = computed(() => route.query.hex_q != null ? Number(route.query.hex_q) : undefined)
const targetHexR = computed(() => route.query.hex_r != null ? Number(route.query.hex_r) : undefined)

interface InstanceItem {
  id: string
  name: string
  slug?: string
  status: string
}

const instances = ref<InstanceItem[]>([])
const loading = ref(false)
const adding = ref<string | null>(null)
const addingStep = ref(0)
const addingDone = ref<string | null>(null)
let stepTimer: ReturnType<typeof setInterval> | null = null
const search = ref('')

const ADDING_STEPS = ['配置中...', '部署插件...', '重启实例...', '连接中...']

const alreadyInWorkspace = computed(() =>
  new Set(store.currentWorkspace?.agents?.map((a) => a.instance_id) || []),
)

const filtered = computed(() =>
  instances.value.filter(
    (i) => !search.value || i.name.toLowerCase().includes(search.value.toLowerCase()),
  ),
)

const runningInstances = computed(() =>
  filtered.value.filter((i) => i.status === 'running' && !alreadyInWorkspace.value.has(i.id)),
)
const addedInstances = computed(() =>
  filtered.value.filter((i) => alreadyInWorkspace.value.has(i.id)),
)
const unavailableInstances = computed(() =>
  filtered.value.filter((i) => i.status !== 'running' && !alreadyInWorkspace.value.has(i.id)),
)

async function fetchInstances() {
  loading.value = true
  try {
    const res = await api.get('/instances')
    instances.value = (res.data.data || []).map((i: any) => ({
      id: i.id,
      name: i.name,
      slug: i.slug,
      status: i.status,
    }))
  } catch (e) {
    console.error('fetch instances error:', e)
  } finally {
    loading.value = false
  }
}

onMounted(fetchInstances)

async function addToWorkspace(instanceId: string) {
  adding.value = instanceId
  addingStep.value = 0
  stepTimer = setInterval(() => {
    if (addingStep.value < ADDING_STEPS.length - 1) addingStep.value++
  }, 4000)
  try {
    await store.addAgent(workspaceId.value, instanceId, undefined, targetHexQ.value, targetHexR.value)
    if (stepTimer) { clearInterval(stepTimer); stepTimer = null }
    adding.value = null
    addingDone.value = instanceId
    setTimeout(() => { addingDone.value = null }, 1500)
    await fetchInstances()
    toast.success('Agent 已添加到工作区', {
      action: {
        label: '前往查看',
        onClick: () => router.push({
          path: `/workspace/${workspaceId.value}`,
          query: { focus_agent: instanceId },
        }),
      },
    })
  } catch (e: any) {
    if (stepTimer) { clearInterval(stepTimer); stepTimer = null }
    alert(e?.response?.data?.detail || '添加失败')
    adding.value = null
  }
}

function goBack() {
  router.push(`/workspace/${workspaceId.value}`)
}
</script>

<template>
  <div class="max-w-lg mx-auto px-6 py-8">
    <div class="flex items-center gap-3 mb-6">
      <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" @click="goBack">
        <ArrowLeft class="w-5 h-5" />
      </button>
      <h1 class="text-xl font-bold">添加 Agent</h1>
    </div>

    <p class="text-sm text-muted-foreground mb-4">
      从已有实例中选择一个 Agent 添加到工作区，或创建新实例
    </p>

    <!-- Create new instance -->
    <button
      class="w-full flex items-center gap-3 px-4 py-3 mb-4 rounded-lg border border-dashed border-primary/40 bg-primary/5 hover:bg-primary/10 transition-colors"
      @click="router.push(`/instances/create?workspace=${workspaceId}`)"
    >
      <Rocket class="w-5 h-5 text-primary" />
      <div class="text-left">
        <p class="text-sm font-medium">创建新实例</p>
        <p class="text-xs text-muted-foreground">部署一个全新的 OpenClaw 实例</p>
      </div>
    </button>

    <!-- Search + Refresh -->
    <div class="flex items-center gap-2 mb-4">
      <div class="relative flex-1">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          v-model="search"
          class="w-full pl-9 pr-3 py-2 rounded-lg bg-muted border border-border text-sm outline-none focus:ring-1 focus:ring-primary/50"
          placeholder="搜索实例..."
        />
      </div>
      <button
        class="p-2 rounded-lg border border-border hover:bg-muted transition-colors disabled:opacity-50"
        :disabled="loading"
        title="刷新列表"
        @click="fetchInstances"
      >
        <RefreshCw class="w-4 h-4" :class="loading ? 'animate-spin' : ''" />
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex justify-center py-10">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <!-- Empty -->
    <div v-else-if="filtered.length === 0" class="text-center py-10 text-muted-foreground text-sm">
      没有可用的实例
    </div>

    <template v-else>
      <!-- Running instances (can be added) -->
      <div v-if="runningInstances.length > 0" class="space-y-2">
        <div
          v-for="inst in runningInstances"
          :key="inst.id"
          class="flex items-center justify-between px-4 py-3 rounded-lg bg-card border border-border hover:border-primary/20 transition-colors"
        >
          <div class="flex items-center gap-3">
            <Bot class="w-5 h-5 text-primary" />
            <div>
              <div class="flex items-center gap-2">
                <p class="text-sm font-medium">{{ inst.name }}</p>
                <span v-if="inst.slug" class="px-1.5 py-0.5 rounded bg-muted text-[10px] font-mono text-muted-foreground leading-none">{{ inst.slug }}</span>
              </div>
              <p class="text-xs text-muted-foreground">{{ inst.status }}</p>
            </div>
          </div>
          <!-- Adding progress -->
          <div v-if="adding === inst.id" class="flex items-center gap-2 min-w-[140px]">
            <div class="flex-1">
              <div class="flex items-center gap-1.5 mb-1">
                <Loader2 class="w-3 h-3 animate-spin text-primary" />
                <span class="text-xs text-muted-foreground">{{ ADDING_STEPS[addingStep] }}</span>
              </div>
              <div class="h-1 rounded-full bg-muted overflow-hidden">
                <div
                  class="h-full rounded-full bg-primary transition-all duration-700 ease-out"
                  :style="{ width: `${((addingStep + 1) / ADDING_STEPS.length) * 100}%` }"
                />
              </div>
            </div>
          </div>
          <span
            v-else-if="addingDone === inst.id"
            class="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-green-500/10 text-green-600 text-xs font-medium"
          >
            <Check class="w-3 h-3" />
            已添加
          </span>
          <button
            v-else
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 disabled:opacity-50"
            :disabled="!!adding"
            @click="addToWorkspace(inst.id)"
          >
            <Plus class="w-3 h-3" />
            添加
          </button>
        </div>
      </div>

      <!-- Already in this workspace -->
      <div v-if="addedInstances.length > 0" class="mt-6">
        <p class="text-xs text-muted-foreground mb-2">已在当前工作区</p>
        <div class="space-y-2">
          <div
            v-for="inst in addedInstances"
            :key="inst.id"
            class="flex items-center justify-between px-4 py-3 rounded-lg bg-card border border-border opacity-60"
          >
            <div class="flex items-center gap-3">
              <Bot class="w-5 h-5 text-muted-foreground" />
              <div>
                <div class="flex items-center gap-2">
                  <p class="text-sm font-medium text-muted-foreground">{{ inst.name }}</p>
                  <span v-if="inst.slug" class="px-1.5 py-0.5 rounded bg-muted text-[10px] font-mono text-muted-foreground leading-none">{{ inst.slug }}</span>
                </div>
                <p class="text-xs text-muted-foreground">{{ inst.status }}</p>
              </div>
            </div>
            <span class="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-muted text-muted-foreground text-xs">
              <Check class="w-3 h-3" />
              已添加
            </span>
          </div>
        </div>
      </div>

      <!-- Unavailable instances (not running) -->
      <div v-if="unavailableInstances.length > 0" class="mt-6">
        <p class="text-xs text-muted-foreground mb-2">以下实例尚未就绪，无法添加到工作区</p>
        <div class="space-y-2 opacity-50">
          <div
            v-for="inst in unavailableInstances"
            :key="inst.id"
            class="flex items-center justify-between px-4 py-3 rounded-lg bg-card border border-border cursor-not-allowed"
          >
            <div class="flex items-center gap-3">
              <Bot class="w-5 h-5 text-muted-foreground" />
              <div>
                <div class="flex items-center gap-2">
                  <p class="text-sm font-medium text-muted-foreground">{{ inst.name }}</p>
                  <span v-if="inst.slug" class="px-1.5 py-0.5 rounded bg-muted text-[10px] font-mono text-muted-foreground leading-none">{{ inst.slug }}</span>
                </div>
                <p class="text-xs text-muted-foreground">{{ inst.status }}</p>
              </div>
            </div>
            <span class="px-3 py-1.5 rounded-lg bg-muted text-muted-foreground text-xs">
              不可用
            </span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
