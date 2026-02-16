<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { PawPrint, Loader2, Rocket, ChevronRight } from 'lucide-vue-next'
import api from '@/services/api'

const router = useRouter()

const name = ref('')
const description = ref('')
const selectedSpec = ref('medium')
const deploying = ref(false)
const error = ref('')

// 从后端获取可用镜像版本和集群
const imageTags = ref<string[]>([])
const clusters = ref<{ id: string; name: string }[]>([])
const loadingInit = ref(true)

const specs = [
  { key: 'small', label: '轻量', desc: '适合个人使用', cpu: '2 核', mem: '4 GB' },
  { key: 'medium', label: '标准', desc: '适合小团队', cpu: '4 核', mem: '8 GB' },
  { key: 'large', label: '高性能', desc: '适合大规模使用', cpu: '8 核', mem: '16 GB' },
]

const specResources: Record<string, { cpu_req: string; cpu_lim: string; mem_req: string; mem_lim: string; quota_cpu: string; quota_mem: string }> = {
  small: { cpu_req: '1000m', cpu_lim: '2000m', mem_req: '2Gi', mem_lim: '4Gi', quota_cpu: '2', quota_mem: '4Gi' },
  medium: { cpu_req: '2000m', cpu_lim: '4000m', mem_req: '4Gi', mem_lim: '8Gi', quota_cpu: '4', quota_mem: '8Gi' },
  large: { cpu_req: '4000m', cpu_lim: '8000m', mem_req: '8Gi', mem_lim: '16Gi', quota_cpu: '8', quota_mem: '16Gi' },
}

onMounted(async () => {
  try {
    const [tagsRes, clustersRes] = await Promise.all([
      api.get('/registry/tags'),
      api.get('/clusters'),
    ])
    imageTags.value = tagsRes.data.data?.tags ?? []
    clusters.value = (clustersRes.data.data ?? []).filter((c: any) => c.status === 'connected')
  } catch {
    // ignore init errors
  } finally {
    loadingInit.value = false
  }
})

async function handleDeploy() {
  if (!name.value.trim()) {
    error.value = '请输入实例名称'
    return
  }
  if (clusters.value.length === 0) {
    error.value = '没有可用的集群，请联系管理员'
    return
  }

  deploying.value = true
  error.value = ''

  const res_spec = specResources[selectedSpec.value]

  try {
    const res = await api.post('/deploy', {
      name: name.value.trim(),
      cluster_id: clusters.value[0].id,
      image_version: imageTags.value[0] || 'latest',
      replicas: 1,
      cpu_request: res_spec.cpu_req,
      cpu_limit: res_spec.cpu_lim,
      mem_request: res_spec.mem_req,
      mem_limit: res_spec.mem_lim,
      quota_cpu: res_spec.quota_cpu,
      quota_mem: res_spec.quota_mem,
      description: description.value || undefined,
    })

    const deployId = res.data.data?.deploy_id
    if (deployId) {
      router.push(`/instances/${deployId}`)
    } else {
      router.push('/')
    }
  } catch (e: any) {
    error.value = e?.response?.data?.message || e?.response?.data?.detail || '部署失败'
  } finally {
    deploying.value = false
  }
}
</script>

<template>
  <div class="max-w-2xl mx-auto px-6 py-8">
    <div class="mb-8">
      <h1 class="text-xl font-bold">创建实例</h1>
      <p class="text-sm text-muted-foreground mt-1">只需几步即可部署你的 AI 助手</p>
    </div>

    <div v-if="loadingInit" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <div v-else class="space-y-8">
      <!-- 名称 -->
      <div class="space-y-2">
        <label class="text-sm font-medium">给你的 AI 助手取个名字</label>
        <input
          v-model="name"
          type="text"
          placeholder="例如：my-assistant"
          class="w-full px-4 py-2.5 rounded-lg bg-card border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-colors"
        />
      </div>

      <!-- 规格选择 -->
      <div class="space-y-3">
        <label class="text-sm font-medium">选择规格</label>
        <div class="grid grid-cols-3 gap-3">
          <button
            v-for="spec in specs"
            :key="spec.key"
            :class="[
              'p-4 rounded-xl border text-left transition-all',
              selectedSpec === spec.key
                ? 'border-primary bg-primary/5 ring-1 ring-primary/30'
                : 'border-border bg-card hover:border-primary/20',
            ]"
            @click="selectedSpec = spec.key"
          >
            <div class="font-medium text-sm">{{ spec.label }}</div>
            <div class="text-xs text-muted-foreground mt-0.5">{{ spec.desc }}</div>
            <div class="flex gap-3 mt-2 text-xs text-muted-foreground">
              <span>{{ spec.cpu }}</span>
              <span>{{ spec.mem }}</span>
            </div>
          </button>
        </div>
      </div>

      <!-- 部署 -->
      <div class="pt-4">
        <p v-if="error" class="text-sm text-destructive mb-3">{{ error }}</p>
        <button
          :disabled="deploying"
          class="w-full py-3 px-4 rounded-lg bg-primary text-primary-foreground font-medium text-sm hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          @click="handleDeploy"
        >
          <Loader2 v-if="deploying" class="w-4 h-4 animate-spin" />
          <Rocket v-else class="w-4 h-4" />
          {{ deploying ? '部署中...' : '一键部署' }}
        </button>
      </div>
    </div>
  </div>
</template>
