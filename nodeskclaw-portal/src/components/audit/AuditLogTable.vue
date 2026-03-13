<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useOrgStore } from '@/stores/org'
import api from '@/services/api'
import { useToast } from '@/composables/useToast'
import { resolveApiErrorMessage } from '@/i18n/error'
import CustomSelect, { type SelectOption } from '@/components/shared/CustomSelect.vue'
import BaseTooltip from '@/components/shared/BaseTooltip.vue'
import {
  Download, ChevronLeft, ChevronRight, FileJson, FileSpreadsheet,
  Search, User as UserIcon, Loader2, ScrollText,
} from 'lucide-vue-next'

const { t } = useI18n()
const orgStore = useOrgStore()
const toast = useToast()

interface AuditLog {
  id: string
  org_id: string | null
  workspace_id: string | null
  action: string
  target_type: string
  target_id: string | null
  actor_type: string
  actor_id: string | null
  actor_name: string | null
  details: Record<string, unknown> | null
  created_at: string
}

const logs = ref<AuditLog[]>([])
const loading = ref(false)

const filters = ref({
  action: '',
  target_type: null as string | null,
  from_time: '',
  to_time: '',
})

const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

const exportOpen = ref(false)

const targetTypeOptions = computed<SelectOption[]>(() => [
  { value: null, label: t('auditLogs.filterAll') },
  { value: 'user', label: 'user' },
  { value: 'instance', label: 'instance' },
  { value: 'cluster', label: 'cluster' },
  { value: 'workspace', label: 'workspace' },
  { value: 'organization', label: 'organization' },
  { value: 'llm_key', label: 'llm_key' },
  { value: 'system_config', label: 'system_config' },
])

const actionColorMap: Record<string, string> = {
  auth: 'bg-blue-500/15 text-blue-400',
  instance: 'bg-emerald-500/15 text-emerald-400',
  deploy: 'bg-emerald-500/15 text-emerald-400',
  cluster: 'bg-amber-500/15 text-amber-400',
  workspace: 'bg-violet-500/15 text-violet-400',
  org: 'bg-amber-500/15 text-amber-400',
  llm_key: 'bg-amber-500/15 text-amber-400',
  system: 'bg-amber-500/15 text-amber-400',
}

function actionBadgeClass(action: string): string {
  const prefix = action.split('.')[0]
  return actionColorMap[prefix] ?? 'bg-muted text-muted-foreground'
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function truncate(s: string | null | undefined, max = 12): string {
  if (!s) return '-'
  return s.length > max ? s.slice(0, max) + '...' : s
}

function buildParams(): Record<string, string | number> {
  const params: Record<string, string | number> = {
    page: page.value,
    page_size: pageSize.value,
  }
  if (filters.value.action.trim()) params.action = filters.value.action.trim()
  if (filters.value.target_type) params.target_type = filters.value.target_type
  if (filters.value.from_time) params.from_time = new Date(filters.value.from_time).toISOString()
  if (filters.value.to_time) params.to_time = new Date(filters.value.to_time).toISOString()
  return params
}

async function fetchLogs() {
  const orgId = orgStore.currentOrgId
  if (!orgId) return
  loading.value = true
  try {
    const res = await api.get(`/orgs/${orgId}/audit-logs`, { params: buildParams() })
    logs.value = res.data.data ?? []
    total.value = res.data.pagination?.total ?? 0
  } catch (e: unknown) {
    toast.error(resolveApiErrorMessage(e, t('auditLogs.loadFailed')))
  } finally {
    loading.value = false
  }
}

async function handleExport(format: 'csv' | 'json') {
  const orgId = orgStore.currentOrgId
  if (!orgId) return
  exportOpen.value = false
  try {
    const params = { ...buildParams(), format, limit: 5000 }
    delete (params as any).page
    delete (params as any).page_size
    const res = await api.get(`/orgs/${orgId}/audit-logs/export`, { params, responseType: 'blob' })
    const blob = new Blob([res.data])
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `audit-logs.${format}`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    toast.success(t('auditLogs.exportSuccess'))
  } catch (e: unknown) {
    toast.error(resolveApiErrorMessage(e, t('auditLogs.exportFailed')))
  }
}

function applyFilters() {
  page.value = 1
  fetchLogs()
}

watch(page, () => fetchLogs())

onMounted(async () => {
  if (!orgStore.currentOrg) await orgStore.fetchMyOrg()
  await fetchLogs()
})
</script>

<template>
  <div class="space-y-5">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-base font-semibold">{{ t('auditLogs.title') }}</h2>
        <p class="text-xs text-muted-foreground mt-1">{{ t('auditLogs.description') }}</p>
      </div>
      <div class="relative">
        <button
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs font-medium hover:bg-muted/50 transition-colors"
          @click="exportOpen = !exportOpen"
        >
          <Download class="w-3.5 h-3.5" />
          {{ t('auditLogs.export') }}
        </button>
        <div
          v-if="exportOpen"
          class="absolute right-0 top-full z-50 mt-1 min-w-[10rem] rounded-md border border-border bg-card shadow-lg overflow-hidden"
        >
          <button
            class="flex w-full items-center gap-2 px-3 py-2 text-xs text-foreground hover:bg-accent transition-colors"
            @click="handleExport('csv')"
          >
            <FileSpreadsheet class="w-3.5 h-3.5" />
            {{ t('auditLogs.exportCsv') }}
          </button>
          <button
            class="flex w-full items-center gap-2 px-3 py-2 text-xs text-foreground hover:bg-accent transition-colors"
            @click="handleExport('json')"
          >
            <FileJson class="w-3.5 h-3.5" />
            {{ t('auditLogs.exportJson') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap items-end gap-3">
      <div class="space-y-1">
        <label class="text-xs text-muted-foreground">{{ t('auditLogs.filterAction') }}</label>
        <div class="relative">
          <Search class="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <input
            v-model="filters.action"
            :placeholder="t('auditLogs.filterActionPlaceholder')"
            class="w-48 h-8 pl-7 pr-3 rounded-md border border-border bg-card text-xs focus:outline-none focus:ring-2 focus:ring-primary/30"
            @keydown.enter="applyFilters"
          />
        </div>
      </div>

      <div class="space-y-1">
        <label class="text-xs text-muted-foreground">{{ t('auditLogs.filterTargetType') }}</label>
        <CustomSelect
          :model-value="filters.target_type"
          :options="targetTypeOptions"
          :placeholder="t('auditLogs.filterAll')"
          size="xs"
          trigger-class="w-36 h-8"
          @update:model-value="filters.target_type = $event; applyFilters()"
        />
      </div>

      <div class="space-y-1">
        <label class="text-xs text-muted-foreground">{{ t('auditLogs.filterFromTime') }}</label>
        <input
          v-model="filters.from_time"
          type="datetime-local"
          class="w-44 h-8 px-2 rounded-md border border-border bg-card text-xs focus:outline-none focus:ring-2 focus:ring-primary/30 [color-scheme:dark]"
          @change="applyFilters"
        />
      </div>

      <div class="space-y-1">
        <label class="text-xs text-muted-foreground">{{ t('auditLogs.filterToTime') }}</label>
        <input
          v-model="filters.to_time"
          type="datetime-local"
          class="w-44 h-8 px-2 rounded-md border border-border bg-card text-xs focus:outline-none focus:ring-2 focus:ring-primary/30 [color-scheme:dark]"
          @change="applyFilters"
        />
      </div>
    </div>

    <!-- Table -->
    <div class="border border-border rounded-lg overflow-hidden">
      <table class="w-full text-left text-xs">
        <thead class="bg-muted/40 text-muted-foreground">
          <tr>
            <th class="px-3 py-2.5 font-medium w-[160px]">{{ t('auditLogs.colTime') }}</th>
            <th class="px-3 py-2.5 font-medium w-[180px]">{{ t('auditLogs.colAction') }}</th>
            <th class="px-3 py-2.5 font-medium w-[100px]">{{ t('auditLogs.colTargetType') }}</th>
            <th class="px-3 py-2.5 font-medium w-[120px]">{{ t('auditLogs.colTargetId') }}</th>
            <th class="px-3 py-2.5 font-medium w-[140px]">{{ t('auditLogs.colActor') }}</th>
            <th class="px-3 py-2.5 font-medium">{{ t('auditLogs.colDetails') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-border">
          <tr v-if="loading">
            <td colspan="6" class="text-center py-12 text-muted-foreground">
              <Loader2 class="w-5 h-5 animate-spin mx-auto" />
            </td>
          </tr>
          <tr v-else-if="logs.length === 0">
            <td colspan="6" class="text-center py-12">
              <ScrollText class="w-8 h-8 text-muted-foreground/50 mx-auto mb-2" />
              <p class="text-sm text-muted-foreground">{{ t('auditLogs.empty') }}</p>
            </td>
          </tr>
          <tr v-for="log in logs" :key="log.id" v-else class="hover:bg-muted/30 transition-colors">
            <td class="px-3 py-2.5 tabular-nums whitespace-nowrap">{{ formatDate(log.created_at) }}</td>
            <td class="px-3 py-2.5">
              <span class="inline-block px-2 py-0.5 rounded text-[11px] font-mono" :class="actionBadgeClass(log.action)">
                {{ log.action }}
              </span>
            </td>
            <td class="px-3 py-2.5">{{ log.target_type || '-' }}</td>
            <td class="px-3 py-2.5">
              <BaseTooltip :text="log.target_id || '-'">
                <span class="cursor-default">{{ truncate(log.target_id) }}</span>
              </BaseTooltip>
            </td>
            <td class="px-3 py-2.5">
              <BaseTooltip :text="log.actor_id || '-'">
                <span class="inline-flex items-center gap-1 cursor-default">
                  <UserIcon class="w-3 h-3 text-muted-foreground shrink-0" />
                  {{ log.actor_name || truncate(log.actor_id) }}
                </span>
              </BaseTooltip>
            </td>
            <td class="px-3 py-2.5 max-w-[260px]">
              <BaseTooltip :text="log.details ? JSON.stringify(log.details) : '-'">
                <span class="block truncate cursor-default">
                  {{ log.details ? JSON.stringify(log.details) : '-' }}
                </span>
              </BaseTooltip>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div class="flex items-center justify-between">
      <span class="text-xs text-muted-foreground">
        {{ t('auditLogs.pagination', { page: page, total: totalPages }) }}
      </span>
      <div class="flex items-center gap-2">
        <button
          class="flex items-center gap-1 px-2.5 py-1.5 rounded-md border border-border text-xs hover:bg-muted/50 transition-colors disabled:opacity-40 disabled:pointer-events-none"
          :disabled="page <= 1"
          @click="page--"
        >
          <ChevronLeft class="w-3.5 h-3.5" />
          {{ t('auditLogs.prevPage') }}
        </button>
        <button
          class="flex items-center gap-1 px-2.5 py-1.5 rounded-md border border-border text-xs hover:bg-muted/50 transition-colors disabled:opacity-40 disabled:pointer-events-none"
          :disabled="page >= totalPages"
          @click="page++"
        >
          {{ t('auditLogs.nextPage') }}
          <ChevronRight class="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  </div>
</template>
