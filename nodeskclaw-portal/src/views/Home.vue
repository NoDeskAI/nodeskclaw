<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, ExternalLink, Circle, Loader2, Trash2 } from 'lucide-vue-next'
import api from '@/services/api'

const router = useRouter()

interface InstanceItem {
  id: string
  name: string
  status: string
  image_version: string
  ingress_domain: string | null
  created_at: string
}

const instances = ref<InstanceItem[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const res = await api.get('/instances')
    instances.value = res.data.data ?? []
  } finally {
    loading.value = false
  }
})

const statusColors: Record<string, string> = {
  running: 'text-green-400',
  learning: 'text-blue-400',
  deploying: 'text-yellow-400',
  creating: 'text-blue-400',
  updating: 'text-blue-400',
  failed: 'text-red-400',
  deleting: 'text-zinc-400',
  pending: 'text-yellow-400',
}

const statusLabels: Record<string, string> = {
  running: '运行中',
  learning: '学习中',
  deploying: '部署中',
  creating: '创建中',
  updating: '更新中',
  failed: '异常',
  deleting: '删除中',
  pending: '等待中',
}

const isEmpty = computed(() => !loading.value && instances.value.length === 0)
</script>

<template>
  <div class="max-w-4xl mx-auto px-6 py-8">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-xl font-bold">我的AI 员工</h1>
        <p class="text-sm text-muted-foreground mt-0.5">管理你部署的 DeskClaw AI 员工</p>
      </div>
      <button
        class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        @click="router.push('/create')"
      >
        <Plus class="w-4 h-4" />
        创建AI 员工
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <!-- Empty -->
    <div v-else-if="isEmpty" class="text-center py-20 space-y-4">
      <div class="w-16 h-16 mx-auto rounded-full bg-primary/10 flex items-center justify-center">
        <Plus class="w-8 h-8 text-primary" />
      </div>
      <div>
        <p class="text-lg font-medium">还没有AI 员工</p>
        <p class="text-sm text-muted-foreground mt-1">点击下方按钮创建你的第一个 AI 员工</p>
      </div>
      <button
        class="px-6 py-2.5 rounded-lg bg-primary text-primary-foreground font-medium text-sm hover:bg-primary/90 transition-colors"
        @click="router.push('/create')"
      >
        创建AI 员工
      </button>
    </div>

    <!-- Instance List -->
    <div v-else class="space-y-3">
      <div
        v-for="inst in instances"
        :key="inst.id"
        class="flex items-center justify-between p-4 rounded-xl border border-border bg-card hover:border-primary/30 transition-colors cursor-pointer"
        @click="router.push(`/instances/${inst.id}`)"
      >
        <div class="flex items-center gap-4">
          <div class="flex items-center gap-2">
            <Circle class="w-2.5 h-2.5 fill-current" :class="statusColors[inst.status] || 'text-zinc-500'" />
            <span class="font-medium">{{ inst.name }}</span>
          </div>
          <span class="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded">
            {{ inst.image_version }}
          </span>
        </div>
        <div class="flex items-center gap-4">
          <span class="text-xs" :class="statusColors[inst.status] || 'text-zinc-500'">
            {{ statusLabels[inst.status] || inst.status }}
          </span>
          <a
            v-if="inst.ingress_domain && inst.status === 'running'"
            :href="`https://${inst.ingress_domain}`"
            target="_blank"
            class="text-primary hover:text-primary/80"
            @click.stop
          >
            <ExternalLink class="w-4 h-4" />
          </a>
        </div>
      </div>
    </div>
  </div>
</template>
