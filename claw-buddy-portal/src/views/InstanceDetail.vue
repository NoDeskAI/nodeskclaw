<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ExternalLink, RefreshCw, Trash2, Circle, Loader2, Settings } from 'lucide-vue-next'
import api from '@/services/api'

const route = useRoute()
const router = useRouter()
const instanceId = computed(() => route.params.id as string)

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
  env_vars: string | null
  created_at: string
  pods: { name: string; status: string; ready: boolean; restart_count: number }[]
}

const instance = ref<InstanceDetail | null>(null)
const loading = ref(true)
const error = ref('')
const openclawUrl = ref('')

onMounted(async () => {
  await fetchDetail()
})

async function fetchDetail() {
  loading.value = true
  try {
    const res = await api.get(`/instances/${instanceId.value}`)
    instance.value = res.data.data

    // 构造 OpenClaw 访问地址
    if (instance.value?.ingress_domain && instance.value.env_vars) {
      try {
        const envs = JSON.parse(instance.value.env_vars)
        const token = envs.OPENCLAW_GATEWAY_TOKEN
        if (token) {
          openclawUrl.value = `https://${instance.value.ingress_domain}?token=${token}`
        }
      } catch { /* ignore */ }
    }
  } catch (e: any) {
    error.value = e?.response?.data?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function handleDelete() {
  if (!confirm(`确定删除实例「${instance.value?.name}」？此操作不可恢复。`)) return
  try {
    await api.delete(`/instances/${instanceId.value}`)
    router.push('/instances')
  } catch (e: any) {
    error.value = e?.response?.data?.message || '删除失败'
  }
}

const statusColors: Record<string, string> = {
  running: 'text-green-400',
  deploying: 'text-yellow-400',
  failed: 'text-red-400',
}
const statusLabels: Record<string, string> = {
  running: '运行中',
  deploying: '部署中',
  creating: '创建中',
  updating: '更新中',
  failed: '异常',
  pending: '等待中',
}
</script>

<template>
  <div class="max-w-3xl mx-auto px-6 py-8">
    <!-- Header -->
    <div class="flex items-center gap-3 mb-6">
      <button class="text-muted-foreground hover:text-foreground" @click="router.push('/instances')">
        <ArrowLeft class="w-5 h-5" />
      </button>
      <div v-if="instance" class="flex items-center gap-3">
        <h1 class="text-xl font-bold">{{ instance.name }}</h1>
        <span class="flex items-center gap-1 text-xs" :class="statusColors[instance.status] || 'text-zinc-400'">
          <Circle class="w-2 h-2 fill-current" />
          {{ statusLabels[instance.status] || instance.status }}
        </span>
      </div>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <div v-else-if="error" class="text-center py-20 text-destructive">{{ error }}</div>

    <div v-else-if="instance" class="space-y-6">
      <!-- OpenClaw 访问 -->
      <div v-if="openclawUrl" class="p-4 rounded-xl border border-primary/30 bg-primary/5">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm font-medium">OpenClaw 访问地址</p>
            <p class="text-xs text-muted-foreground mt-0.5">点击即可打开 AI 助手</p>
          </div>
          <a
            :href="openclawUrl"
            target="_blank"
            class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            <ExternalLink class="w-4 h-4" />
            打开
          </a>
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
            <span class="text-muted-foreground">副本</span>
            <span class="ml-2">{{ instance.available_replicas }}/{{ instance.replicas }}</span>
          </div>
          <div>
            <span class="text-muted-foreground">CPU</span>
            <span class="ml-2">{{ instance.cpu_limit }}</span>
          </div>
          <div>
            <span class="text-muted-foreground">内存</span>
            <span class="ml-2">{{ instance.mem_limit }}</span>
          </div>
          <div class="col-span-2">
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
          class="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-border text-sm hover:bg-card transition-colors"
          @click="router.push(`/instances/${instanceId}/settings`)"
        >
          <Settings class="w-4 h-4" />
          设置
        </button>
        <button
          class="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-red-500/30 text-red-400 text-sm hover:bg-red-500/10 transition-colors ml-auto"
          @click="handleDelete"
        >
          <Trash2 class="w-4 h-4" />
          删除实例
        </button>
      </div>
    </div>
  </div>
</template>
