<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import {
  CheckCircle, XCircle, Loader2, Circle, Rocket, ExternalLink, ArrowLeft,
  ChevronDown, ChevronRight, Square,
} from 'lucide-vue-next'
import { fetchEventSource } from '@microsoft/fetch-event-source'
import api, { API_BASE } from '@/services/api'
import { toast } from 'vue-sonner'

const route = useRoute()
const router = useRouter()

const deployId = route.params.deployId as string
const instanceName = (route.query.name as string) || ''

// 后端 DEPLOY_STEPS 的 9 个步骤名称（硬编码，与后端保持一致）
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
  logs: string[]       // 该步骤的日志行
  expanded: boolean    // 是否展开日志
}

const steps = ref<StepItem[]>(
  STEP_NAMES.map((name) => ({ name, status: 'pending', logs: [], expanded: false })),
)
const finalStatus = ref<'in_progress' | 'success' | 'failed'>('in_progress')
const finalMessage = ref('')
const percent = ref(0)

// SSE 控制
let abortCtrl: AbortController | null = null
let sseTimeout: ReturnType<typeof setTimeout> | null = null

function toggleLogs(idx: number) {
  steps.value[idx].expanded = !steps.value[idx].expanded
}

function updateSteps(stepIndex: number, status: string, message?: string, logs?: string[]) {
  // 已完成的步骤（收起日志）
  for (let i = 0; i < stepIndex - 1 && i < steps.value.length; i++) {
    if (steps.value[i].status !== 'completed') {
      steps.value[i].status = 'completed'
      steps.value[i].expanded = false
    }
  }

  if (status === 'success') {
    // 全部完成
    for (const s of steps.value) {
      s.status = 'completed'
      s.expanded = false
    }
    finalStatus.value = 'success'
    finalMessage.value = message || '部署成功'
  } else if (status === 'failed') {
    // 当前步骤标记失败（展开显示日志）
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
    // in_progress：当前步骤进行中（自动展开日志）
    if (stepIndex - 1 >= 0 && stepIndex - 1 < steps.value.length) {
      const s = steps.value[stepIndex - 1]
      s.status = 'in_progress'
      if (logs?.length) s.logs = logs
      s.expanded = true
    }
  }
}

function subscribeSSE() {
  const token = localStorage.getItem('token')
  abortCtrl = new AbortController()

  // 6 分钟超时（后端最多等 300s + 前段步骤时间）
  sseTimeout = setTimeout(() => {
    abortCtrl?.abort()
    if (finalStatus.value === 'in_progress') {
      finalStatus.value = 'failed'
      finalMessage.value = '部署超时（6 分钟），请在实例列表查看状态'
    }
  }, 360_000)

  fetchEventSource(`${API_BASE}/deploy/progress/${deployId}`, {
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
    // abort 引起的错误忽略
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

const cancelling = ref(false)

async function handleCancel() {
  if (!confirm('确定要停止部署吗？这将立即清除命名空间和所有已创建的资源。')) return
  cancelling.value = true
  try {
    const res = await api.post(`/deploy/${deployId}/cancel`)
    toast.info(res.data?.data?.message || '部署已取消')
  } catch {
    toast.error('取消请求失败')
  } finally {
    cancelling.value = false
  }
}

const isFinished = computed(() => finalStatus.value !== 'in_progress')
</script>

<template>
  <div class="max-w-2xl mx-auto">
    <!-- 顶部标题 + 进度条（固定在顶部） -->
    <div class="sticky top-0 z-10 bg-background pt-6 pb-4 px-6 space-y-4">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <Rocket class="w-6 h-6 text-primary" />
          <div>
            <h1 class="text-xl font-semibold">部署实例</h1>
            <p v-if="instanceName" class="text-sm text-muted-foreground">{{ instanceName }}</p>
          </div>
        </div>
        <Button
          v-if="!isFinished"
          variant="destructive"
          size="sm"
          :disabled="cancelling"
          @click="handleCancel"
        >
          <Loader2 v-if="cancelling" class="w-4 h-4 mr-1 animate-spin" />
          <Square v-else class="w-4 h-4 mr-1" />
          取消部署
        </Button>
      </div>

      <!-- 总进度条 -->
      <div class="w-full h-2 bg-muted rounded-full overflow-hidden">
        <div
          class="h-full rounded-full transition-all duration-500"
          :class="{
            'bg-primary': finalStatus === 'in_progress',
            'bg-green-500': finalStatus === 'success',
            'bg-red-500': finalStatus === 'failed',
          }"
          :style="{ width: `${percent}%` }"
        />
      </div>
    </div>

    <!-- 步骤时间线 -->
    <Card class="mx-6 mt-2">
      <CardHeader>
        <CardTitle class="text-base">部署步骤</CardTitle>
      </CardHeader>
      <CardContent>
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
              :class="{
                'bg-green-500/40': step.status === 'completed',
                'bg-primary/40': step.status === 'in_progress',
                'bg-red-500/40': step.status === 'failed',
                'bg-muted': step.status === 'pending',
              }"
            />
            <!-- 步骤头部 -->
            <div
              class="flex items-start gap-3 cursor-pointer select-none"
              @click="step.logs.length ? toggleLogs(idx) : undefined"
            >
              <!-- 图标 -->
              <div class="shrink-0 mt-0.5">
                <CheckCircle
                  v-if="step.status === 'completed'"
                  class="w-6 h-6 text-green-500"
                />
                <Loader2
                  v-else-if="step.status === 'in_progress'"
                  class="w-6 h-6 text-primary animate-spin"
                />
                <XCircle
                  v-else-if="step.status === 'failed'"
                  class="w-6 h-6 text-red-500"
                />
                <Circle
                  v-else
                  class="w-6 h-6 text-muted-foreground/40"
                />
              </div>
              <!-- 内容 -->
              <div class="flex-1 min-w-0 flex items-center gap-1.5">
                <span
                  class="text-sm font-medium"
                  :class="{
                    'text-green-500': step.status === 'completed',
                    'text-foreground': step.status === 'in_progress',
                    'text-red-500': step.status === 'failed',
                    'text-muted-foreground': step.status === 'pending',
                  }"
                >
                  {{ step.name }}
                </span>
                <!-- 展开/收起指示器（仅有日志时显示） -->
                <component
                  :is="step.expanded ? ChevronDown : ChevronRight"
                  v-if="step.logs.length > 0"
                  class="w-3.5 h-3.5 text-muted-foreground shrink-0"
                />
              </div>
            </div>

            <!-- 日志区域（展开时显示） -->
            <div
              v-if="step.expanded && step.logs.length > 0"
              class="ml-9 mt-1.5 rounded bg-muted/50 border border-border/50 px-3 py-2 space-y-0.5 max-h-40 overflow-y-auto"
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

            <!-- 失败消息（始终显示） -->
            <p
              v-if="step.message && step.status === 'failed' && !step.expanded"
              class="ml-9 mt-0.5 text-xs text-red-400 break-all"
            >
              {{ step.message }}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>

    <!-- 结果区域 -->
    <Card v-if="isFinished" class="mx-6 mt-4 mb-6">
      <CardContent class="pt-6">
        <!-- 成功 -->
        <div v-if="finalStatus === 'success'" class="text-center space-y-4">
          <CheckCircle class="w-12 h-12 text-green-500 mx-auto" />
          <div>
            <p class="text-lg font-semibold text-green-500">部署成功</p>
            <p class="text-sm text-muted-foreground mt-1">实例 {{ instanceName }} 已就绪</p>
          </div>
          <div class="flex justify-center gap-3">
            <Button @click="router.push('/instances')">
              <ExternalLink class="w-4 h-4 mr-1" /> 查看实例列表
            </Button>
            <Button variant="outline" @click="router.push('/deploy')">
              继续部署
            </Button>
          </div>
        </div>

        <!-- 失败 -->
        <div v-else class="text-center space-y-4">
          <XCircle class="w-12 h-12 text-red-500 mx-auto" />
          <div>
            <p class="text-lg font-semibold text-red-500">部署失败</p>
            <p class="text-sm text-muted-foreground mt-1 max-w-md mx-auto break-all">
              {{ finalMessage }}
            </p>
          </div>
          <div class="flex justify-center gap-3">
            <Button @click="router.push('/deploy')">
              <ArrowLeft class="w-4 h-4 mr-1" /> 返回重新部署
            </Button>
            <Button variant="outline" @click="router.push('/instances')">
              查看实例列表
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
