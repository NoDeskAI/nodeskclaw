<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  CheckCircle, XCircle, Loader2, Circle, Rocket,
  ExternalLink, ArrowLeft, ChevronDown, ChevronRight, Square,
} from 'lucide-vue-next'
import { fetchEventSource } from '@microsoft/fetch-event-source'

const route = useRoute()
const router = useRouter()

const deployId = route.params.deployId as string
const instanceName = (route.query.name as string) || ''
const instanceId = (route.query.instanceId as string) || ''

const STEP_NAMES = [
  '预检',
  '创建命名空间',
  '创建 ConfigMap',
  '创建 PVC',
  '创建 Deployment',
  '创建 Service',
  '创建 Ingress（自动路由）',
  '配置网络策略',
  '等待 Deployment 就绪',
]

type StepStatus = 'pending' | 'in_progress' | 'completed' | 'failed'

interface StepItem {
  name: string
  status: StepStatus
  message?: string
  logs: string[]
  expanded: boolean
}

const steps = ref<StepItem[]>(
  STEP_NAMES.map((name) => ({ name, status: 'pending', logs: [], expanded: false })),
)
const finalStatus = ref<'in_progress' | 'success' | 'failed'>('in_progress')
const finalMessage = ref('')
const percent = ref(0)

let abortCtrl: AbortController | null = null
let sseTimeout: ReturnType<typeof setTimeout> | null = null

function toggleLogs(idx: number) {
  steps.value[idx].expanded = !steps.value[idx].expanded
}

function updateSteps(stepIndex: number, status: string, message?: string, logs?: string[]) {
  for (let i = 0; i < stepIndex - 1 && i < steps.value.length; i++) {
    if (steps.value[i].status !== 'completed') {
      steps.value[i].status = 'completed'
      steps.value[i].expanded = false
    }
  }

  if (status === 'success') {
    for (const s of steps.value) {
      s.status = 'completed'
      s.expanded = false
    }
    finalStatus.value = 'success'
    finalMessage.value = message || '部署成功'
  } else if (status === 'failed') {
    if (stepIndex - 1 >= 0 && stepIndex - 1 < steps.value.length) {
      const s = steps.value[stepIndex - 1]
      s.status = 'failed'
      s.message = message
      if (logs?.length) s.logs = logs
      s.expanded = true
    }
    finalStatus.value = 'failed'
    finalMessage.value = message || '部署失败'
  } else {
    if (stepIndex - 1 >= 0 && stepIndex - 1 < steps.value.length) {
      const s = steps.value[stepIndex - 1]
      s.status = 'in_progress'
      if (logs?.length) s.logs = logs
      s.expanded = true
    }
  }
}

function subscribeSSE() {
  const token = localStorage.getItem('portal_token')
  abortCtrl = new AbortController()

  sseTimeout = setTimeout(() => {
    abortCtrl?.abort()
    if (finalStatus.value === 'in_progress') {
      finalStatus.value = 'failed'
      finalMessage.value = '部署超时（6 分钟），请在实例列表查看状态'
    }
  }, 360_000)

  fetchEventSource(`/api/v1/deploy/progress/${deployId}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    signal: abortCtrl.signal,
    openWhenHidden: true,
    onmessage(ev) {
      if (ev.event === 'deploy_progress') {
        const data = JSON.parse(ev.data)
        percent.value = data.percent ?? 0
        updateSteps(data.step, data.status, data.message, data.logs)

        if (data.status === 'success' || data.status === 'failed') {
          if (sseTimeout) clearTimeout(sseTimeout)
          abortCtrl?.abort()
        }
      }
    },
    onerror(err) {
      if (abortCtrl?.signal.aborted) return
      console.warn('SSE 连接异常，将自动重试', err)
    },
  }).catch((e) => {
    if (e instanceof DOMException && e.name === 'AbortError') return
  })
}

onMounted(() => {
  subscribeSSE()
})

onUnmounted(() => {
  if (sseTimeout) clearTimeout(sseTimeout)
  abortCtrl?.abort()
})

const isFinished = computed(() => finalStatus.value !== 'in_progress')

const progressBarClass = computed(() => {
  if (finalStatus.value === 'success') return 'bg-green-500'
  if (finalStatus.value === 'failed') return 'bg-red-500'
  return 'bg-primary'
})

function stepIconColor(status: StepStatus) {
  if (status === 'completed') return 'text-green-500'
  if (status === 'in_progress') return 'text-primary'
  if (status === 'failed') return 'text-red-500'
  return 'text-muted-foreground/40'
}

function stepTextColor(status: StepStatus) {
  if (status === 'completed') return 'text-green-500'
  if (status === 'in_progress') return 'text-foreground'
  if (status === 'failed') return 'text-red-500'
  return 'text-muted-foreground'
}

function lineColor(status: StepStatus) {
  if (status === 'completed') return 'bg-green-500/40'
  if (status === 'in_progress') return 'bg-primary/40'
  if (status === 'failed') return 'bg-red-500/40'
  return 'bg-muted'
}
</script>

<template>
  <div class="max-w-2xl mx-auto px-6 py-8">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div class="flex items-center gap-3">
        <Rocket class="w-5 h-5 text-primary" />
        <div>
          <h1 class="text-xl font-bold">部署实例</h1>
          <p v-if="instanceName" class="text-sm text-muted-foreground">{{ instanceName }}</p>
        </div>
      </div>
    </div>

    <!-- Progress Bar -->
    <div class="w-full h-2 bg-muted rounded-full overflow-hidden mb-8">
      <div
        class="h-full rounded-full transition-all duration-500"
        :class="progressBarClass"
        :style="{ width: `${percent}%` }"
      />
    </div>

    <!-- Steps Timeline -->
    <div class="rounded-xl border border-border bg-card p-5">
      <h2 class="text-sm font-medium mb-4">部署步骤</h2>
      <div class="space-y-0">
        <div
          v-for="(step, idx) in steps"
          :key="idx"
          class="relative"
          :class="idx < steps.length - 1 ? 'pb-4' : ''"
        >
          <!-- 连线 -->
          <div
            v-if="idx < steps.length - 1"
            class="absolute left-[11px] top-[24px] w-[2px] h-[calc(100%-12px)]"
            :class="lineColor(step.status)"
          />
          <!-- 步骤头部 -->
          <div
            class="flex items-start gap-3 select-none"
            :class="step.logs.length ? 'cursor-pointer' : ''"
            @click="step.logs.length ? toggleLogs(idx) : undefined"
          >
            <div class="shrink-0 mt-0.5">
              <CheckCircle v-if="step.status === 'completed'" class="w-6 h-6" :class="stepIconColor(step.status)" />
              <Loader2 v-else-if="step.status === 'in_progress'" class="w-6 h-6 animate-spin" :class="stepIconColor(step.status)" />
              <XCircle v-else-if="step.status === 'failed'" class="w-6 h-6" :class="stepIconColor(step.status)" />
              <Circle v-else class="w-6 h-6" :class="stepIconColor(step.status)" />
            </div>
            <div class="flex-1 min-w-0 flex items-center gap-1.5">
              <span class="text-sm font-medium" :class="stepTextColor(step.status)">
                {{ step.name }}
              </span>
              <component
                :is="step.expanded ? ChevronDown : ChevronRight"
                v-if="step.logs.length > 0"
                class="w-3.5 h-3.5 text-muted-foreground shrink-0"
              />
            </div>
          </div>

          <!-- 日志区域 -->
          <div
            v-if="step.expanded && step.logs.length > 0"
            class="ml-9 mt-1.5 rounded-lg bg-muted/50 border border-border/50 px-3 py-2 space-y-0.5 max-h-40 overflow-y-auto"
          >
            <p
              v-for="(line, li) in step.logs"
              :key="li"
              class="text-xs font-mono break-all"
              :class="step.status === 'failed' ? 'text-red-400' : 'text-muted-foreground'"
            >
              {{ line }}
            </p>
          </div>

          <!-- 失败消息 -->
          <p
            v-if="step.message && step.status === 'failed' && !step.expanded"
            class="ml-9 mt-0.5 text-xs text-red-400 break-all"
          >
            {{ step.message }}
          </p>
        </div>
      </div>
    </div>

    <!-- Result -->
    <div v-if="isFinished" class="mt-6 rounded-xl border border-border bg-card p-6">
      <!-- Success -->
      <div v-if="finalStatus === 'success'" class="text-center space-y-4">
        <CheckCircle class="w-12 h-12 text-green-500 mx-auto" />
        <div>
          <p class="text-lg font-semibold text-green-500">部署成功</p>
          <p class="text-sm text-muted-foreground mt-1">实例 {{ instanceName }} 已就绪</p>
        </div>
        <div class="flex justify-center gap-3">
          <button
            v-if="instanceId"
            class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
            @click="router.push(`/instances/${instanceId}`)"
          >
            <ExternalLink class="w-4 h-4" />
            查看实例
          </button>
          <button
            class="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-border text-sm hover:bg-card transition-colors"
            @click="router.push('/instances')"
          >
            实例列表
          </button>
        </div>
      </div>

      <!-- Failed -->
      <div v-else class="text-center space-y-4">
        <XCircle class="w-12 h-12 text-red-500 mx-auto" />
        <div>
          <p class="text-lg font-semibold text-red-500">部署失败</p>
          <p class="text-sm text-muted-foreground mt-1 max-w-md mx-auto break-all">
            {{ finalMessage }}
          </p>
        </div>
        <div class="flex justify-center gap-3">
          <button
            class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
            @click="router.push('/instances/create')"
          >
            <ArrowLeft class="w-4 h-4" />
            重新创建
          </button>
          <button
            class="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-border text-sm hover:bg-card transition-colors"
            @click="router.push('/instances')"
          >
            实例列表
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
