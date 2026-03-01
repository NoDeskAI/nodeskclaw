<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, inject, type Ref, type ComputedRef } from 'vue'
import { useRouter } from 'vue-router'
import { ExternalLink, RefreshCw, Trash2, Circle, Loader2, Copy, Check, RotateCcw, AlertTriangle } from 'lucide-vue-next'
import api from '@/services/api'
import { useToast } from '@/composables/useToast'

const router = useRouter()
const toast = useToast()
const instanceId = inject<ComputedRef<string>>('instanceId')!
const instanceBasic = inject<Ref<{ name: string } | null>>('instanceBasic')!
const refreshInstanceBasic = inject<() => Promise<void>>('refreshInstanceBasic')!
const myInstanceRole = inject<Ref<string | null>>('myInstanceRole', ref(null))
const ROLE_LEVEL: Record<string, number> = { viewer: 10, user: 20, editor: 30, admin: 40 }
const canEdit = computed(() => (ROLE_LEVEL[myInstanceRole.value ?? ''] ?? 0) >= ROLE_LEVEL.editor)
const canAdmin = computed(() => (ROLE_LEVEL[myInstanceRole.value ?? ''] ?? 0) >= ROLE_LEVEL.admin)

interface InstanceDetail {
  id: string
  name: string
  status: string
  image_version: string
  ingress_domain: string | null
  namespace: string
  replicas: number
  available_replicas: number
  cpu_request: string
  cpu_limit: string
  mem_request: string
  mem_limit: string
  env_vars: Record<string, string> | null
  created_at: string
  pods: { name: string; status: string; ready: boolean; restart_count: number }[]
}

const instance = ref<InstanceDetail | null>(null)
const loading = ref(true)
const pageError = ref('')
const openclawUrl = ref('')
const urlCopied = ref(false)
const restarting = ref(false)
const showRestartDialog = ref(false)
const showDeleteDialog = ref(false)
const deleting = ref(false)

let pollTimer: ReturnType<typeof setInterval> | null = null
let pollTimeout: ReturnType<typeof setTimeout> | null = null

function formatCpu(val: string): string {
  if (val.endsWith('m')) {
    const cores = parseInt(val.slice(0, -1), 10) / 1000
    return Number.isInteger(cores) ? `${cores} 核` : `${cores.toFixed(2)} 核`
  }
  return `${val} 核`
}

async function copyUrl() {
  try {
    await navigator.clipboard.writeText(openclawUrl.value)
    urlCopied.value = true
    setTimeout(() => { urlCopied.value = false }, 2000)
  } catch { /* ignore */ }
}

onMounted(async () => {
  await fetchDetail()
  if (instance.value?.status === 'restarting') {
    restarting.value = true
    startPolling()
  }
})

onUnmounted(() => {
  stopPolling()
})

async function fetchDetail() {
  loading.value = true
  try {
    const res = await api.get(`/instances/${instanceId.value}`)
    instance.value = res.data.data

    if (instance.value?.ingress_domain && instance.value.env_vars) {
      const token = instance.value.env_vars.OPENCLAW_GATEWAY_TOKEN
      if (token) {
        openclawUrl.value = `https://${instance.value.ingress_domain}?token=${token}`
      }
    }
  } catch (e: any) {
    pageError.value = e?.response?.data?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function pollOnce() {
  try {
    const res = await api.get(`/instances/${instanceId.value}`)
    instance.value = res.data.data
    await refreshInstanceBasic()

    if (instance.value && instance.value.status !== 'restarting') {
      stopPolling()
      restarting.value = false
      toast.success('重启完成，实例已恢复运行')
    }
  } catch {
    // 轮询期间忽略网络错误
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(pollOnce, 3000)
  pollTimeout = setTimeout(() => {
    stopPolling()
    restarting.value = false
    toast.error('重启超时，请手动刷新查看状态')
  }, 120_000)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  if (pollTimeout) { clearTimeout(pollTimeout); pollTimeout = null }
}

async function handleRestart() {
  showRestartDialog.value = false
  restarting.value = true
  try {
    const res = await api.post(`/instances/${instanceId.value}/restart`)
    toast.success(res.data?.message || '已触发重启，实例将在数秒后恢复')
    await refreshInstanceBasic()
    startPolling()
  } catch (e: any) {
    restarting.value = false
    const msg = e?.response?.data?.message || e?.message || '重启失败'
    toast.error(msg)
    console.error('[handleRestart]', e)
  }
}

async function handleDelete() {
  showDeleteDialog.value = false
  deleting.value = true
  try {
    await api.delete(`/instances/${instanceId.value}`)
    toast.success('实例已删除')
    router.push('/instances')
  } catch (e: any) {
    deleting.value = false
    toast.error(e?.response?.data?.message || '删除失败')
  }
}
</script>

<template>
  <div>
    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <div v-else-if="pageError" class="text-center py-20 text-destructive">{{ pageError }}</div>

    <div v-else-if="instance" class="space-y-6">
      <!-- OpenClaw 访问 -->
      <div v-if="openclawUrl" class="p-4 rounded-xl border border-primary/30 bg-primary/5 space-y-3">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm font-medium">OpenClaw 访问地址</p>
            <p class="text-xs text-muted-foreground mt-0.5">
              {{ restarting ? '实例正在重启，请稍候...' : '点击即可打开 AI 助手' }}
            </p>
          </div>
          <button
            v-if="restarting"
            disabled
            class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-muted text-muted-foreground text-sm font-medium cursor-not-allowed"
          >
            <Loader2 class="w-4 h-4 animate-spin" />
            重启中
          </button>
          <a
            v-else
            :href="openclawUrl"
            target="_blank"
            class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            <ExternalLink class="w-4 h-4" />
            打开
          </a>
        </div>
        <div class="flex items-center gap-2 px-3 py-2 rounded-lg bg-background/60 border border-border/50">
          <a
            :href="openclawUrl"
            target="_blank"
            class="flex-1 text-xs font-mono truncate transition-colors"
            :class="restarting ? 'text-muted-foreground pointer-events-none' : 'text-primary/80 hover:text-primary'"
          >{{ openclawUrl }}</a>
          <button
            class="shrink-0 p-1 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
            @click="copyUrl"
          >
            <Check v-if="urlCopied" class="w-3.5 h-3.5 text-green-400" />
            <Copy v-else class="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <!-- 基本信息 -->
      <div class="p-4 rounded-xl border border-border bg-card">
        <h2 class="text-sm font-medium mb-3">基本信息</h2>
        <div class="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span class="text-muted-foreground">镜像版本</span>
            <span class="ml-2 font-mono text-xs bg-muted px-1.5 py-0.5 rounded">{{ instance.image_version }}</span>
          </div>
          <div>
            <span class="text-muted-foreground">CPU</span>
            <span class="ml-2">{{ formatCpu(instance.cpu_limit) }}</span>
          </div>
          <div>
            <span class="text-muted-foreground">内存</span>
            <span class="ml-2">{{ instance.mem_limit }}</span>
          </div>
          <div class="col-span-2">
            <span class="text-muted-foreground">创建时间</span>
            <span class="ml-2">{{ new Date(instance.created_at).toLocaleString('zh-CN') }}</span>
          </div>
        </div>
      </div>

      <!-- Pod 状态 -->
      <div v-if="instance.pods?.length" class="p-4 rounded-xl border border-border bg-card">
        <h2 class="text-sm font-medium mb-3">Pod 状态</h2>
        <div class="space-y-2">
          <div
            v-for="pod in instance.pods"
            :key="pod.name"
            class="flex items-center justify-between text-sm p-2 rounded-md bg-muted/30"
          >
            <div class="flex items-center gap-2">
              <Circle
                class="w-2 h-2 fill-current"
                :class="pod.ready ? 'text-green-400' : 'text-yellow-400'"
              />
              <span class="font-mono text-xs">{{ pod.name }}</span>
            </div>
            <span class="text-xs text-muted-foreground">
              重启 {{ pod.restart_count }} 次
            </span>
          </div>
        </div>
      </div>
      <div v-else-if="restarting" class="p-4 rounded-xl border border-amber-500/20 bg-amber-500/5">
        <div class="flex items-center gap-2 text-sm text-amber-400">
          <Loader2 class="w-4 h-4 animate-spin" />
          实例正在重启，等待新 Pod 启动...
        </div>
      </div>

      <!-- 操作 -->
      <div class="flex items-center gap-3 pt-4 border-t border-border">
        <button
          class="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-border text-sm hover:bg-card transition-colors"
          @click="fetchDetail"
        >
          <RefreshCw class="w-4 h-4" />
          刷新
        </button>
        <button
          v-if="canEdit"
          class="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-amber-500/30 text-amber-400 text-sm hover:bg-amber-500/10 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="restarting"
          @click="showRestartDialog = true"
        >
          <RotateCcw class="w-4 h-4" :class="restarting ? 'animate-spin' : ''" />
          {{ restarting ? '重启中...' : '重启实例' }}
        </button>
        <button
          v-if="canAdmin"
          class="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-red-500/30 text-red-400 text-sm hover:bg-red-500/10 transition-colors ml-auto disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="deleting"
          @click="showDeleteDialog = true"
        >
          <Loader2 v-if="deleting" class="w-4 h-4 animate-spin" />
          <Trash2 v-else class="w-4 h-4" />
          {{ deleting ? '删除中...' : '删除实例' }}
        </button>
      </div>
    </div>

    <!-- 重启确认弹窗 -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showRestartDialog" class="fixed inset-0 z-50 flex items-center justify-center">
          <div class="absolute inset-0 bg-black/50" @click="showRestartDialog = false" />
          <div class="relative bg-card border border-border rounded-xl p-6 w-full max-w-sm shadow-lg space-y-4">
            <div class="flex items-center gap-3">
              <div class="p-2 rounded-lg bg-amber-500/10">
                <AlertTriangle class="w-5 h-5 text-amber-400" />
              </div>
              <h3 class="text-base font-semibold">重启实例</h3>
            </div>
            <div class="text-sm text-muted-foreground space-y-2">
              <p>即将重启实例，这将会：</p>
              <ul class="list-disc list-inside space-y-1 text-xs">
                <li>关闭实例中所有运行的程序</li>
                <li>重启期间服务将短暂不可用</li>
                <li>正在进行的对话和任务会被中断</li>
              </ul>
            </div>
            <div class="flex justify-end gap-3 pt-2">
              <button
                class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-muted transition-colors"
                @click="showRestartDialog = false"
              >
                取消
              </button>
              <button
                class="px-4 py-2 rounded-lg bg-amber-500 text-white text-sm font-medium hover:bg-amber-600 transition-colors"
                @click="handleRestart"
              >
                确认重启
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 删除确认弹窗 -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showDeleteDialog" class="fixed inset-0 z-50 flex items-center justify-center">
          <div class="absolute inset-0 bg-black/50" @click="showDeleteDialog = false" />
          <div class="relative bg-card border border-border rounded-xl p-6 w-full max-w-sm shadow-lg space-y-4">
            <div class="flex items-center gap-3">
              <div class="p-2 rounded-lg bg-red-500/10">
                <AlertTriangle class="w-5 h-5 text-red-400" />
              </div>
              <h3 class="text-base font-semibold">删除实例</h3>
            </div>
            <div class="text-sm text-muted-foreground space-y-2">
              <p>确定删除实例「<span class="text-foreground font-medium">{{ instanceBasic?.name }}</span>」？</p>
              <ul class="list-disc list-inside space-y-1 text-xs">
                <li>实例及其 K8s 资源将被永久删除</li>
                <li>所有对话记录和工作区数据将丢失</li>
                <li>此操作不可恢复</li>
              </ul>
            </div>
            <div class="flex justify-end gap-3 pt-2">
              <button
                class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-muted transition-colors"
                @click="showDeleteDialog = false"
              >
                取消
              </button>
              <button
                class="px-4 py-2 rounded-lg bg-red-500 text-white text-sm font-medium hover:bg-red-600 transition-colors"
                @click="handleDelete"
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
