<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useInstanceStore, type InstanceInfo } from '@/stores/instance'
import { useClusterStore } from '@/stores/cluster'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import GlowCard from '@/components/GlowCard.vue'
import StatusDot from '@/components/StatusDot.vue'
import { Box, Trash2, Eye, Rocket, Search, LayoutGrid, List } from 'lucide-vue-next'
import { toast } from 'vue-sonner'

const router = useRouter()
const instanceStore = useInstanceStore()
const clusterStore = useClusterStore()

// ── 过滤与搜索 ──
const searchQuery = ref('')
const statusFilter = ref('all')
const namespaceFilter = ref('all')
const viewMode = ref<'card' | 'table'>('card')

onMounted(() => {
  instanceStore.fetchInstances(clusterStore.currentClusterId ?? undefined)
})

// 从实例列表提取去重的命名空间
const namespaces = computed(() => {
  const ns = new Set(instanceStore.instances.map((i) => i.namespace))
  return Array.from(ns).sort()
})

// 从实例列表提取去重的状态
const statuses = computed(() => {
  const s = new Set(instanceStore.instances.map((i) => i.status))
  return Array.from(s).sort()
})

// 过滤后的实例列表
const filteredInstances = computed(() => {
  let list = instanceStore.instances
  // 搜索
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(
      (i) => i.name.toLowerCase().includes(q) || i.slug?.toLowerCase().includes(q) || i.namespace.toLowerCase().includes(q),
    )
  }
  // 状态过滤
  if (statusFilter.value !== 'all') {
    list = list.filter((i) => i.status === statusFilter.value)
  }
  // 命名空间过滤
  if (namespaceFilter.value !== 'all') {
    list = list.filter((i) => i.namespace === namespaceFilter.value)
  }
  return list
})

function statusToGlow(status: string) {
  if (status === 'running') return 'running' as const
  if (status === 'deploying' || status === 'pending') return 'warning' as const
  return 'error' as const
}

function statusToDot(status: string) {
  if (status === 'running') return 'running' as const
  if (status === 'deploying' || status === 'pending') return 'pending' as const
  if (status === 'failed' || status === 'stopped') return 'failed' as const
  return 'unknown' as const
}

function statusBadgeVariant(status: string) {
  if (status === 'running') return 'default' as const
  if (status === 'deploying' || status === 'pending') return 'secondary' as const
  return 'destructive' as const
}

async function handleDelete(inst: InstanceInfo) {
  if (!confirm(`确定删除实例 "${inst.name}"？K8s 资源将同步删除。`)) return
  try {
    await instanceStore.deleteInstance(inst.id)
    toast.success('实例已删除')
  } catch {
    toast.error('删除失败')
  }
}
</script>

<template>
  <div class="p-6 space-y-4">
    <!-- 标题栏 -->
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-bold">实例管理</h1>
      <Button @click="router.push('/deploy')">
        <Rocket class="w-4 h-4 mr-2" />
        部署新实例
      </Button>
    </div>

    <!-- 工具栏：搜索 + 过滤 + 视图切换 -->
    <div class="flex items-center gap-3">
      <div class="relative flex-1 max-w-sm">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <Input
          v-model="searchQuery"
          placeholder="搜索实例名称或命名空间..."
          class="pl-9"
        />
      </div>
      <Select v-model="statusFilter">
        <SelectTrigger class="w-[130px]">
          <SelectValue placeholder="状态" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">全部状态</SelectItem>
          <SelectItem v-for="s in statuses" :key="s" :value="s">{{ s }}</SelectItem>
        </SelectContent>
      </Select>
      <Select v-model="namespaceFilter">
        <SelectTrigger class="w-[160px]">
          <SelectValue placeholder="命名空间" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">全部命名空间</SelectItem>
          <SelectItem v-for="ns in namespaces" :key="ns" :value="ns">{{ ns }}</SelectItem>
        </SelectContent>
      </Select>
      <div class="flex items-center border border-border rounded-md overflow-hidden ml-auto">
        <button
          class="p-1.5 transition-colors"
          :class="viewMode === 'card' ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground'"
          @click="viewMode = 'card'"
        >
          <LayoutGrid class="w-4 h-4" />
        </button>
        <button
          class="p-1.5 transition-colors"
          :class="viewMode === 'table' ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground'"
          @click="viewMode = 'table'"
        >
          <List class="w-4 h-4" />
        </button>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="instanceStore.loading" class="text-muted-foreground text-center py-12">
      加载中...
    </div>

    <!-- 空状态 -->
    <div v-else-if="instanceStore.instances.length === 0" class="text-center py-20">
      <Box class="w-12 h-12 text-muted-foreground mx-auto mb-4" />
      <p class="text-muted-foreground">暂无实例</p>
    </div>

    <!-- 过滤无结果 -->
    <div v-else-if="filteredInstances.length === 0" class="text-center py-12">
      <Search class="w-8 h-8 text-muted-foreground mx-auto mb-3" />
      <p class="text-muted-foreground">没有匹配的实例</p>
    </div>

    <!-- 卡片视图 -->
    <div v-else-if="viewMode === 'card'" class="grid gap-4">
      <GlowCard
        v-for="inst in filteredInstances"
        :key="inst.id"
        :status="statusToGlow(inst.status)"
        class="cursor-pointer"
        @click="router.push(`/instances/${inst.id}`)"
      >
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <StatusDot :status="statusToDot(inst.status)" size="md" />
            <div>
              <div class="font-medium">{{ inst.name }}</div>
              <div class="text-xs font-mono text-muted-foreground">{{ inst.slug }}</div>
              <div class="text-sm text-muted-foreground mt-0.5">
                {{ inst.namespace }} / {{ inst.image_version }}
                <span class="ml-2">
                  {{ inst.available_replicas }}/{{ inst.replicas }} 副本
                </span>
              </div>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <Badge :variant="statusBadgeVariant(inst.status)">
              {{ inst.status }}
            </Badge>
            <Button
              variant="outline"
              size="sm"
              @click.stop="router.push(`/instances/${inst.id}`)"
            >
              <Eye class="w-3 h-3 mr-1" />
              详情
            </Button>
            <Button
              variant="ghost"
              size="sm"
              @click.stop="handleDelete(inst)"
            >
              <Trash2 class="w-3 h-3 text-destructive" />
            </Button>
          </div>
        </div>
      </GlowCard>
    </div>

    <!-- 表格视图 -->
    <div v-else class="rounded-lg border border-border overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-border bg-muted/30">
            <th class="text-left px-4 py-2.5 font-medium">状态</th>
            <th class="text-left px-4 py-2.5 font-medium">实例名</th>
            <th class="text-left px-4 py-2.5 font-medium">标识</th>
            <th class="text-left px-4 py-2.5 font-medium">命名空间</th>
            <th class="text-left px-4 py-2.5 font-medium">镜像版本</th>
            <th class="text-left px-4 py-2.5 font-medium">副本</th>
            <th class="text-right px-4 py-2.5 font-medium">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="inst in filteredInstances"
            :key="inst.id"
            class="border-b border-border last:border-b-0 hover:bg-muted/20 cursor-pointer transition-colors"
            @click="router.push(`/instances/${inst.id}`)"
          >
            <td class="px-4 py-2.5">
              <div class="flex items-center gap-2">
                <StatusDot :status="statusToDot(inst.status)" />
                <Badge :variant="statusBadgeVariant(inst.status)" class="text-xs">
                  {{ inst.status }}
                </Badge>
              </div>
            </td>
            <td class="px-4 py-2.5 font-medium">{{ inst.name }}</td>
            <td class="px-4 py-2.5 font-mono text-xs text-muted-foreground">{{ inst.slug }}</td>
            <td class="px-4 py-2.5 text-muted-foreground font-mono text-xs">{{ inst.namespace }}</td>
            <td class="px-4 py-2.5 font-mono text-xs">{{ inst.image_version }}</td>
            <td class="px-4 py-2.5">{{ inst.available_replicas }}/{{ inst.replicas }}</td>
            <td class="px-4 py-2.5 text-right">
              <div class="flex items-center justify-end gap-1">
                <Button variant="ghost" size="sm" @click.stop="router.push(`/instances/${inst.id}`)">
                  <Eye class="w-3 h-3" />
                </Button>
                <Button variant="ghost" size="sm" @click.stop="handleDelete(inst)">
                  <Trash2 class="w-3 h-3 text-destructive" />
                </Button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
