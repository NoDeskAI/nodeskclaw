<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useOrgStore } from '@/stores/org'
import { BarChart3, Loader2, Box, Cpu, HardDrive, Database, Sparkles } from 'lucide-vue-next'

const orgStore = useOrgStore()
const loading = ref(true)

onMounted(async () => {
  if (!orgStore.currentOrgId) {
    await orgStore.fetchMyOrg()
  }
  if (orgStore.currentOrgId) {
    await orgStore.fetchUsage()
  }
  loading.value = false
})

function parseResource(val: string | undefined | null): number {
  if (!val) return 0
  const s = String(val)
  if (s.endsWith('m')) return parseInt(s) / 1000
  if (s.endsWith('Mi')) return parseInt(s)
  if (s.endsWith('Gi')) return parseInt(s) * 1024
  return parseFloat(s) || 0
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

function parseStorage(val: string | undefined | null): number {
  if (!val) return 0
  const s = String(val)
  if (s.endsWith('Ti')) return parseFloat(s) * 1024
  if (s.endsWith('Gi')) return parseFloat(s)
  if (s.endsWith('Mi')) return parseFloat(s) / 1024
  return parseFloat(s) || 0
}

function barColor(percent: number): string {
  if (percent >= 90) return 'bg-red-500'
  if (percent >= 70) return 'bg-amber-500'
  return 'bg-primary'
}
</script>

<template>
  <div class="max-w-4xl mx-auto px-6 py-8">
    <div class="mb-6">
      <h1 class="text-xl font-bold">资源用量</h1>
      <p class="text-sm text-muted-foreground mt-0.5">
        <span class="font-medium text-foreground">{{ orgStore.currentOrg?.name || '组织' }}</span> 的资源使用概览
      </p>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <!-- No Org -->
    <div v-else-if="!orgStore.currentOrg" class="text-center py-20 space-y-3">
      <BarChart3 class="w-12 h-12 mx-auto text-muted-foreground/40" />
      <p class="text-muted-foreground">你当前还没有加入任何组织</p>
    </div>

    <template v-else>
      <!-- Plan Info -->
      <div class="mb-6 p-4 rounded-xl border border-border bg-card flex items-center gap-3">
        <div class="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
          <Sparkles class="w-5 h-5 text-primary" />
        </div>
        <div>
          <p class="text-sm font-medium">当前套餐：<span class="text-primary">{{ orgStore.currentOrg.plan || 'free' }}</span></p>
          <p class="text-xs text-muted-foreground mt-0.5">
            {{ orgStore.currentOrg.member_count }} 位成员
          </p>
        </div>
      </div>

      <!-- Usage Cards -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <!-- Instances -->
        <div class="p-5 rounded-xl border border-border bg-card space-y-3">
          <div class="flex items-center gap-2 text-sm font-medium">
            <Box class="w-4 h-4 text-blue-400" />
            实例数
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
          <p class="text-xs text-muted-foreground">{{ instancePercent }}% 已使用</p>
        </div>

        <!-- CPU -->
        <div class="p-5 rounded-xl border border-border bg-card space-y-3">
          <div class="flex items-center gap-2 text-sm font-medium">
            <Cpu class="w-4 h-4 text-green-400" />
            CPU
          </div>
          <div class="flex items-baseline gap-1">
            <span class="text-2xl font-bold">{{ orgStore.usage?.cpu_used ?? '0' }}</span>
            <span class="text-sm text-muted-foreground">/ {{ orgStore.usage?.cpu_limit ?? '0' }}</span>
          </div>
          <div class="w-full h-2 rounded-full bg-muted overflow-hidden">
            <div
              class="h-full rounded-full transition-all duration-500"
              :class="barColor(cpuPercent)"
              :style="{ width: cpuPercent + '%' }"
            />
          </div>
          <p class="text-xs text-muted-foreground">{{ cpuPercent }}% 已使用</p>
        </div>

        <!-- Memory -->
        <div class="p-5 rounded-xl border border-border bg-card space-y-3">
          <div class="flex items-center gap-2 text-sm font-medium">
            <HardDrive class="w-4 h-4 text-purple-400" />
            内存
          </div>
          <div class="flex items-baseline gap-1">
            <span class="text-2xl font-bold">{{ orgStore.usage?.mem_used ?? '0' }}</span>
            <span class="text-sm text-muted-foreground">/ {{ orgStore.usage?.mem_limit ?? '0' }}</span>
          </div>
          <div class="w-full h-2 rounded-full bg-muted overflow-hidden">
            <div
              class="h-full rounded-full transition-all duration-500"
              :class="barColor(memPercent)"
              :style="{ width: memPercent + '%' }"
            />
          </div>
          <p class="text-xs text-muted-foreground">{{ memPercent }}% 已使用</p>
        </div>

        <!-- Storage -->
        <div class="p-5 rounded-xl border border-border bg-card space-y-3">
          <div class="flex items-center gap-2 text-sm font-medium">
            <Database class="w-4 h-4 text-orange-400" />
            存储
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
          <p class="text-xs text-muted-foreground">{{ storagePercent }}% 已使用</p>
        </div>
      </div>
    </template>
  </div>
</template>
