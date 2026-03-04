<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, inject, type Ref, type ComputedRef } from 'vue'
import { useRouter } from 'vue-router'
import {
  ExternalLink, RefreshCw, Trash2, Circle, Loader2, Copy, Check, RotateCcw, AlertTriangle,
  Package, Zap, FileText,
} from 'lucide-vue-next'
import api from '@/services/api'
import { useToast } from '@/composables/useToast'
import type { InstanceSkillItem, InstanceGeneItem, GenomeItem } from '@/stores/gene'

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
  workspace_id: string | null
  workspace_name: string | null
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

const skills = ref<InstanceSkillItem[]>([])
const instanceGenes = ref<InstanceGeneItem[]>([])
const appliedGenomes = ref<GenomeItem[]>([])
const genesLoading = ref(false)

const geneStatusClass: Record<string, string> = {
  installed: 'bg-green-500/10 text-green-500',
  learning: 'bg-yellow-500/10 text-yellow-500',
  learn_failed: 'bg-red-500/10 text-red-500',
  failed: 'bg-red-500/10 text-red-500',
  installing: 'bg-blue-500/10 text-blue-500',
  uninstalling: 'bg-gray-500/10 text-gray-500',
  forgetting: 'bg-amber-500/10 text-amber-500',
  forget_failed: 'bg-red-500/10 text-red-500',
  simplified: 'bg-blue-500/10 text-blue-500',
}

function getStatusClass(status: string): string {
  return geneStatusClass[status] ?? 'bg-gray-500/10 text-gray-500'
}

const statusLabels: Record<string, string> = {
  installed: '已学习',
  learning: '学习中',
  learn_failed: '学习失败',
  failed: '失败',
  installing: '学习中',
  uninstalling: '遗忘中',
  forgetting: '深度遗忘中',
  forget_failed: '遗忘失败',
  simplified: '已简化',
}

function getStatusLabel(status: string): string {
  return statusLabels[status] ?? status
}

function effectivenessScore(item: InstanceSkillItem): number {
  if (item.instance_gene?.agent_self_eval != null) return item.instance_gene.agent_self_eval
  return item.gene?.effectiveness_score ?? 0
}

let pollTimer: ReturnType<typeof setInterval> | null = null
let pollTimeout: ReturnType<typeof setTimeout> | null = null

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
  fetchGenes()
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

async function fetchGenes() {
  genesLoading.value = true
  try {
    const [skillsRes, genesRes] = await Promise.all([
      api.get(`/instances/${instanceId.value}/skills`),
      api.get(`/instances/${instanceId.value}/genes`),
    ])
    skills.value = skillsRes.data.data || []
    instanceGenes.value = genesRes.data.data || []

    const genomeIds = [...new Set(
      instanceGenes.value
        .map((g: InstanceGeneItem) => g.genome_id)
        .filter((id): id is string => !!id),
    )]
    if (genomeIds.length > 0) {
      const genomeResults = await Promise.all(
        genomeIds.map(id => api.get(`/genomes/${id}`).catch(() => null)),
      )
      appliedGenomes.value = genomeResults
        .filter(r => r?.data?.data)
        .map(r => r!.data.data)
    } else {
      appliedGenomes.value = []
    }
  } catch {
    skills.value = []
    instanceGenes.value = []
    appliedGenomes.value = []
  } finally {
    genesLoading.value = false
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
            <p class="text-sm font-medium">DeskClaw 访问地址</p>
            <p class="text-xs text-muted-foreground mt-0.5">
              {{ restarting ? '实例正在重启，请稍候...' : '点击即可打开 AI 员工' }}
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

      <!-- 已安装基因 -->
      <div class="p-4 rounded-xl border border-border bg-card">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-sm font-medium">已安装基因</h2>
          <router-link
            v-if="skills.length"
            :to="`/instances/${instanceId}/genes`"
            class="text-xs text-primary hover:text-primary/80 transition-colors"
          >查看全部</router-link>
        </div>
        <div v-if="genesLoading" class="flex items-center justify-center py-8">
          <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
        <div v-else-if="skills.length === 0" class="py-8 text-center">
          <Package class="w-8 h-8 mx-auto mb-2 text-muted-foreground/50" />
          <p class="text-sm text-muted-foreground">暂无基因</p>
        </div>
        <div v-else class="space-y-3">
          <div
            v-for="item in skills"
            :key="item.skill_name"
            class="rounded-lg border border-border p-3 hover:border-primary/30 transition-colors"
          >
            <div v-if="item.type === 'hub'" class="space-y-2">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-medium text-sm">{{ item.gene?.name ?? item.name }}</span>
                <span class="text-xs text-muted-foreground">{{ item.gene?.slug ?? item.skill_name }}</span>
                <span v-if="item.instance_gene?.installed_version || item.gene?.version" class="text-xs text-muted-foreground">
                  v{{ item.instance_gene?.installed_version ?? item.gene?.version ?? '-' }}
                </span>
                <span
                  v-if="item.instance_gene"
                  class="px-2 py-0.5 rounded text-xs font-medium"
                  :class="getStatusClass(item.instance_gene.status)"
                >{{ getStatusLabel(item.instance_gene.status) }}</span>
                <span v-else class="px-2 py-0.5 rounded text-xs font-medium bg-green-500/10 text-green-500">
                  已学习
                </span>
              </div>
              <div v-if="item.gene?.tags?.length" class="flex flex-wrap gap-1">
                <span
                  v-for="tag in item.gene.tags"
                  :key="tag"
                  class="px-2 py-0.5 rounded bg-muted text-xs text-muted-foreground"
                >{{ tag }}</span>
              </div>
              <div class="flex items-center gap-4">
                <div class="flex-1 max-w-[200px]">
                  <div class="flex justify-between text-xs text-muted-foreground mb-1">
                    <span>效能</span>
                    <span>{{ Math.round(effectivenessScore(item) * 100) }}%</span>
                  </div>
                  <div class="h-1.5 rounded-full bg-muted overflow-hidden">
                    <div
                      class="h-full rounded-full bg-primary transition-all"
                      :style="{ width: `${Math.min(100, effectivenessScore(item) * 100)}%` }"
                    />
                  </div>
                </div>
                <span v-if="item.instance_gene" class="text-xs text-muted-foreground">
                  使用 {{ item.instance_gene.usage_count }} 次
                </span>
              </div>
            </div>
            <div v-else class="space-y-1.5">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-medium text-sm">{{ item.name }}</span>
                <span class="text-xs text-muted-foreground">{{ item.skill_name }}</span>
                <span class="px-2 py-0.5 rounded text-xs font-medium bg-violet-500/10 text-violet-500">
                  <Zap class="w-3 h-3 inline -mt-0.5 mr-0.5" />基因涌现
                </span>
              </div>
              <p v-if="item.description" class="text-sm text-muted-foreground line-clamp-2">{{ item.description }}</p>
              <div class="flex items-center gap-3 text-xs text-muted-foreground">
                <span class="inline-flex items-center gap-1">
                  <FileText class="w-3.5 h-3.5" />
                  {{ item.file_count }} 个文件
                </span>
                <span v-if="item.frontmatter?.always" class="inline-flex items-center gap-1 text-amber-500">
                  <Zap class="w-3.5 h-3.5" />
                  常驻激活
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 已应用基因组 -->
      <div v-if="appliedGenomes.length" class="p-4 rounded-xl border border-border bg-card">
        <h2 class="text-sm font-medium mb-3">已应用基因组</h2>
        <div class="space-y-2">
          <div
            v-for="genome in appliedGenomes"
            :key="genome.id"
            class="flex items-center justify-between p-3 rounded-lg border border-border hover:border-primary/30 transition-colors"
          >
            <div class="min-w-0">
              <span class="font-medium text-sm">{{ genome.name }}</span>
              <p v-if="genome.short_description" class="text-xs text-muted-foreground mt-0.5 truncate">{{ genome.short_description }}</p>
            </div>
            <span class="text-xs text-muted-foreground shrink-0 ml-3">{{ genome.gene_slugs.length }} 个基因</span>
          </div>
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
            <div v-if="instance?.workspace_id" class="text-sm text-muted-foreground space-y-2">
              <p>该实例当前已加入工作区「<span class="text-foreground font-medium">{{ instance.workspace_name }}</span>」，无法直接删除。</p>
              <p class="text-xs">请先在工作区中将此 Agent 移除，然后再执行删除操作。</p>
            </div>
            <div v-else class="text-sm text-muted-foreground space-y-2">
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
                {{ instance?.workspace_id ? '知道了' : '取消' }}
              </button>
              <button
                v-if="!instance?.workspace_id"
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
