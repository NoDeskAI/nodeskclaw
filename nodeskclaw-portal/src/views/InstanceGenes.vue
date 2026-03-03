<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, inject, type ComputedRef } from 'vue'
import { useRoute } from 'vue-router'
import { Loader2, Package, Download, Trash2, Upload, Sparkles, X, AlertTriangle, RefreshCw } from 'lucide-vue-next'
import { useGeneStore } from '@/stores/gene'
import type { InstanceGeneItem } from '@/stores/gene'
import { useToast } from '@/composables/useToast'
import GeneMarketDialog from '@/components/gene/GeneMarketDialog.vue'
import api from '@/services/api'

const route = useRoute()
const toast = useToast()
const instanceId = inject<ComputedRef<string>>('instanceId')!
const store = useGeneStore()

const initialLoading = ref(true)
const instanceGenes = computed(() => store.instanceGenes)
const marketDialogOpen = ref(false)
const focusGeneId = computed(() => {
  const value = route.query.focus_gene_id
  return typeof value === 'string' ? value : ''
})
const displayedInstanceGenes = computed(() => {
  const list = instanceGenes.value
  const targetGeneId = focusGeneId.value
  if (!targetGeneId) return list
  const targetItem = list.find(item => item.gene_id === targetGeneId)
  if (!targetItem) return list
  if (list[0]?.id === targetItem.id) return list
  return [targetItem, ...list.filter(item => item.id !== targetItem.id)]
})
const createDialogOpen = ref(false)
const createPrompt = ref('')
const creating = ref(false)

const forgetTarget = ref<InstanceGeneItem | null>(null)
const confirmInput = ref('')
const forgetting = ref(false)

const isConfirmed = computed(() => {
  if (!forgetTarget.value?.gene?.name) return false
  return confirmInput.value === forgetTarget.value.gene.name
})

const statusBadgeClass: Record<string, string> = {
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

function getStatusClass(status: string): string {
  return statusBadgeClass[status] ?? 'bg-gray-500/10 text-gray-500'
}

function getStatusLabel(status: string): string {
  return statusLabels[status] ?? status
}

function effectivenessScore(item: InstanceGeneItem): number {
  if (item.agent_self_eval != null) return item.agent_self_eval
  return item.gene?.effectiveness_score ?? 0
}

const busyStatuses = new Set(['uninstalling', 'forgetting', 'installing', 'learning'])

const TRANSITIONAL_STATUSES = new Set(['learning', 'installing', 'forgetting', 'uninstalling'])
const hasTransitionalGenes = computed(() =>
  instanceGenes.value.some(g => TRANSITIONAL_STATUSES.has(g.status)),
)

let pollTimer: ReturnType<typeof setInterval> | null = null

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const res = await api.get(`/instances/${instanceId.value}/genes`)
      store.instanceGenes = res.data.data || []
    } catch { /* ignore */ }
    if (!hasTransitionalGenes.value) stopPolling()
  }, 5000)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

watch(hasTransitionalGenes, (has) => {
  if (has) startPolling()
  else stopPolling()
})

function openMarketDialog() {
  marketDialogOpen.value = true
}

async function onGeneInstalled() {
  await store.fetchInstanceGenes(instanceId.value)
}

function openForgetDialog(item: InstanceGeneItem) {
  forgetTarget.value = item
  confirmInput.value = ''
}

async function confirmForget() {
  if (!forgetTarget.value || !isConfirmed.value) return
  forgetting.value = true
  try {
    await store.uninstallGene(instanceId.value, forgetTarget.value.gene_id)
    forgetTarget.value = null
    await store.fetchInstanceGenes(instanceId.value)
    toast.success('已提交遗忘')
  } catch (e) {
    toast.error('遗忘失败')
  } finally {
    forgetting.value = false
  }
}

async function handleRelearn(item: InstanceGeneItem) {
  if (!item.gene?.slug) return
  try {
    await store.installGene(instanceId.value, item.gene.slug)
    await store.fetchInstanceGenes(instanceId.value)
    toast.success('已提交重新学习')
  } catch (e) {
    toast.error('重新学习失败')
  }
}

async function handlePublishVariant(item: InstanceGeneItem) {
  try {
    await store.publishVariant(instanceId.value, item.gene_id)
    await store.fetchInstanceGenes(instanceId.value)
    toast.success('变体已发布')
  } catch (e) {
    toast.error('发布失败')
  }
}

function openCreateDialog() {
  createDialogOpen.value = true
  createPrompt.value = ''
}

async function handleCreate() {
  creating.value = true
  try {
    await store.triggerCreation(instanceId.value, createPrompt.value || undefined)
    createDialogOpen.value = false
    await store.fetchInstanceGenes(instanceId.value)
    toast.success('已提交创造任务')
  } catch (e) {
    toast.error('提交失败')
  } finally {
    creating.value = false
  }
}

onMounted(async () => {
  await store.fetchInstanceGenes(instanceId.value)
  initialLoading.value = false
})

onUnmounted(stopPolling)
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <h2 class="text-lg font-semibold">基因管理</h2>
      <div class="flex items-center gap-2">
        <button
          class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
          @click="openMarketDialog"
        >
          <Download class="w-4 h-4" />
          学习基因
        </button>
        <button
          class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm border border-border hover:bg-muted/50 transition-colors"
          @click="openCreateDialog"
        >
          <Sparkles class="w-4 h-4" />
          创造基因
        </button>
      </div>
    </div>

    <div v-if="initialLoading" class="flex items-center justify-center py-16">
      <Loader2 class="w-8 h-8 animate-spin text-muted-foreground" />
    </div>

    <div v-else-if="instanceGenes.length === 0" class="rounded-xl border border-dashed border-border py-16 text-center text-muted-foreground">
      <Package class="w-12 h-12 mx-auto mb-4 opacity-50" />
      <p class="text-sm">暂无已学习基因</p>
      <button
        class="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
        @click="openMarketDialog"
      >
        <Download class="w-4 h-4" />
        学习基因
      </button>
    </div>

    <div v-else class="space-y-3">
      <div
        v-for="item in displayedInstanceGenes"
        :key="item.id"
        class="rounded-xl border border-border bg-card p-4 hover:border-primary/30 transition-colors"
      >
        <div class="flex items-start justify-between gap-4">
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-medium">{{ item.gene?.name ?? '未知基因' }}</span>
              <span class="text-xs text-muted-foreground">{{ item.gene?.slug }}</span>
              <span class="text-xs text-muted-foreground">v{{ item.installed_version ?? item.gene?.version ?? '-' }}</span>
              <span
                class="px-2 py-0.5 rounded text-xs font-medium"
                :class="getStatusClass(item.status)"
              >
                {{ getStatusLabel(item.status) }}
              </span>
            </div>
            <div v-if="item.gene?.tags?.length" class="flex flex-wrap gap-1 mt-2">
              <span
                v-for="tag in item.gene.tags"
                :key="tag"
                class="px-2 py-0.5 rounded bg-muted text-xs text-muted-foreground"
              >
                {{ tag }}
              </span>
            </div>
            <div class="mt-3 flex items-center gap-4">
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
              <span class="text-sm text-muted-foreground">使用 {{ item.usage_count }} 次</span>
            </div>
          </div>
          <div class="flex items-center gap-2 shrink-0">
            <button
              v-if="item.learning_output && !item.variant_published && item.status === 'installed'"
              class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs border border-border hover:bg-muted/50 transition-colors"
              @click="handlePublishVariant(item)"
            >
              <Upload class="w-3.5 h-3.5" />
              发布变体
            </button>
            <button
              v-if="item.status === 'simplified'"
              class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs border border-border hover:bg-muted/50 transition-colors"
              @click="handleRelearn(item)"
            >
              <RefreshCw class="w-3.5 h-3.5" />
              恢复学习
            </button>
            <button
              v-if="!busyStatuses.has(item.status)"
              class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs text-destructive border border-destructive/30 hover:bg-destructive/10 transition-colors"
              @click="openForgetDialog(item)"
            >
              <Trash2 class="w-3.5 h-3.5" />
              {{ item.status === 'simplified' ? '完全遗忘' : '遗忘' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Forgetting Ceremony Dialog -->
    <div
      v-if="forgetTarget"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      @click.self="forgetTarget = null"
    >
      <div class="bg-card rounded-xl border border-border shadow-xl w-full max-w-md mx-4 p-6">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-semibold">遗忘确认</h3>
          <button class="text-muted-foreground hover:text-foreground" @click="forgetTarget = null">
            <X class="w-5 h-5" />
          </button>
        </div>

        <div class="rounded-lg border border-border bg-muted/30 p-3 mb-4">
          <div class="flex items-center gap-2 mb-1">
            <span class="font-medium text-sm">{{ forgetTarget.gene?.name ?? '未知基因' }}</span>
            <span class="text-xs text-muted-foreground">{{ forgetTarget.gene?.slug }}</span>
          </div>
          <p v-if="forgetTarget.gene?.short_description || forgetTarget.gene?.description" class="text-xs text-muted-foreground line-clamp-2">
            {{ forgetTarget.gene?.short_description || forgetTarget.gene?.description }}
          </p>
        </div>

        <div class="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 mb-4">
          <div class="flex items-start gap-2">
            <AlertTriangle class="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
            <div class="text-xs text-muted-foreground space-y-1">
              <p>Agent 将进入深度遗忘，回顾使用经验并产出遗忘总结。Agent 可能选择完全遗忘或简化保留核心认知。</p>
              <p>遗忘完成后实例将自动重启。</p>
              <p>此操作不可撤销，但可以重新学习。</p>
            </div>
          </div>
        </div>

        <div class="mb-4">
          <label class="block text-sm text-muted-foreground mb-2">
            请输入基因名称
            <span class="font-medium text-foreground">{{ forgetTarget.gene?.name }}</span>
            以确认遗忘
          </label>
          <input
            v-model="confirmInput"
            class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-destructive/50"
            :placeholder="forgetTarget.gene?.name"
          />
        </div>

        <div class="flex justify-end gap-2">
          <button
            class="px-4 py-2 rounded-lg text-sm border border-border hover:bg-muted/50"
            @click="forgetTarget = null"
          >
            取消
          </button>
          <button
            class="px-4 py-2 rounded-lg text-sm bg-destructive text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50"
            :disabled="!isConfirmed || forgetting"
            @click="confirmForget"
          >
            <Loader2 v-if="forgetting" class="w-4 h-4 animate-spin inline mr-1" />
            确认遗忘
          </button>
        </div>
      </div>
    </div>

    <div
      v-if="createDialogOpen"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      @click.self="createDialogOpen = false"
    >
      <div class="bg-card rounded-xl border border-border shadow-xl w-full max-w-md mx-4 p-6">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-semibold">创造基因</h3>
          <button class="text-muted-foreground hover:text-foreground" @click="createDialogOpen = false">
            <X class="w-5 h-5" />
          </button>
        </div>
        <p class="text-sm text-muted-foreground mb-4">描述你希望创造的基因能力，AI 将尝试学习并生成新基因。</p>
        <textarea
          v-model="createPrompt"
          class="w-full h-24 px-3 py-2 rounded-lg border border-border bg-background text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary"
          placeholder="例如：能够根据用户需求自动生成 SQL 查询..."
        />
        <div class="flex justify-end gap-2 mt-4">
          <button
            class="px-4 py-2 rounded-lg text-sm border border-border hover:bg-muted/50"
            @click="createDialogOpen = false"
          >
            取消
          </button>
          <button
            class="px-4 py-2 rounded-lg text-sm bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            :disabled="creating"
            @click="handleCreate"
          >
            <Loader2 v-if="creating" class="w-4 h-4 animate-spin inline mr-1" />
            提交
          </button>
        </div>
      </div>
    </div>

    <GeneMarketDialog
      v-model="marketDialogOpen"
      :instance-id="instanceId"
      @installed="onGeneInstalled"
    />
  </div>
</template>
