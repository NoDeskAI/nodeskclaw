<script setup lang="ts">
import { ref, onMounted, inject, type ComputedRef } from 'vue'
import {
  Loader2,
  CheckCircle,
  XCircle,
  Trash2,
  Sparkles,
  Layers,
  Brain,
  ChevronDown,
  ChevronUp,
  History,
} from 'lucide-vue-next'
import { useGeneStore } from '@/stores/gene'
import type { EvolutionEventItem } from '@/stores/gene'

const instanceId = inject<ComputedRef<string>>('instanceId')!
const store = useGeneStore()

const events = ref<EvolutionEventItem[]>([])
const loading = ref(true)
const page = ref(1)
const hasMore = ref(true)
const loadingMore = ref(false)
const expandedIds = ref<Set<string>>(new Set())

const eventConfig: Record<string, { icon: typeof CheckCircle; color: string; label: string }> = {
  learned: { icon: CheckCircle, color: 'text-green-500', label: '学习成功' },
  forgotten: { icon: Trash2, color: 'text-amber-500', label: '已遗忘' },
  simplified: { icon: Brain, color: 'text-blue-500', label: '已简化' },
  learn_failed: { icon: XCircle, color: 'text-red-500', label: '学习失败' },
  forget_failed: { icon: XCircle, color: 'text-red-500', label: '遗忘失败' },
  variant_published: { icon: Sparkles, color: 'text-purple-500', label: '变体发布' },
  genome_applied: { icon: Layers, color: 'text-indigo-500', label: '基因组应用' },
}

function getConfig(type: string) {
  return eventConfig[type] ?? { icon: History, color: 'text-muted-foreground', label: type }
}

function toggleExpand(id: string) {
  if (expandedIds.value.has(id)) {
    expandedIds.value.delete(id)
  } else {
    expandedIds.value.add(id)
  }
}

function hasExpandableDetails(ev: EvolutionEventItem): boolean {
  if (!ev.details) return false
  return !!(ev.details.forgetting_summary || ev.details.simplified_reason || ev.details.reason)
}

function formatTime(dateStr?: string): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function loadEvents() {
  loading.value = true
  try {
    const data = await store.fetchEvolutionLog(instanceId.value, 1, 20)
    events.value = data
    hasMore.value = data.length === 20
    page.value = 1
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  loadingMore.value = true
  try {
    const next = page.value + 1
    const data = await store.fetchEvolutionLog(instanceId.value, next, 20)
    events.value.push(...data)
    hasMore.value = data.length === 20
    page.value = next
  } finally {
    loadingMore.value = false
  }
}

onMounted(loadEvents)
</script>

<template>
  <div class="space-y-6">
    <h2 class="text-lg font-semibold">进化日志</h2>

    <div v-if="loading" class="flex items-center justify-center py-16">
      <Loader2 class="w-8 h-8 animate-spin text-muted-foreground" />
    </div>

    <div v-else-if="events.length === 0" class="rounded-xl border border-dashed border-border py-16 text-center text-muted-foreground">
      <History class="w-12 h-12 mx-auto mb-4 opacity-50" />
      <p class="text-sm">暂无进化事件</p>
    </div>

    <div v-else class="relative">
      <div class="absolute left-[19px] top-0 bottom-0 w-px bg-border" />

      <div
        v-for="ev in events"
        :key="ev.id"
        class="relative flex gap-4 pb-6"
      >
        <div
          class="shrink-0 w-10 h-10 rounded-full border-2 border-background bg-card flex items-center justify-center z-10"
          :class="getConfig(ev.event_type).color"
        >
          <component :is="getConfig(ev.event_type).icon" class="w-4 h-4" />
        </div>

        <div class="flex-1 min-w-0 pt-1">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="text-sm font-medium" :class="getConfig(ev.event_type).color">
              {{ getConfig(ev.event_type).label }}
            </span>
            <span class="text-sm">{{ ev.gene_name }}</span>
            <span v-if="ev.gene_slug" class="text-xs text-muted-foreground">{{ ev.gene_slug }}</span>
            <span class="text-xs text-muted-foreground ml-auto shrink-0">{{ formatTime(ev.created_at) }}</span>
          </div>

          <div v-if="ev.details?.method" class="text-xs text-muted-foreground mt-1">
            {{ ev.details.method === 'deep' ? '深度遗忘' : '直接操作' }}
            <template v-if="ev.details.usage_count != null">
              -- 使用 {{ ev.details.usage_count }} 次
            </template>
          </div>

          <div v-if="hasExpandableDetails(ev)" class="mt-2">
            <button
              class="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
              @click="toggleExpand(ev.id)"
            >
              <component :is="expandedIds.has(ev.id) ? ChevronUp : ChevronDown" class="w-3 h-3" />
              {{ expandedIds.has(ev.id) ? '收起' : '查看详情' }}
            </button>
            <div v-if="expandedIds.has(ev.id)" class="mt-2 p-3 rounded-lg bg-muted/30 border border-border text-sm text-muted-foreground whitespace-pre-wrap">
              {{ ev.details?.forgetting_summary || ev.details?.simplified_reason || ev.details?.reason }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="hasMore && !loading" class="text-center">
      <button
        class="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm border border-border hover:bg-muted/50 transition-colors"
        :disabled="loadingMore"
        @click="loadMore"
      >
        <Loader2 v-if="loadingMore" class="w-4 h-4 animate-spin" />
        加载更多
      </button>
    </div>
  </div>
</template>
