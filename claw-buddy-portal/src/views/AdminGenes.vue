<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Loader2, Dna, Download, TrendingUp, AlertCircle, Sparkles, Check, X, Activity } from 'lucide-vue-next'
import { useGeneStore } from '@/stores/gene'
import type { GeneItem } from '@/stores/gene'
import { useToast } from '@/composables/useToast'

const store = useGeneStore()
const toast = useToast()

const stats = ref(store.geneStats)
const hotGenes = ref<GeneItem[]>([])
const activity = ref<{ id: string; gene_slug: string; gene_name: string; metric_type: string; value: number; created_at?: string }[]>([])
const pendingGenes = ref<GeneItem[]>([])
const loading = ref(true)
const activityLoading = ref(false)
const pendingLoading = ref(false)
const reviewingId = ref<string | null>(null)

async function loadStats() {
  await store.fetchGeneStats()
  stats.value = store.geneStats
}

async function loadHotGenes() {
  await store.fetchGenes({ sort: 'effectiveness', page_size: 10 })
  hotGenes.value = [...store.genes]
}

async function loadActivity() {
  activityLoading.value = true
  try {
    const data = await store.fetchGeneActivity(50)
    activity.value = data as typeof activity.value
  } finally {
    activityLoading.value = false
  }
}

async function loadPending() {
  pendingLoading.value = true
  try {
    const data = await store.fetchPendingReviewGenes()
    pendingGenes.value = (data as GeneItem[]) ?? []
  } finally {
    pendingLoading.value = false
  }
}

async function handleReview(geneId: string, action: 'approve' | 'reject') {
  reviewingId.value = geneId
  try {
    await store.reviewGene(geneId, action)
    pendingGenes.value = pendingGenes.value.filter((g) => g.id !== geneId)
    toast.success(action === 'approve' ? '已通过' : '已拒绝')
  } catch (e) {
    toast.error('操作失败')
  } finally {
    reviewingId.value = null
  }
}

function formatMetricType(t: string): string {
  const map: Record<string, string> = {
    user_positive: '用户正向',
    user_negative: '用户负向',
    task_success: '任务成功',
    agent_self_eval: 'Agent 自评',
  }
  return map[t] ?? t
}

function formatDate(s?: string): string {
  if (!s) return '-'
  const d = new Date(s)
  return d.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([loadStats(), loadHotGenes()])
  } finally {
    loading.value = false
  }
  loadActivity()
  loadPending()
})
</script>

<template>
  <div class="min-h-screen bg-background">
    <div class="max-w-6xl mx-auto px-6 py-8">
      <h1 class="text-2xl font-bold mb-6">基因运营</h1>

      <div v-if="loading" class="flex items-center justify-center py-24">
        <Loader2 class="w-8 h-8 animate-spin text-muted-foreground" />
      </div>

      <template v-else>
        <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
          <div class="rounded-xl border border-border bg-card p-4">
            <div class="flex items-center gap-2 text-muted-foreground mb-1">
              <Dna class="w-4 h-4" />
              <span class="text-sm">基因总数</span>
            </div>
            <div class="text-2xl font-bold">{{ stats?.total_genes ?? 0 }}</div>
          </div>
          <div class="rounded-xl border border-border bg-card p-4">
            <div class="flex items-center gap-2 text-muted-foreground mb-1">
              <Download class="w-4 h-4" />
              <span class="text-sm">总安装数</span>
            </div>
            <div class="text-2xl font-bold">{{ stats?.total_installs ?? 0 }}</div>
          </div>
          <div class="rounded-xl border border-border bg-card p-4">
            <div class="flex items-center gap-2 text-muted-foreground mb-1">
              <TrendingUp class="w-4 h-4" />
              <span class="text-sm">学习中</span>
            </div>
            <div class="text-2xl font-bold">{{ stats?.learning_count ?? 0 }}</div>
          </div>
          <div class="rounded-xl border border-border bg-card p-4">
            <div class="flex items-center gap-2 text-muted-foreground mb-1">
              <AlertCircle class="w-4 h-4" />
              <span class="text-sm">失败数</span>
            </div>
            <div class="text-2xl font-bold">{{ stats?.failed_count ?? 0 }}</div>
          </div>
          <div class="rounded-xl border border-border bg-card p-4">
            <div class="flex items-center gap-2 text-muted-foreground mb-1">
              <Sparkles class="w-4 h-4" />
              <span class="text-sm">Agent 创造</span>
            </div>
            <div class="text-2xl font-bold">{{ stats?.agent_created_count ?? 0 }}</div>
          </div>
        </div>

        <div class="grid md:grid-cols-2 gap-6 mb-8">
          <div class="rounded-xl border border-border bg-card overflow-hidden">
            <div class="px-4 py-3 border-b border-border">
              <h2 class="font-semibold">热门基因 (按效能)</h2>
            </div>
            <div class="divide-y divide-border max-h-[320px] overflow-y-auto">
              <div
                v-for="(g, i) in hotGenes"
                :key="g.id"
                class="px-4 py-3 flex items-center justify-between gap-4"
              >
                <span class="text-muted-foreground w-6">{{ i + 1 }}</span>
                <div class="min-w-0 flex-1">
                  <div class="font-medium truncate">{{ g.name }}</div>
                  <div class="text-xs text-muted-foreground">{{ g.slug }}</div>
                </div>
                <div class="shrink-0">
                  <div class="text-sm font-medium">{{ Math.round((g.effectiveness_score ?? 0) * 100) }}%</div>
                  <div class="w-16 h-1.5 rounded-full bg-muted overflow-hidden">
                    <div
                      class="h-full rounded-full bg-primary"
                      :style="{ width: `${Math.min(100, (g.effectiveness_score ?? 0) * 100)}%` }"
                    />
                  </div>
                </div>
              </div>
              <div v-if="hotGenes.length === 0" class="px-4 py-8 text-center text-muted-foreground text-sm">
                暂无数据
              </div>
            </div>
          </div>

          <div class="rounded-xl border border-border bg-card overflow-hidden">
            <div class="px-4 py-3 border-b border-border flex items-center gap-2">
              <Activity class="w-4 h-4" />
              <h2 class="font-semibold">活动流</h2>
            </div>
            <div class="divide-y divide-border max-h-[320px] overflow-y-auto">
              <div v-if="activityLoading" class="px-4 py-8 flex justify-center">
                <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
              </div>
              <div
                v-else
                v-for="a in activity"
                :key="a.id"
                class="px-4 py-2.5 text-sm"
              >
                <span class="font-medium">{{ a.gene_name }}</span>
                <span class="text-muted-foreground mx-1">{{ formatMetricType(a.metric_type) }}</span>
                <span class="text-muted-foreground">{{ formatDate(a.created_at) }}</span>
              </div>
              <div v-if="!activityLoading && activity.length === 0" class="px-4 py-8 text-center text-muted-foreground text-sm">
                暂无活动
              </div>
            </div>
          </div>
        </div>

        <div class="rounded-xl border border-border bg-card overflow-hidden">
          <div class="px-4 py-3 border-b border-border">
            <h2 class="font-semibold">待审核</h2>
          </div>
          <div v-if="pendingLoading" class="px-4 py-8 flex justify-center">
            <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
          <div v-else-if="pendingGenes.length === 0" class="px-4 py-8 text-center text-muted-foreground text-sm">
            暂无待审核基因
          </div>
          <div v-else class="divide-y divide-border">
            <div
              v-for="g in pendingGenes"
              :key="g.id"
              class="px-4 py-3 flex items-center justify-between gap-4"
            >
              <div class="min-w-0 flex-1">
                <div class="font-medium">{{ g.name }}</div>
                <div class="text-sm text-muted-foreground">{{ g.slug }} · {{ g.review_status }}</div>
              </div>
              <div class="flex items-center gap-2 shrink-0">
                <button
                  class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm bg-green-500/10 text-green-600 hover:bg-green-500/20 disabled:opacity-50"
                  :disabled="reviewingId === g.id"
                  @click="handleReview(g.id, 'approve')"
                >
                  <Loader2 v-if="reviewingId === g.id" class="w-4 h-4 animate-spin" />
                  <Check v-else class="w-4 h-4" />
                  通过
                </button>
                <button
                  class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm bg-red-500/10 text-red-600 hover:bg-red-500/20 disabled:opacity-50"
                  :disabled="reviewingId === g.id"
                  @click="handleReview(g.id, 'reject')"
                >
                  <X class="w-4 h-4" />
                  拒绝
                </button>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
