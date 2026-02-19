<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useInstanceStore, type InstanceDetail as IDetail, type DeployRecord, type PodInfo } from '@/stores/instance'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import api from '@/services/api'
import StatusDot from '@/components/StatusDot.vue'
import {
  ArrowLeft, RefreshCw, FileText, MoreVertical, Scale, Trash2, RotateCw,
  ArrowUpCircle, Cpu, MemoryStick, HardDrive, Globe, Container, Copy,
} from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { useNotify } from '@/components/ui/notify'

const route = useRoute()
const router = useRouter()
const instanceStore = useInstanceStore()
const notify = useNotify()

const detail = ref<IDetail | null>(null)
const loading = ref(true)
const history = ref<DeployRecord[]>([])
const logsText = ref('')
const showingLogs = ref(false)
const selectedPod = ref('')
const activeTab = ref('overview')

const instanceId = route.params.id as string

// LLM config
interface LlmConfigItem {
  provider: string
  key_source: string
  key_label: string | null
  api_key_masked: string | null
}
const llmConfigs = ref<LlmConfigItem[]>([])
const llmConfigLoading = ref(false)

async function fetchLlmConfig() {
  llmConfigLoading.value = true
  try {
    const res = await api.get(`/instances/${instanceId}/llm-config`)
    llmConfigs.value = res.data.data ?? []
  } catch {
    llmConfigs.value = []
  } finally {
    llmConfigLoading.value = false
  }
}

// Modal states
const showScaleDialog = ref(false)
const showRestartDialog = ref(false)
const showDeleteDialog = ref(false)
const showUpdateDialog = ref(false)
const deleteConfirmName = ref('')
const scaleReplicas = ref(1)

// Update form
const updateForm = ref({
  image_version: '',
  cpu_request: '',
  cpu_limit: '',
  mem_request: '',
  mem_limit: '',
})

onMounted(async () => {
  try {
    detail.value = await instanceStore.fetchDetail(instanceId)
    scaleReplicas.value = detail.value.replicas
    updateForm.value = {
      image_version: detail.value.image_version,
      cpu_request: detail.value.cpu_request,
      cpu_limit: detail.value.cpu_limit,
      mem_request: detail.value.mem_request,
      mem_limit: detail.value.mem_limit,
    }
    history.value = await instanceStore.getHistory(instanceId)
    fetchLlmConfig()
  } finally {
    loading.value = false
  }
})

// ── 镜像版本列表 ──
const imageTags = ref<string[]>([])
const loadingTags = ref(false)

async function fetchImageTags() {
  loadingTags.value = true
  try {
    const res = await api.get('/registry/tags')
    const tags = res.data.data as { tag: string }[]
    imageTags.value = tags.map((t) => t.tag)
  } catch {
    imageTags.value = []
  } finally {
    loadingTags.value = false
  }
}

function podStatusToDot(phase: string) {
  if (phase === 'Running') return 'running' as const
  if (phase === 'Pending') return 'pending' as const
  if (phase === 'Failed') return 'failed' as const
  return 'unknown' as const
}

// Scale
async function handleScale() {
  try {
    await instanceStore.scale(instanceId, scaleReplicas.value)
    toast.success(`已扩缩容至 ${scaleReplicas.value} 副本`)
    showScaleDialog.value = false
    detail.value = await instanceStore.fetchDetail(instanceId)
  } catch {
    toast.error('扩缩容失败')
  }
}

// Restart
async function handleRestart() {
  try {
    await instanceStore.restart(instanceId)
    toast.success('已触发滚动重启')
    showRestartDialog.value = false
  } catch {
    toast.error('重启失败')
  }
}

// Delete
async function handleDelete() {
  try {
    await instanceStore.deleteInstance(instanceId)
    toast.success('实例已删除')
    router.push('/instances')
  } catch {
    toast.error('删除失败')
  }
}

// Save Config (step 1 of two-step mode)
const applyingConfig = ref(false)
const showApplyConfirm = ref(false)

async function handleUpdate() {
  try {
    await instanceStore.saveConfig(instanceId, {
      image_version: updateForm.value.image_version || undefined,
      cpu_request: updateForm.value.cpu_request || undefined,
      cpu_limit: updateForm.value.cpu_limit || undefined,
      mem_request: updateForm.value.mem_request || undefined,
      mem_limit: updateForm.value.mem_limit || undefined,
    })
    toast.success('配置已保存，请在"配置"页签点击"应用"以生效')
    showUpdateDialog.value = false
    detail.value = await instanceStore.fetchDetail(instanceId)
  } catch {
    toast.error('保存失败')
  }
}

// Apply Config (step 2 of two-step mode)
async function handleApply() {
  applyingConfig.value = true
  try {
    await instanceStore.applyConfig(instanceId)
    toast.success('配置已应用，滚动更新已触发')
    showApplyConfirm.value = false
    detail.value = await instanceStore.fetchDetail(instanceId)
    history.value = await instanceStore.getHistory(instanceId)
  } catch {
    toast.error('应用失败')
  } finally {
    applyingConfig.value = false
  }
}

// Rollback
async function handleRollback(revision: number) {
  try {
    await instanceStore.rollback(instanceId, revision)
    toast.success(`已回滚到 Revision ${revision}`)
    detail.value = await instanceStore.fetchDetail(instanceId)
    history.value = await instanceStore.getHistory(instanceId)
  } catch {
    toast.error('回滚失败')
  }
}

// View logs
async function viewLogs(podName: string) {
  selectedPod.value = podName
  showingLogs.value = true
  try {
    logsText.value = await instanceStore.getLogs(instanceId, podName)
  } catch {
    logsText.value = '获取日志失败'
  }
}

// Gateway Token
const gatewayToken = computed(() => detail.value?.env_vars?.OPENCLAW_GATEWAY_TOKEN || '')
const consoleUrl = computed(() => {
  if (!detail.value?.ingress_domain || !gatewayToken.value) return ''
  return `https://${detail.value.ingress_domain}/?token=${gatewayToken.value}`
})
const syncingToken = ref(false)

async function handleSyncToken() {
  syncingToken.value = true
  try {
    await instanceStore.syncToken(instanceId)
    detail.value = await instanceStore.fetchDetail(instanceId)
    toast.success('Token 获取成功')
  } catch {
    toast.error('获取 Token 失败，请确保实例 Pod 正在运行')
  } finally {
    syncingToken.value = false
  }
}

async function copyEnvVar(key: string, val: string) {
  const text = `${key}=${val}`
  try {
    await navigator.clipboard.writeText(text)
    notify.success(`已复制 ${key}`)
  } catch {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    notify.success(`已复制 ${key}`)
  }
}

const canDelete = computed(() => deleteConfirmName.value === detail.value?.name)

function formatTime(ts: string | null): string {
  if (!ts) return '-'
  return new Date(ts).toLocaleString('zh-CN')
}
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <Button variant="ghost" size="sm" @click="router.back()">
          <ArrowLeft class="w-4 h-4" />
        </Button>
        <h1 class="text-2xl font-bold">{{ detail?.name || '加载中...' }}</h1>
        <Badge v-if="detail" :variant="detail.status === 'running' ? 'default' : 'destructive'">
          {{ detail.status }}
        </Badge>
      </div>
      <div v-if="detail" class="flex items-center gap-2">
        <Button variant="outline" size="sm" @click="showUpdateDialog = true; fetchImageTags()">
          <ArrowUpCircle class="w-4 h-4 mr-1" />
          滚动更新
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button variant="outline" size="sm">
              <MoreVertical class="w-4 h-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem @click="showRestartDialog = true">
              <RotateCw class="w-4 h-4 mr-2" /> 重启
            </DropdownMenuItem>
            <DropdownMenuItem @click="showScaleDialog = true">
              <Scale class="w-4 h-4 mr-2" /> 扩缩容
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem class="text-destructive" @click="showDeleteDialog = true">
              <Trash2 class="w-4 h-4 mr-2" /> 删除
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>

    <div v-if="loading" class="text-muted-foreground text-center py-12">加载中...</div>

    <template v-else-if="detail">
      <Tabs v-model="activeTab">
        <TabsList>
          <TabsTrigger value="overview">概览</TabsTrigger>
          <TabsTrigger value="pods">Pod 列表</TabsTrigger>
          <TabsTrigger value="config">配置</TabsTrigger>
          <TabsTrigger value="llm">LLM 配置</TabsTrigger>
          <TabsTrigger value="logs">日志</TabsTrigger>
          <TabsTrigger value="events">事件</TabsTrigger>
          <TabsTrigger value="history">历史</TabsTrigger>
        </TabsList>

        <!-- Overview Tab -->
        <TabsContent value="overview">
          <div class="grid grid-cols-2 gap-4 mt-4">
            <Card>
              <CardHeader><CardTitle class="text-sm">基本信息</CardTitle></CardHeader>
              <CardContent class="text-sm space-y-2">
                <div class="flex justify-between"><span class="text-muted-foreground">实例名称</span><span>{{ detail.name }}</span></div>
                <div class="flex justify-between"><span class="text-muted-foreground">实例标识</span><span class="font-mono text-xs">{{ detail.slug }}</span></div>
                <div class="flex justify-between"><span class="text-muted-foreground">命名空间</span><span class="font-mono text-xs">{{ detail.namespace }}</span></div>
                <div class="flex justify-between"><span class="text-muted-foreground">镜像</span><span>{{ detail.image_version }}</span></div>
                <div class="flex justify-between"><span class="text-muted-foreground">集群</span><span>{{ detail.cluster_id }}</span></div>
                <div class="flex justify-between"><span class="text-muted-foreground">创建时间</span><span>{{ formatTime(detail.created_at) }}</span></div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle class="text-sm">运行状态</CardTitle></CardHeader>
              <CardContent class="text-sm space-y-2">
                <div class="flex justify-between"><span class="text-muted-foreground">副本</span><span>{{ detail.available_replicas }}/{{ detail.replicas }}</span></div>
                <div class="flex justify-between">
                  <span class="text-muted-foreground">状态</span>
                  <StatusDot :status="
                    detail.status === 'running' ? 'running'
                    : detail.status === 'failed' ? 'failed'
                    : ['pending', 'deploying', 'creating', 'updating'].includes(detail.status) ? 'pending'
                    : 'unknown'
                  " />
                </div>
                <div class="flex justify-between">
                  <span class="text-muted-foreground">访问地址</span>
                  <a
                    v-if="detail.ingress_domain"
                    :href="`https://${detail.ingress_domain}`"
                    target="_blank"
                    class="text-primary hover:underline font-mono text-xs"
                  >{{ detail.ingress_domain }}</a>
                  <span v-else class="text-muted-foreground">-</span>
                </div>
                <div class="flex justify-between items-center">
                  <span class="text-muted-foreground">OpenClaw 控制台</span>
                  <a
                    v-if="consoleUrl"
                    :href="consoleUrl"
                    target="_blank"
                    class="text-primary hover:underline font-mono text-xs truncate max-w-[220px]"
                  >打开控制台</a>
                  <Button
                    v-else-if="detail.ingress_domain"
                    variant="ghost"
                    size="sm"
                    class="h-6 text-xs px-2"
                    :disabled="syncingToken"
                    @click="handleSyncToken"
                  >
                    <RefreshCw v-if="syncingToken" class="w-3 h-3 mr-1 animate-spin" />
                    {{ syncingToken ? '获取中...' : '获取 Token' }}
                  </Button>
                  <span v-else class="text-muted-foreground">-</span>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle class="text-sm">资源配额</CardTitle></CardHeader>
              <CardContent class="text-sm space-y-2">
                <div class="flex justify-between"><span class="text-muted-foreground">CPU Request</span><span>{{ detail.cpu_request }}</span></div>
                <div class="flex justify-between"><span class="text-muted-foreground">CPU Limit</span><span>{{ detail.cpu_limit }}</span></div>
                <div class="flex justify-between"><span class="text-muted-foreground">内存 Request</span><span>{{ detail.mem_request }}</span></div>
                <div class="flex justify-between"><span class="text-muted-foreground">内存 Limit</span><span>{{ detail.mem_limit }}</span></div>
                <div class="flex justify-between"><span class="text-muted-foreground">存储类型</span><span class="font-mono">{{ detail.storage_class || '-' }}</span></div>
                <div class="flex justify-between"><span class="text-muted-foreground">存储大小</span><span class="font-mono">{{ detail.storage_size }}</span></div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <div class="flex items-center justify-between">
                  <CardTitle class="text-sm">环境变量</CardTitle>
                </div>
              </CardHeader>
              <CardContent>
                <div v-if="Object.keys(detail.env_vars || {}).length === 0" class="text-sm text-muted-foreground">无</div>
                <div v-else class="space-y-1">
                  <div
                    v-for="(val, key) in detail.env_vars"
                    :key="key"
                    class="group flex items-center gap-2 text-xs font-mono min-w-0 rounded px-1 -mx-1 hover:bg-muted/50 cursor-pointer"
                    @click="copyEnvVar(String(key), String(val))"
                  >
                    <span class="text-muted-foreground shrink-0">{{ key }}</span>
                    <span class="shrink-0">=</span>
                    <span class="truncate" :title="String(val)">{{ val }}</span>
                    <Copy class="w-3 h-3 text-muted-foreground opacity-0 group-hover:opacity-100 shrink-0 transition-opacity" />
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <!-- Pods Tab -->
        <TabsContent value="pods">
          <Card class="mt-4">
            <CardHeader><CardTitle>Pods</CardTitle></CardHeader>
            <CardContent>
              <div v-if="detail.pods.length === 0" class="text-muted-foreground text-sm py-4">暂无 Pod</div>
              <div v-else class="space-y-3">
                <div
                  v-for="pod in detail.pods"
                  :key="pod.name"
                  class="flex items-center justify-between rounded-md bg-muted/30 px-4 py-3"
                >
                  <div class="flex items-center gap-3">
                    <StatusDot :status="podStatusToDot(pod.status)" />
                    <div>
                      <div class="text-sm font-mono">{{ pod.name }}</div>
                      <div class="text-xs text-muted-foreground mt-0.5">
                        {{ pod.status }} · Node: {{ pod.node || '-' }} · IP: {{ pod.ip || '-' }}
                        · Restarts: {{ pod.restart_count }}
                      </div>
                    </div>
                  </div>
                  <div class="flex gap-2">
                    <Button variant="ghost" size="sm" @click="viewLogs(pod.name)">
                      <FileText class="w-3 h-3 mr-1" /> 日志
                    </Button>
                    <Button variant="ghost" size="sm" @click="router.push(`/instances/${instanceId}/logs`)">
                      实时日志
                    </Button>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <!-- Inline Logs Panel -->
          <Card v-if="showingLogs" class="mt-4">
            <CardHeader>
              <div class="flex items-center justify-between">
                <CardTitle>{{ selectedPod }} 日志</CardTitle>
                <Button variant="ghost" size="sm" @click="showingLogs = false">关闭</Button>
              </div>
            </CardHeader>
            <CardContent>
              <pre class="bg-black text-green-400 rounded-md p-4 text-xs font-mono overflow-auto max-h-[500px] whitespace-pre-wrap">{{ logsText }}</pre>
            </CardContent>
          </Card>
        </TabsContent>

        <!-- Config Tab -->
        <TabsContent value="config">
          <div class="mt-4 space-y-4">
            <!-- Pending config banner (two-step mode) -->
            <div
              v-if="detail.pending_config"
              class="flex items-center justify-between px-4 py-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20"
            >
              <div class="text-sm text-yellow-400">
                有待应用的配置变更（尚未同步到 K8s）
              </div>
              <Button
                size="sm"
                :disabled="applyingConfig"
                @click="showApplyConfirm = true"
              >
                {{ applyingConfig ? '应用中...' : '立即应用' }}
              </Button>
            </div>

            <Card>
              <CardHeader>
                <div class="flex items-center justify-between">
                  <CardTitle>当前配置</CardTitle>
                  <Button variant="outline" size="sm" @click="showUpdateDialog = true; fetchImageTags()">
                    <ArrowUpCircle class="w-4 h-4 mr-1" /> 修改配置
                  </Button>
                </div>
              </CardHeader>
              <CardContent class="text-sm space-y-3">
                <div class="grid grid-cols-2 gap-4">
                  <div class="flex items-center gap-2">
                    <Container class="w-4 h-4 text-muted-foreground" />
                    <span class="text-muted-foreground">镜像版本:</span>
                    <span class="font-medium">{{ detail.image_version }}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <Scale class="w-4 h-4 text-muted-foreground" />
                    <span class="text-muted-foreground">副本数:</span>
                    <span class="font-medium">{{ detail.replicas }}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <Cpu class="w-4 h-4 text-muted-foreground" />
                    <span class="text-muted-foreground">CPU:</span>
                    <span class="font-medium">{{ detail.cpu_request }} / {{ detail.cpu_limit }}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <MemoryStick class="w-4 h-4 text-muted-foreground" />
                    <span class="text-muted-foreground">内存:</span>
                    <span class="font-medium">{{ detail.mem_request }} / {{ detail.mem_limit }}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <HardDrive class="w-4 h-4 text-muted-foreground" />
                    <span class="text-muted-foreground">存储:</span>
                    <span class="font-medium">{{ detail.storage_size }}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <Globe class="w-4 h-4 text-muted-foreground" />
                    <span class="text-muted-foreground">服务类型:</span>
                    <span class="font-medium">{{ detail.service_type }}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <!-- LLM Config Tab -->
        <TabsContent value="llm">
          <div class="mt-4 space-y-4">
            <Card>
              <CardHeader><CardTitle>LLM 配置</CardTitle></CardHeader>
              <CardContent>
                <div v-if="llmConfigLoading" class="text-sm text-muted-foreground py-4 text-center">加载中...</div>
                <div v-else-if="llmConfigs.length === 0" class="text-sm text-muted-foreground py-4 text-center">
                  该实例未配置 LLM Key
                </div>
                <div v-else class="space-y-3">
                  <div v-for="cfg in llmConfigs" :key="cfg.provider" class="flex items-center justify-between p-3 rounded-lg border border-border">
                    <div class="flex items-center gap-3">
                      <Badge variant="outline">{{ cfg.provider }}</Badge>
                      <span class="text-sm">{{ cfg.key_source === 'org' ? '组织 Key' : '个人 Key' }}</span>
                      <span v-if="cfg.key_label" class="text-xs text-muted-foreground">({{ cfg.key_label }})</span>
                    </div>
                    <span v-if="cfg.api_key_masked" class="font-mono text-xs text-muted-foreground">{{ cfg.api_key_masked }}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <!-- Logs Tab (link to full page) -->
        <TabsContent value="logs">
          <div class="mt-4 text-center py-12">
            <FileText class="w-12 h-12 text-muted-foreground mx-auto mb-3" />
            <p class="text-muted-foreground mb-4">查看实时日志流</p>
            <Button @click="router.push(`/instances/${instanceId}/logs`)">
              打开日志页面
            </Button>
          </div>
        </TabsContent>

        <!-- Events Tab -->
        <TabsContent value="events">
          <Card class="mt-4">
            <CardHeader><CardTitle>实例事件</CardTitle></CardHeader>
            <CardContent>
              <div v-if="!detail.events || detail.events.length === 0" class="text-sm text-muted-foreground py-4">
                暂无事件
              </div>
              <div v-else class="space-y-2">
                <div
                  v-for="(ev, idx) in detail.events"
                  :key="idx"
                  class="flex items-start gap-3 rounded-md px-4 py-2"
                  :class="ev.type === 'Warning' ? 'bg-yellow-500/5 border-l-2 border-l-yellow-400' : 'bg-muted/30'"
                >
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center gap-2">
                      <Badge :variant="ev.type === 'Warning' ? 'destructive' : 'secondary'" class="text-xs">{{ ev.type }}</Badge>
                      <span class="text-sm font-medium">{{ ev.reason }}</span>
                    </div>
                    <p class="text-xs text-muted-foreground mt-1">{{ ev.message }}</p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <!-- History Tab -->
        <TabsContent value="history">
          <Card class="mt-4">
            <CardHeader><CardTitle>部署历史</CardTitle></CardHeader>
            <CardContent>
              <div v-if="history.length === 0" class="text-sm text-muted-foreground py-4">暂无部署记录</div>
              <div v-else class="relative">
                <!-- Timeline line -->
                <div class="absolute left-[11px] top-4 bottom-4 w-px bg-primary/30" />
                <div v-for="(rec, idx) in history" :key="rec.id" class="relative pl-8 pb-6">
                  <!-- Timeline dot -->
                  <div class="absolute left-0 top-1 w-6 h-6 rounded-full flex items-center justify-center"
                    :class="idx === 0 ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'"
                  >
                    <span class="text-[10px] font-bold">{{ rec.revision }}</span>
                  </div>
                  <div class="rounded-md border bg-card px-4 py-3">
                    <div class="flex items-center justify-between">
                      <div class="flex items-center gap-2">
                        <Badge v-if="idx === 0" variant="default" class="text-xs">当前</Badge>
                        <Badge variant="outline" class="text-xs">{{ rec.action }}</Badge>
                        <Badge :variant="rec.status === 'success' ? 'default' : rec.status === 'failed' ? 'destructive' : 'secondary'" class="text-xs">
                          {{ rec.status }}
                        </Badge>
                      </div>
                      <span class="text-xs text-muted-foreground">{{ formatTime(rec.started_at) }}</span>
                    </div>
                    <div class="mt-2 text-xs text-muted-foreground space-y-1">
                      <div v-if="rec.image_version">镜像: {{ rec.image_version }}</div>
                      <div v-if="rec.replicas">副本: {{ rec.replicas }}</div>
                      <div v-if="rec.message" class="text-red-400">{{ rec.message }}</div>
                    </div>
                    <div v-if="idx !== 0 && rec.config_snapshot" class="mt-2">
                      <Button variant="ghost" size="sm" class="text-xs h-7" @click="handleRollback(rec.revision)">
                        回滚到此版本
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </template>

    <!-- Scale Dialog -->
    <Dialog v-model:open="showScaleDialog">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>扩缩容</DialogTitle>
          <DialogDescription>调整实例副本数量</DialogDescription>
        </DialogHeader>
        <div class="py-4">
          <Label>副本数</Label>
          <div class="flex items-center gap-3 mt-2">
            <Button variant="outline" size="sm" :disabled="scaleReplicas <= 1" @click="scaleReplicas--">-</Button>
            <Input v-model.number="scaleReplicas" type="number" class="w-20 text-center" :min="1" :max="10" />
            <Button variant="outline" size="sm" :disabled="scaleReplicas >= 10" @click="scaleReplicas++">+</Button>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="showScaleDialog = false">取消</Button>
          <Button @click="handleScale">确认</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Restart Confirm -->
    <AlertDialog v-model:open="showRestartDialog">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>确认重启</AlertDialogTitle>
          <AlertDialogDescription>
            将触发 {{ detail?.name }} 的滚动重启，期间服务可能短暂中断。
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>取消</AlertDialogCancel>
          <AlertDialogAction @click="handleRestart">确认重启</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <!-- Delete Confirm -->
    <AlertDialog v-model:open="showDeleteDialog">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>删除实例</AlertDialogTitle>
          <AlertDialogDescription class="space-y-2">
            <p>此操作<strong class="text-destructive">不可撤销</strong>。将删除实例 <strong>{{ detail?.name }}</strong> 对应的整个命名空间 <code class="text-xs bg-muted px-1 py-0.5 rounded">{{ detail?.namespace }}</code> 及其下所有 K8s 资源，包括：</p>
            <ul class="text-xs list-disc list-inside text-muted-foreground">
              <li>Deployment、Service、Ingress（实例将完全不可访问）</li>
              <li>PVC 持久化存储（聊天记录、配置等数据将永久丢失）</li>
              <li>ConfigMap、Secret 等配置资源</li>
            </ul>
            <p>请输入实例名称 <strong>{{ detail?.name }}</strong> 以确认删除。</p>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <div class="py-2">
          <Input v-model="deleteConfirmName" placeholder="输入实例名称确认" />
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel @click="deleteConfirmName = ''">取消</AlertDialogCancel>
          <AlertDialogAction :disabled="!canDelete" class="bg-destructive text-destructive-foreground" @click="handleDelete">
            删除
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <!-- Rolling Update Dialog -->
    <Dialog v-model:open="showUpdateDialog">
      <DialogContent class="max-w-lg">
        <DialogHeader>
          <DialogTitle>滚动更新</DialogTitle>
          <DialogDescription>修改配置后将触发 Deployment 滚动更新</DialogDescription>
        </DialogHeader>
        <div class="space-y-4 py-4">
          <div>
            <div class="flex items-center gap-1.5">
              <Label>镜像版本</Label>
              <button
                class="inline-flex items-center justify-center w-5 h-5 rounded hover:bg-muted transition-colors"
                :class="{ 'animate-spin': loadingTags }"
                :disabled="loadingTags"
                title="刷新镜像版本列表"
                @click="fetchImageTags()"
              >
                <RefreshCw class="w-3.5 h-3.5 text-muted-foreground" />
              </button>
            </div>
            <Select v-if="imageTags.length > 0" v-model="updateForm.image_version" class="mt-1">
              <SelectTrigger class="w-full font-mono text-sm mt-1">
                <SelectValue placeholder="选择镜像版本" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="tag in imageTags" :key="tag" :value="tag">
                  {{ tag }}
                </SelectItem>
              </SelectContent>
            </Select>
            <Input v-else v-model="updateForm.image_version" class="mt-1" :placeholder="loadingTags ? '加载中...' : '手动输入版本号'" />
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <Label>CPU Request</Label>
              <Input v-model="updateForm.cpu_request" class="mt-1" placeholder="500m" />
            </div>
            <div>
              <Label>CPU Limit</Label>
              <Input v-model="updateForm.cpu_limit" class="mt-1" placeholder="2000m" />
            </div>
            <div>
              <Label>Memory Request</Label>
              <Input v-model="updateForm.mem_request" class="mt-1" placeholder="512Mi" />
            </div>
            <div>
              <Label>Memory Limit</Label>
              <Input v-model="updateForm.mem_limit" class="mt-1" placeholder="2Gi" />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="showUpdateDialog = false">取消</Button>
          <Button @click="handleUpdate">保存配置</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Apply Config Confirm -->
    <AlertDialog v-model:open="showApplyConfirm">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>应用配置变更</AlertDialogTitle>
          <AlertDialogDescription>
            将 pending 配置同步到 K8s 并触发滚动更新，期间服务可能短暂中断。
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>取消</AlertDialogCancel>
          <AlertDialogAction :disabled="applyingConfig" @click="handleApply">
            {{ applyingConfig ? '应用中...' : '确认应用' }}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
</template>
