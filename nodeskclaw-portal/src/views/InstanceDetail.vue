<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, inject, type Ref, type ComputedRef } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  RefreshCw, Trash2, Circle, Loader2, Copy, Check, RotateCcw, AlertTriangle,
} from 'lucide-vue-next'
import api from '@/services/api'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'

const router = useRouter()
const toast = useToast()
const { t, locale } = useI18n()

function joinNames(names: string[]): string {
  return names.join(String(locale.value).startsWith('zh') ? '、' : ', ')
}
const { confirm } = useConfirm()
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
  storage_size: string
  env_vars: Record<string, string> | null
  created_at: string
  workspaces?: { id: string; name: string }[]
  pods: { name: string; status: string; ready: boolean; restart_count: number }[]
  endpoint_url?: string | null
  compute_provider?: string
  runtime?: string
}

const instance = ref<InstanceDetail | null>(null)
const isDocker = computed(() => instance.value?.compute_provider === 'docker')

const ENGINE_NAMES: Record<string, string> = {
  openclaw: '全能工作引擎 (Powered by OpenClaw)',
  zeroclaw: '高性能工作引擎 (Powered by ZeroClaw)',
  nanobot: '轻量工作引擎 (Powered by Nanobot)',
}
const engineLabel = computed(() => ENGINE_NAMES[instance.value?.runtime ?? 'openclaw'] ?? instance.value?.runtime ?? 'openclaw')
const loading = ref(true)
const pageError = ref('')
const gatewayToken = ref('')
const tokenCopied = ref(false)
const restarting = ref(false)
const resettingToken = ref(false)
const showRestartDialog = ref(false)
const showDeleteDialog = ref(false)
const deleting = ref(false)

function formatCpu(val: string): string {
  if (val.endsWith('m')) {
    const cores = parseInt(val.slice(0, -1), 10) / 1000
    return Number.isInteger(cores) ? `${cores} 核` : `${cores.toFixed(2)} 核`
  }
  return `${val} 核`
}

let pollTimer: ReturnType<typeof setInterval> | null = null
let pollTimeout: ReturnType<typeof setTimeout> | null = null

const maskedGatewayToken = computed(() => {
  const token = gatewayToken.value
  if (!token) return ''
  if (token.length <= 4) return `${token.slice(0, 1)}****${token.slice(-1)}`
  if (token.length <= 8) return `${token.slice(0, 2)}****${token.slice(-2)}`
  return `${token.slice(0, 6)}********${token.slice(-4)}`
})

function syncGatewayToken(detail: InstanceDetail | null) {
  gatewayToken.value = detail?.env_vars?.OPENCLAW_GATEWAY_TOKEN || ''
}

async function copyToken() {
  try {
    await navigator.clipboard.writeText(gatewayToken.value)
    tokenCopied.value = true
    toast.success(t('agentDetailDialog.tokenCopied'))
    setTimeout(() => { tokenCopied.value = false }, 2000)
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

function normalizeWorkspaces(data: any): { id: string; name: string }[] {
  if (Array.isArray(data?.workspaces)) return data.workspaces
  if (data?.workspace_id) return [{ id: data.workspace_id, name: data.workspace_name ?? '' }]
  return []
}

async function fetchDetail() {
  loading.value = true
  try {
    const res = await api.get(`/instances/${instanceId.value}`)
    const data = res.data.data
    if (data) {
      data.workspaces = normalizeWorkspaces(data)
    }
    instance.value = data
    syncGatewayToken(instance.value)
  } catch (e: any) {
    pageError.value = e?.response?.data?.message || t('agentDetailDialog.loadFailed')
  } finally {
    loading.value = false
  }
}

async function pollOnce() {
  try {
    const res = await api.get(`/instances/${instanceId.value}`)
    const data = res.data.data
    if (data) {
      data.workspaces = normalizeWorkspaces(data)
    }
    instance.value = data
    syncGatewayToken(instance.value)
    await refreshInstanceBasic()

    if (instance.value && instance.value.status !== 'restarting') {
      stopPolling()
      restarting.value = false
      toast.success('重启完成，AI 员工已恢复运行')
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
    toast.success(res.data?.message || '已触发重启，AI 员工将在数秒后恢复')
    await refreshInstanceBasic()
    startPolling()
  } catch (e: any) {
    restarting.value = false
    const msg = e?.response?.data?.message || e?.message || '重启失败'
    toast.error(msg)
    console.error('[handleRestart]', e)
  }
}

async function handleResetToken() {
  if (restarting.value || resettingToken.value) return

  const ok = await confirm({
    title: t('agentDetailDialog.resetTokenConfirmTitle'),
    description: t('agentDetailDialog.resetTokenConfirmDesc'),
    confirmText: t('agentDetailDialog.resetTokenConfirmAction'),
    cancelText: t('common.cancel'),
    variant: 'danger',
  })
  if (!ok) return

  resettingToken.value = true
  try {
    const res = await api.post(`/instances/${instanceId.value}/regenerate-token`)
    const token = res.data?.data?.token || ''
    if (token) {
      gatewayToken.value = token
      if (instance.value) {
        instance.value.env_vars = {
          ...(instance.value.env_vars || {}),
          OPENCLAW_GATEWAY_TOKEN: token,
          NODESKCLAW_TOKEN: token,
        }
      }
    }
    restarting.value = true
    toast.success(res.data?.message || t('agentDetailDialog.resetTokenSuccess'))
    await refreshInstanceBasic()
    startPolling()
  } catch (e: any) {
    toast.error(e?.response?.data?.message || t('agentDetailDialog.resetTokenFailed'))
  } finally {
    resettingToken.value = false
  }
}

async function handleDelete() {
  showDeleteDialog.value = false
  deleting.value = true
  try {
    await api.delete(`/instances/${instanceId.value}`)
    toast.success('AI 员工已删除')
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
      <!-- Access Token -->
      <div v-if="gatewayToken" class="p-4 rounded-xl border border-primary/30 bg-primary/5 space-y-3">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm font-medium">{{ t('agentDetailDialog.accessToken') }}</p>
            <p class="text-xs text-muted-foreground mt-0.5">
              {{ restarting ? t('agentDetailDialog.accessTokenRestartingHint') : t('agentDetailDialog.accessTokenHint') }}
            </p>
          </div>
          <button
            class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="restarting || resettingToken"
            @click="handleResetToken"
          >
            <Loader2 v-if="resettingToken" class="w-4 h-4 animate-spin" />
            <RotateCcw v-else class="w-4 h-4" />
            {{ resettingToken ? t('agentDetailDialog.resettingToken') : t('agentDetailDialog.resetToken') }}
          </button>
        </div>
        <div class="flex items-center gap-2 px-3 py-2 rounded-lg bg-background/60 border border-border/50">
          <span class="flex-1 text-xs font-mono break-all text-foreground/80">{{ maskedGatewayToken }}</span>
          <button
            class="shrink-0 p-1 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
            :disabled="!gatewayToken"
            @click="copyToken"
          >
            <Check v-if="tokenCopied" class="w-3.5 h-3.5 text-green-400" />
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
          <div>
            <span class="text-muted-foreground">存储</span>
            <span class="ml-2">{{ instance.storage_size }}</span>
          </div>
          <div v-if="instance.runtime" class="col-span-2">
            <span class="text-muted-foreground">{{ t('engine.title') }}</span>
            <span class="ml-2 text-xs bg-muted px-1.5 py-0.5 rounded">{{ engineLabel }}</span>
          </div>
          <div class="col-span-2">
            <span class="text-muted-foreground">创建时间</span>
            <span class="ml-2">{{ new Date(instance.created_at).toLocaleString('zh-CN') }}</span>
          </div>
          <div v-if="instance.endpoint_url" class="col-span-2">
            <span class="text-muted-foreground">访问地址</span>
            <a
              :href="instance.endpoint_url"
              target="_blank"
              rel="noopener"
              class="ml-2 text-primary hover:underline font-mono text-xs"
            >{{ instance.endpoint_url }}</a>
          </div>
        </div>
      </div>

      <!-- Pod / 容器状态 -->
      <div v-if="instance.pods?.length" class="p-4 rounded-xl border border-border bg-card">
        <h2 class="text-sm font-medium mb-3">{{ isDocker ? '容器状态' : 'Pod 状态' }}</h2>
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
          AI 员工正在重启，等待新 Pod 启动...
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
          {{ restarting ? '重启中...' : '重启AI 员工' }}
        </button>
        <button
          v-if="canAdmin"
          class="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-red-500/30 text-red-400 text-sm hover:bg-red-500/10 transition-colors ml-auto disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="deleting"
          @click="showDeleteDialog = true"
        >
          <Loader2 v-if="deleting" class="w-4 h-4 animate-spin" />
          <Trash2 v-else class="w-4 h-4" />
          {{ deleting ? '删除中...' : '删除AI 员工' }}
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
              <h3 class="text-base font-semibold">重启AI 员工</h3>
            </div>
            <div class="text-sm text-muted-foreground space-y-2">
              <p>即将重启AI 员工，这将会：</p>
              <ul class="list-disc list-inside space-y-1 text-xs">
                <li>关闭AI 员工中所有运行的程序</li>
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
              <h3 class="text-base font-semibold">删除AI 员工</h3>
            </div>
            <div v-if="instance?.workspaces?.length" class="text-sm text-muted-foreground space-y-2">
              <p>{{ t('instanceDetail.cannotDeleteInWorkspaces', { names: joinNames(instance.workspaces.map(w => w.name)) }) }}</p>
              <p class="text-xs">{{ t('instanceDetail.workspaces') }}:</p>
              <div class="flex flex-wrap gap-2 mt-1">
                <router-link
                  v-for="ws in instance.workspaces"
                  :key="ws.id"
                  :to="`/workspace/${ws.id}`"
                  class="text-xs text-primary hover:underline"
                >
                  {{ ws.name }}
                </router-link>
              </div>
            </div>
            <div v-else class="text-sm text-muted-foreground space-y-2">
              <p>确定删除AI 员工「<span class="text-foreground font-medium">{{ instanceBasic?.name }}</span>」？</p>
              <ul class="list-disc list-inside space-y-1 text-xs">
                <li>AI 员工及其{{ isDocker ? '容器' : ' K8s' }}资源将被永久删除</li>
                <li>所有对话记录和办公室数据将丢失</li>
                <li>此操作不可恢复</li>
              </ul>
            </div>
            <div class="flex justify-end gap-3 pt-2">
              <button
                class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-muted transition-colors"
                @click="showDeleteDialog = false"
              >
                {{ instance?.workspaces?.length ? t('common.close') : t('common.cancel') }}
              </button>
              <button
                v-if="!instance?.workspaces?.length"
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
