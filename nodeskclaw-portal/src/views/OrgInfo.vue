<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useOrgStore } from '@/stores/org'
import { useClusterStore } from '@/stores/cluster'
import { useToast } from '@/composables/useToast'
import { useEdition, useFeature } from '@/composables/useFeature'
import { resolveApiErrorMessage } from '@/i18n/error'
import { Pencil, Check, X, Loader2, Box, Cpu, HardDrive, Database, Server } from 'lucide-vue-next'

const { t } = useI18n()
const orgStore = useOrgStore()
const clusterStore = useClusterStore()
const toast = useToast()
const { isEE } = useEdition()
const { isEnabled: hasBilling } = useFeature('billing')

const hasCluster = computed(() => clusterStore.clusters.length > 0)
const loading = ref(true)
const editing = ref(false)
const saving = ref(false)
const editName = ref('')

function startEdit() {
  editName.value = orgStore.currentOrg?.name ?? ''
  editing.value = true
}

function cancelEdit() {
  editing.value = false
}

async function saveName() {
  const trimmed = editName.value.trim()
  if (!trimmed || trimmed === orgStore.currentOrg?.name) {
    editing.value = false
    return
  }
  saving.value = true
  try {
    await orgStore.updateOrgName(trimmed)
    toast.success(t('orgSettings.nameUpdated'))
    editing.value = false
  } catch (e: unknown) {
    toast.error(resolveApiErrorMessage(e, t))
  } finally {
    saving.value = false
  }
}

function formatDate(iso: string | undefined): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric', month: 'long', day: 'numeric',
  })
}

// ── 用量 helpers ──

function parseResource(val: string | undefined | null): number {
  if (!val) return 0
  const s = String(val)
  if (s.endsWith('m')) return parseInt(s) / 1000
  if (s.endsWith('Mi')) return parseInt(s)
  if (s.endsWith('Gi')) return parseInt(s) * 1024
  return parseFloat(s) || 0
}

function parseStorage(val: string | undefined | null): number {
  if (!val) return 0
  const s = String(val)
  if (s.endsWith('Ti')) return parseFloat(s) * 1024
  if (s.endsWith('Gi')) return parseFloat(s)
  if (s.endsWith('Mi')) return parseFloat(s) / 1024
  return parseFloat(s) || 0
}

function formatCpuValue(val: string | undefined | null): string {
  if (!val) return '0'
  const s = String(val)
  if (s.endsWith('m')) {
    const cores = parseInt(s.slice(0, -1), 10) / 1000
    return Number.isInteger(cores) ? `${cores}` : `${cores.toFixed(2)}`
  }
  return s
}

function formatMemory(val: string | undefined | null): string {
  if (!val) return '0'
  const s = String(val)
  if (s.endsWith('Mi')) {
    const mi = parseInt(s)
    if (mi >= 1024) {
      const gi = mi / 1024
      return Number.isInteger(gi) ? `${gi} Gi` : `${gi.toFixed(1)} Gi`
    }
    return `${mi} Mi`
  }
  if (s.endsWith('Gi')) return `${parseInt(s)} Gi`
  if (s.endsWith('Ti')) return `${parseInt(s)} Ti`
  return s
}

function barColor(percent: number): string {
  if (percent >= 90) return 'bg-red-500'
  if (percent >= 70) return 'bg-amber-500'
  return 'bg-primary'
}

const instancePercent = computed(() => {
  if (!orgStore.usage) return 0
  const { instance_count, instance_limit } = orgStore.usage
  if (!instance_limit) return 0
  return Math.min(100, Math.round((instance_count / instance_limit) * 100))
})

const cpuPercent = computed(() => {
  if (!orgStore.usage) return 0
  const used = parseResource(orgStore.usage.cpu_used)
  const limit = parseResource(orgStore.usage.cpu_limit)
  if (!limit) return 0
  return Math.min(100, Math.round((used / limit) * 100))
})

const memPercent = computed(() => {
  if (!orgStore.usage) return 0
  const used = parseResource(orgStore.usage.mem_used)
  const limit = parseResource(orgStore.usage.mem_limit)
  if (!limit) return 0
  return Math.min(100, Math.round((used / limit) * 100))
})

const storagePercent = computed(() => {
  if (!orgStore.usage) return 0
  const used = parseStorage(orgStore.usage.storage_used)
  const limit = parseStorage(orgStore.usage.storage_limit)
  if (!limit) return 0
  return Math.min(100, Math.round((used / limit) * 100))
})

onMounted(async () => {
  await Promise.all([
    orgStore.fetchCurrentOrg(),
    clusterStore.fetchClusters(),
  ])
  if (hasBilling.value && hasCluster.value) {
    await orgStore.fetchUsage()
  }
  loading.value = false
})
</script>

<template>
  <div v-if="loading" class="flex items-center justify-center py-20">
    <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
  </div>

  <div v-else-if="orgStore.currentOrg" class="space-y-6">
    <!-- 基本信息 -->
    <section class="rounded-xl border border-border bg-card p-5">
      <h2 class="text-sm font-semibold text-muted-foreground mb-4">{{ t('orgSettings.basicInfo') }}</h2>
      <div class="grid grid-cols-[140px_1fr] gap-y-4 items-center text-sm">
        <span class="text-muted-foreground">{{ t('orgSettings.orgName') }}</span>
        <div class="flex items-center gap-2">
          <template v-if="!editing">
            <span class="font-medium">{{ orgStore.currentOrg.name }}</span>
            <button
              class="p-1 rounded hover:bg-muted/60 text-muted-foreground hover:text-foreground transition-colors"
              :title="t('orgSettings.editName')"
              @click="startEdit"
            >
              <Pencil class="w-3.5 h-3.5" />
            </button>
          </template>
          <template v-else>
            <input
              v-model="editName"
              type="text"
              class="h-8 px-2 rounded-md border border-border bg-background text-sm w-60 focus:outline-none focus:ring-1 focus:ring-primary"
              @keyup.enter="saveName"
              @keyup.escape="cancelEdit"
            />
            <button
              class="p-1 rounded hover:bg-primary/10 text-primary transition-colors"
              :disabled="saving"
              @click="saveName"
            >
              <Loader2 v-if="saving" class="w-4 h-4 animate-spin" />
              <Check v-else class="w-4 h-4" />
            </button>
            <button
              class="p-1 rounded hover:bg-muted/60 text-muted-foreground transition-colors"
              :disabled="saving"
              @click="cancelEdit"
            >
              <X class="w-4 h-4" />
            </button>
          </template>
        </div>

        <span class="text-muted-foreground">{{ t('orgSettings.orgSlug') }}</span>
        <span class="font-mono text-xs bg-muted/50 px-2 py-1 rounded w-fit">{{ orgStore.currentOrg.slug }}</span>

        <span class="text-muted-foreground">{{ t('orgSettings.createdAt') }}</span>
        <span>{{ formatDate(orgStore.currentOrg.created_at) }}</span>
      </div>
    </section>

    <!-- 关联信息 -->
    <section class="rounded-xl border border-border bg-card p-5">
      <h2 class="text-sm font-semibold text-muted-foreground mb-4">{{ t('orgSettings.relatedInfo') }}</h2>
      <div class="grid grid-cols-[140px_1fr] gap-y-4 items-center text-sm">
        <template v-if="!isEE">
          <span class="text-muted-foreground">{{ t('orgSettings.clusterName') }}</span>
          <span v-if="orgStore.currentOrg.cluster_name">{{ orgStore.currentOrg.cluster_name }}</span>
          <span v-else class="text-muted-foreground/60 italic">{{ t('orgSettings.clusterNone') }}</span>
        </template>

        <span class="text-muted-foreground">{{ t('orgSettings.memberCount') }}</span>
        <span>{{ orgStore.currentOrg.member_count }}</span>

        <span class="text-muted-foreground">{{ t('orgSettings.isActive') }}</span>
        <span
          class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium w-fit"
          :class="orgStore.currentOrg.is_active ? 'bg-green-500/15 text-green-400' : 'bg-red-500/15 text-red-400'"
        >
          {{ orgStore.currentOrg.is_active ? t('orgSettings.active') : t('orgSettings.inactive') }}
        </span>
      </div>
    </section>

    <!-- 资源用量（仅 billing 启用时） -->
    <section v-if="hasBilling" class="rounded-xl border border-border bg-card p-5">
      <h2 class="text-sm font-semibold text-muted-foreground mb-4">{{ t('orgUsage.title') }}</h2>

      <div v-if="!hasCluster" class="flex flex-col items-center justify-center py-10 text-muted-foreground">
        <Server class="w-8 h-8 mb-3 opacity-40" />
        <p class="text-sm">{{ t('orgUsage.noClusterHint') }}</p>
      </div>

      <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div class="p-4 rounded-lg border border-border bg-background space-y-3">
          <div class="flex items-center gap-2 text-sm font-medium">
            <Box class="w-4 h-4 text-blue-400" />
            {{ t('orgUsage.instances') }}
          </div>
          <div class="flex items-baseline gap-1">
            <span class="text-2xl font-bold">{{ orgStore.usage?.instance_count ?? 0 }}</span>
            <span class="text-sm text-muted-foreground">/ {{ orgStore.usage?.instance_limit ?? 0 }}</span>
          </div>
          <div class="w-full h-2 rounded-full bg-muted overflow-hidden">
            <div
              class="h-full rounded-full transition-all duration-500"
              :class="barColor(instancePercent)"
              :style="{ width: instancePercent + '%' }"
            />
          </div>
          <p class="text-xs text-muted-foreground">{{ t('orgUsage.usedPercent', { percent: instancePercent }) }}</p>
        </div>

        <div class="p-4 rounded-lg border border-border bg-background space-y-3">
          <div class="flex items-center gap-2 text-sm font-medium">
            <Cpu class="w-4 h-4 text-green-400" />
            {{ t('orgUsage.cpu') }}
          </div>
          <div class="flex items-baseline gap-1 whitespace-nowrap">
            <span class="text-2xl font-bold">{{ formatCpuValue(orgStore.usage?.cpu_used) }}</span>
            <span class="text-sm text-muted-foreground">/ {{ formatCpuValue(orgStore.usage?.cpu_limit) }} {{ t('orgUsage.cpuUnit') }}</span>
          </div>
          <div class="w-full h-2 rounded-full bg-muted overflow-hidden">
            <div
              class="h-full rounded-full transition-all duration-500"
              :class="barColor(cpuPercent)"
              :style="{ width: cpuPercent + '%' }"
            />
          </div>
          <p class="text-xs text-muted-foreground">{{ t('orgUsage.usedPercent', { percent: cpuPercent }) }}</p>
        </div>

        <div class="p-4 rounded-lg border border-border bg-background space-y-3">
          <div class="flex items-center gap-2 text-sm font-medium">
            <HardDrive class="w-4 h-4 text-purple-400" />
            {{ t('orgUsage.memory') }}
          </div>
          <div class="flex items-baseline gap-1">
            <span class="text-2xl font-bold">{{ formatMemory(orgStore.usage?.mem_used) }}</span>
            <span class="text-sm text-muted-foreground">/ {{ formatMemory(orgStore.usage?.mem_limit) }}</span>
          </div>
          <div class="w-full h-2 rounded-full bg-muted overflow-hidden">
            <div
              class="h-full rounded-full transition-all duration-500"
              :class="barColor(memPercent)"
              :style="{ width: memPercent + '%' }"
            />
          </div>
          <p class="text-xs text-muted-foreground">{{ t('orgUsage.usedPercent', { percent: memPercent }) }}</p>
        </div>

        <div class="p-4 rounded-lg border border-border bg-background space-y-3">
          <div class="flex items-center gap-2 text-sm font-medium">
            <Database class="w-4 h-4 text-orange-400" />
            {{ t('orgUsage.storage') }}
          </div>
          <div class="flex items-baseline gap-1">
            <span class="text-2xl font-bold">{{ orgStore.usage?.storage_used ?? '0' }}</span>
            <span class="text-sm text-muted-foreground">/ {{ orgStore.usage?.storage_limit ?? '0' }}</span>
          </div>
          <div class="w-full h-2 rounded-full bg-muted overflow-hidden">
            <div
              class="h-full rounded-full transition-all duration-500"
              :class="barColor(storagePercent)"
              :style="{ width: storagePercent + '%' }"
            />
          </div>
          <p class="text-xs text-muted-foreground">{{ t('orgUsage.usedPercent', { percent: storagePercent }) }}</p>
        </div>
      </div>
    </section>
  </div>
</template>
