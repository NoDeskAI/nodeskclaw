<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Plus, Loader2, Server, RefreshCw } from 'lucide-vue-next'
import api from '@/services/api'
import { resolveApiErrorMessage } from '@/i18n/error'

interface InstanceInfo {
  id: string
  name: string
  cluster_id: string
  namespace: string
  image_version: string
  replicas: number
  available_replicas: number
  status: string
  service_type: string
  ingress_domain: string | null
  created_by: string
  created_at: string
  updated_at: string
}

const router = useRouter()
const { t, locale } = useI18n()
const loading = ref(true)
const instances = ref<InstanceInfo[]>([])
const error = ref('')

const statusConfig: Record<string, { color: string; bg: string }> = {
  running: { color: 'text-emerald-400', bg: 'bg-emerald-400' },
  learning: { color: 'text-blue-400', bg: 'bg-blue-400' },
  creating: { color: 'text-blue-400', bg: 'bg-blue-400' },
  pending: { color: 'text-yellow-400', bg: 'bg-yellow-400' },
  deploying: { color: 'text-blue-400', bg: 'bg-blue-400' },
  updating: { color: 'text-amber-400', bg: 'bg-amber-400' },
  failed: { color: 'text-red-400', bg: 'bg-red-400' },
  deleting: { color: 'text-gray-400', bg: 'bg-gray-400' },
}

const animatingStatuses = new Set(['creating', 'pending', 'deploying', 'updating', 'deleting', 'learning'])

function getStatus(status: string) {
  return statusConfig[status] ?? { color: 'text-gray-400', bg: 'bg-gray-400' }
}

function getStatusLabel(status: string) {
  const key = `status.${status}`
  const translated = t(key)
  return translated === key ? status : translated
}

const sortedInstances = computed(() =>
  [...instances.value].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  ),
)

async function fetchInstances() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/instances')
    instances.value = data.data ?? []
  } catch (e: unknown) {
    error.value = resolveApiErrorMessage(e, t('instanceList.loadFailed'))
  } finally {
    loading.value = false
  }
}

function formatTime(iso: string) {
  const d = new Date(iso)
  const currentLocale = locale.value === 'zh-CN' ? 'zh-CN' : 'en-US'
  return d.toLocaleDateString(currentLocale, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

onMounted(fetchInstances)
</script>

<template>
  <div class="max-w-5xl mx-auto px-6 py-8">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold">{{ t('instanceList.title') }}</h1>
        <p class="text-sm text-muted-foreground mt-1">{{ t('instanceList.subtitle') }}</p>
      </div>
      <div class="flex items-center gap-2">
        <button
          class="flex items-center gap-2 px-3 py-2 rounded-lg border border-border text-sm text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          @click="fetchInstances"
        >
          <RefreshCw class="w-4 h-4" />
          {{ t('instanceList.refresh') }}
        </button>
        <button
          class="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
          @click="router.push('/instances/create')"
        >
          <Plus class="w-4 h-4" />
          {{ t('instanceList.createInstance') }}
        </button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="text-center py-20 space-y-4">
      <div class="w-16 h-16 rounded-2xl bg-red-500/10 flex items-center justify-center mx-auto">
        <Server class="w-8 h-8 text-red-400" />
      </div>
      <p class="text-sm text-red-400">{{ error }}</p>
      <button
        class="mt-2 px-4 py-2 rounded-lg border border-border text-sm hover:bg-accent transition-colors"
        @click="fetchInstances"
      >
        {{ t('instanceList.retry') }}
      </button>
    </div>

    <!-- Empty state -->
    <div
      v-else-if="instances.length === 0"
      class="text-center py-20 space-y-4"
    >
      <div class="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto">
        <Server class="w-8 h-8 text-primary" />
      </div>
      <h3 class="text-lg font-semibold">{{ t('instanceList.emptyTitle') }}</h3>
      <p class="text-sm text-muted-foreground max-w-sm mx-auto">
        {{ t('instanceList.emptyDescription') }}
      </p>
      <button
        class="mt-4 px-6 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        @click="router.push('/instances/create')"
      >
        {{ t('instanceList.createFirst') }}
      </button>
    </div>

    <!-- Instance table -->
    <div v-else class="rounded-xl border border-border overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-border bg-card/60">
            <th class="text-left px-4 py-3 font-medium text-muted-foreground">{{ t('instanceList.tableName') }}</th>
            <th class="text-left px-4 py-3 font-medium text-muted-foreground">{{ t('instanceList.tableStatus') }}</th>
            <th class="text-left px-4 py-3 font-medium text-muted-foreground">{{ t('instanceList.tableImageVersion') }}</th>
            <th class="text-left px-4 py-3 font-medium text-muted-foreground">{{ t('instanceList.tableNamespace') }}</th>
            <th class="text-left px-4 py-3 font-medium text-muted-foreground">{{ t('instanceList.tableCreatedAt') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="inst in sortedInstances"
            :key="inst.id"
            class="border-b border-border last:border-b-0 hover:bg-accent/50 cursor-pointer transition-colors"
            @click="router.push(`/instances/${inst.id}`)"
          >
            <td class="px-4 py-3 font-medium">{{ inst.name }}</td>
            <td class="px-4 py-3">
              <span class="inline-flex items-center gap-1.5">
                <span
                  class="w-2 h-2 rounded-full"
                  :class="[
                    getStatus(inst.status).bg,
                    animatingStatuses.has(inst.status) ? 'animate-pulse' : '',
                  ]"
                />
                <span :class="getStatus(inst.status).color">
                  {{ getStatusLabel(inst.status) }}
                </span>
              </span>
            </td>
            <td class="px-4 py-3 text-muted-foreground font-mono text-xs">{{ inst.image_version }}</td>
            <td class="px-4 py-3 text-muted-foreground font-mono text-xs">{{ inst.namespace }}</td>
            <td class="px-4 py-3 text-muted-foreground">{{ formatTime(inst.created_at) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
