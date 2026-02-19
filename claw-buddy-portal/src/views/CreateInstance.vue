<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Loader2, Rocket, Database, ChevronDown, RefreshCw, AlertCircle, Check, Brain, Key } from 'lucide-vue-next'
import { pinyin } from 'pinyin-pro'
import api from '@/services/api'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const name = ref('')
const slug = ref('')
const slugManuallyEdited = ref(false)
const slugChecking = ref(false)
const slugConflict = ref(false)
const slugError = ref('')
const description = ref('')
const selectedSpec = ref('small')
const selectedImage = ref('')
const storageGi = ref(20)
const deploying = ref(false)
const error = ref('')

// ── LLM config ──
interface AvailableKey {
  id: string
  provider: string
  label: string
  api_key_masked: string
  is_active: boolean
}

interface LlmConfigEntry {
  provider: string
  keySource: 'org' | 'personal' | 'none'
  orgKeyId: string
  personalKey: string
}

const PROVIDERS = ['openai', 'anthropic', 'gemini', 'openrouter'] as const
const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  gemini: 'Google Gemini',
  openrouter: 'OpenRouter',
}

const availableOrgKeys = ref<AvailableKey[]>([])
const llmConfigs = ref<LlmConfigEntry[]>(
  PROVIDERS.map(p => ({ provider: p, keySource: 'none' as const, orgKeyId: '', personalKey: '' }))
)
const llmExpanded = ref(true)

function orgKeysForProvider(provider: string) {
  return availableOrgKeys.value.filter(k => k.provider === provider)
}

async function fetchAvailableKeys() {
  const orgId = authStore.user?.current_org_id
  if (!orgId) return
  try {
    const res = await api.get(`/orgs/${orgId}/available-llm-keys`)
    availableOrgKeys.value = res.data.data ?? []
  } catch {
    availableOrgKeys.value = []
  }
}

const storageAnchors = [20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200]
const storageLabels = [20, 60, 100, 150, 200]

const imageTags = ref<string[]>([])
const clusters = ref<{ id: string; name: string }[]>([])
const loadingInit = ref(true)
const loadingTags = ref(false)
const imageDropdownOpen = ref(false)

const specs = [
  { key: 'small', label: '轻量', desc: '写周报、查资料、日常问答', cpu: '2 核', mem: '4 GB' },
  { key: 'medium', label: '标准', desc: '代码审查、文档生成、会议纪要', cpu: '4 核', mem: '8 GB' },
  { key: 'large', label: '高性能', desc: '浏览器自动化、代码开发、数据分析', cpu: '8 核', mem: '16 GB' },
]

const specResources: Record<string, { cpu_req: string; cpu_lim: string; mem_req: string; mem_lim: string; quota_cpu: string; quota_mem: string; storage: number }> = {
  small: { cpu_req: '1000m', cpu_lim: '2000m', mem_req: '2Gi', mem_lim: '4Gi', quota_cpu: '2', quota_mem: '4Gi', storage: 20 },
  medium: { cpu_req: '2000m', cpu_lim: '4000m', mem_req: '4Gi', mem_lim: '8Gi', quota_cpu: '4', quota_mem: '8Gi', storage: 40 },
  large: { cpu_req: '4000m', cpu_lim: '8000m', mem_req: '8Gi', mem_lim: '16Gi', quota_cpu: '8', quota_mem: '16Gi', storage: 80 },
}

function selectSpec(key: string) {
  selectedSpec.value = key
  storageGi.value = specResources[key]?.storage ?? 40
}

const storageIndex = computed({
  get: () => {
    const idx = storageAnchors.indexOf(storageGi.value)
    return idx >= 0 ? idx : 0
  },
  set: (idx: number) => {
    storageGi.value = storageAnchors[idx] ?? storageAnchors[0]
  },
})

async function fetchImageTags() {
  loadingTags.value = true
  try {
    const res = await api.get('/registry/tags')
    const tags = (res.data.data ?? []) as { tag: string }[]
    imageTags.value = tags.map((t) => t.tag)
    if (imageTags.value.length > 0 && !selectedImage.value) {
      selectedImage.value = imageTags.value[0] ?? ''
    }
  } catch {
    imageTags.value = []
  } finally {
    loadingTags.value = false
  }
}

function selectImage(tag: string) {
  selectedImage.value = tag
  imageDropdownOpen.value = false
}

function toSlug(input: string): string {
  const hasChinese = /[\u4e00-\u9fa5]/.test(input)
  const raw = hasChinese
    ? pinyin(input, { toneType: 'none', type: 'array' }).join('-')
    : input
  return raw
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, '-')
    .replace(/-{2,}/g, '-')
    .replace(/^-|-$/g, '')
}

const slugValid = computed(() => /^[a-z][a-z0-9-]*[a-z0-9]$/.test(slug.value) && slug.value.length >= 2)

let slugCheckTimer: ReturnType<typeof setTimeout> | null = null

function debouncedSlugCheck() {
  slugConflict.value = false
  slugError.value = ''
  if (slugCheckTimer) clearTimeout(slugCheckTimer)
  if (!slug.value || !slugValid.value) return
  slugChecking.value = true
  slugCheckTimer = setTimeout(async () => {
    try {
      const res = await api.get('/instances/check-slug', { params: { slug: slug.value } })
      const data = res.data.data
      if (data?.conflict) {
        slugConflict.value = true
        slugError.value = data.reason || '该标识已被占用'
      }
    } catch {
      // ignore
    } finally {
      slugChecking.value = false
    }
  }, 400)
}

watch(name, (val) => {
  if (!slugManuallyEdited.value) {
    slug.value = toSlug(val)
    debouncedSlugCheck()
  }
})

watch(slug, () => {
  debouncedSlugCheck()
})

onMounted(async () => {
  try {
    const [, clustersRes] = await Promise.all([
      fetchImageTags(),
      api.get('/clusters'),
      fetchAvailableKeys(),
    ])
    clusters.value = (clustersRes.data.data ?? []).filter((c: any) => c.status === 'connected')
  } catch {
    // ignore init errors
  } finally {
    loadingInit.value = false
  }
})

const canDeploy = computed(() =>
  !!name.value.trim() && !!slug.value && slugValid.value && !slugConflict.value && !slugChecking.value
  && !!selectedImage.value && clusters.value.length > 0 && !deploying.value
)

async function handleDeploy() {
  if (!name.value.trim()) {
    error.value = '请输入实例名称'
    return
  }
  if (!selectedImage.value) {
    error.value = '请选择镜像版本'
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
    const activeLlm = llmConfigs.value
      .filter(c => c.keySource !== 'none')
      .map(c => ({
        provider: c.provider,
        key_source: c.keySource,
        org_llm_key_id: c.keySource === 'org' ? c.orgKeyId || undefined : undefined,
      }))

    const res = await api.post('/deploy', {
      name: name.value.trim(),
      slug: slug.value,
      cluster_id: clusters.value[0].id,
      image_version: selectedImage.value,
      replicas: 1,
      cpu_request: res_spec.cpu_req,
      cpu_limit: res_spec.cpu_lim,
      mem_request: res_spec.mem_req,
      mem_limit: res_spec.mem_lim,
      quota_cpu: res_spec.quota_cpu,
      quota_mem: res_spec.quota_mem,
      storage_size: `${storageGi.value}Gi`,
      description: description.value || undefined,
      llm_configs: activeLlm.length > 0 ? activeLlm : undefined,
    })

    const deployId = res.data.data?.deploy_id
    const instanceId = res.data.data?.instance_id
    if (deployId) {
      router.push({
        name: 'DeployProgress',
        params: { deployId },
        query: { name: name.value.trim(), instanceId: instanceId || '' },
      })
    } else {
      router.push('/instances')
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
    <div class="flex items-center gap-3 mb-8">
      <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" @click="router.push('/instances')">
        <ArrowLeft class="w-5 h-5" />
      </button>
      <div>
        <h1 class="text-xl font-bold">创建实例</h1>
        <p class="text-sm text-muted-foreground mt-1">只需几步即可部署你的 AI 助手</p>
      </div>
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
          placeholder="例如：我的AI助手"
          class="w-full px-4 py-2.5 rounded-lg bg-card border border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-colors"
        />
      </div>

      <!-- 实例标识 (slug) -->
      <div class="space-y-2">
        <div class="flex items-center gap-2">
          <label class="text-sm font-medium">实例标识</label>
          <span v-if="slug && !slugManuallyEdited" class="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">自动生成</span>
        </div>
        <div class="relative">
          <input
            v-model="slug"
            type="text"
            placeholder="例如：my-assistant"
            class="w-full px-4 py-2.5 rounded-lg bg-card border text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-colors"
            :class="slugError ? 'border-destructive' : slug && slugValid && !slugConflict ? 'border-green-500' : 'border-border'"
            @input="slugManuallyEdited = true"
          />
          <div v-if="slugChecking" class="absolute right-3 top-1/2 -translate-y-1/2">
            <Loader2 class="w-4 h-4 animate-spin text-muted-foreground" />
          </div>
          <div v-else-if="slug && slugValid && !slugConflict && !slugChecking" class="absolute right-3 top-1/2 -translate-y-1/2">
            <Check class="w-4 h-4 text-green-500" />
          </div>
        </div>
        <p v-if="slugError" class="text-xs text-destructive flex items-center gap-1">
          <AlertCircle class="w-3 h-3" />
          {{ slugError }}
        </p>
        <p v-else-if="slug && !slugValid" class="text-xs text-destructive flex items-center gap-1">
          <AlertCircle class="w-3 h-3" />
          须以小写字母开头，仅含小写字母、数字和连字符，至少 2 个字符
        </p>
        <p v-else class="text-xs text-muted-foreground">
          根据名称自动生成，也可手动修改
        </p>
      </div>

      <!-- 镜像版本 -->
      <div class="space-y-2">
        <div class="flex items-center justify-between">
          <label class="text-sm font-medium">镜像版本</label>
          <button
            class="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            :disabled="loadingTags"
            @click="fetchImageTags"
          >
            <RefreshCw class="w-3 h-3" :class="loadingTags ? 'animate-spin' : ''" />
            刷新
          </button>
        </div>
        <div v-if="imageTags.length > 0" class="relative">
          <button
            class="w-full flex items-center justify-between px-4 py-2.5 rounded-lg bg-card border border-border text-sm hover:border-primary/50 transition-colors text-left"
            @click="imageDropdownOpen = !imageDropdownOpen"
          >
            <span class="font-mono">{{ selectedImage || '选择版本' }}</span>
            <ChevronDown class="w-4 h-4 text-muted-foreground transition-transform" :class="imageDropdownOpen ? 'rotate-180' : ''" />
          </button>
          <div
            v-if="imageDropdownOpen"
            class="absolute z-10 mt-1 w-full max-h-48 overflow-y-auto rounded-lg border border-border bg-card shadow-lg"
          >
            <button
              v-for="tag in imageTags"
              :key="tag"
              class="w-full px-4 py-2 text-left text-sm font-mono hover:bg-accent transition-colors"
              :class="tag === selectedImage ? 'text-primary bg-primary/5' : 'text-foreground'"
              @click="selectImage(tag)"
            >
              {{ tag }}
              <span v-if="tag === imageTags[0]" class="ml-2 text-[10px] font-sans text-muted-foreground">(最新)</span>
            </button>
          </div>
        </div>
        <div v-else>
          <input
            v-model="selectedImage"
            type="text"
            :placeholder="loadingTags ? '加载中...' : '手动输入版本号'"
            class="w-full px-4 py-2.5 rounded-lg bg-card border border-border text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-colors"
          />
          <p class="text-xs text-muted-foreground mt-1">未获取到镜像仓库 Tag，请手动输入</p>
        </div>
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
            @click="selectSpec(spec.key)"
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

      <!-- 存储空间 -->
      <div class="space-y-3">
        <label class="text-sm font-medium flex items-center gap-1.5">
          <Database class="w-4 h-4 text-orange-400" />
          存储空间
        </label>
        <div class="space-y-2">
          <input
            type="range"
            :min="0"
            :max="storageAnchors.length - 1"
            :step="1"
            :value="storageIndex"
            class="w-full h-2 rounded-full appearance-none cursor-pointer accent-primary bg-muted"
            @input="(e: Event) => storageIndex = Number((e.target as HTMLInputElement).value)"
          />
          <div class="relative h-5 text-xs text-muted-foreground">
            <span
              v-for="(label, i) in storageLabels"
              :key="label"
              class="absolute cursor-pointer py-0.5 rounded transition-colors"
              :class="storageGi === label ? 'text-primary font-medium' : ''"
              :style="{
                left: (storageAnchors.indexOf(label) / (storageAnchors.length - 1) * 100) + '%',
                transform: i === 0 ? 'none' : i === storageLabels.length - 1 ? 'translateX(-100%)' : 'translateX(-50%)',
              }"
              @click="storageIndex = storageAnchors.indexOf(label)"
            >
              {{ label }}Gi
            </span>
          </div>
          <p class="text-xs text-muted-foreground">
            当前：<span class="font-medium text-foreground">{{ storageGi }}Gi</span>
          </p>
        </div>
      </div>

      <!-- 大模型配置 -->
      <div class="space-y-3">
        <button
          class="flex items-center gap-2 text-sm font-medium w-full text-left"
          @click="llmExpanded = !llmExpanded"
        >
          <Brain class="w-4 h-4 text-violet-400" />
          配置大模型
          <ChevronDown class="w-4 h-4 text-muted-foreground transition-transform ml-auto" :class="llmExpanded ? 'rotate-180' : ''" />
        </button>
        <p class="text-xs text-muted-foreground">
          OpenClaw 需要至少一个大模型 Key 才能正常使用，你也可以稍后在实例设置中配置
        </p>

        <div v-if="llmExpanded" class="space-y-3">
          <div
            v-for="cfg in llmConfigs"
            :key="cfg.provider"
            class="rounded-lg border border-border bg-card p-4 space-y-3"
          >
            <div class="font-medium text-sm">{{ PROVIDER_LABELS[cfg.provider] || cfg.provider }}</div>

            <div class="space-y-2">
              <label class="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="radio"
                  :name="`llm-${cfg.provider}`"
                  value="none"
                  v-model="cfg.keySource"
                  class="accent-primary"
                />
                <span class="text-muted-foreground">不使用</span>
              </label>

              <label
                v-if="orgKeysForProvider(cfg.provider).length > 0"
                class="flex items-center gap-2 text-sm cursor-pointer"
              >
                <input
                  type="radio"
                  :name="`llm-${cfg.provider}`"
                  value="org"
                  v-model="cfg.keySource"
                  class="accent-primary"
                />
                <span>使用组织 Key</span>
              </label>
              <select
                v-if="cfg.keySource === 'org' && orgKeysForProvider(cfg.provider).length > 0"
                v-model="cfg.orgKeyId"
                class="ml-6 w-[calc(100%-1.5rem)] px-3 py-1.5 rounded-md bg-background border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
              >
                <option value="" disabled>选择 Key</option>
                <option
                  v-for="k in orgKeysForProvider(cfg.provider)"
                  :key="k.id"
                  :value="k.id"
                >
                  {{ k.label }} ({{ k.api_key_masked }})
                </option>
              </select>

              <label class="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="radio"
                  :name="`llm-${cfg.provider}`"
                  value="personal"
                  v-model="cfg.keySource"
                  class="accent-primary"
                />
                <span>使用个人 Key</span>
              </label>
              <div v-if="cfg.keySource === 'personal'" class="ml-6">
                <div class="relative">
                  <Key class="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                  <input
                    v-model="cfg.personalKey"
                    type="password"
                    placeholder="输入 API Key"
                    class="w-full pl-9 pr-3 py-1.5 rounded-md bg-background border border-border text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary/50"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 部署 -->
      <div class="pt-4">
        <p v-if="error" class="text-sm text-destructive mb-3">{{ error }}</p>
        <button
          :disabled="!canDeploy"
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

  <!-- 点击外部关闭下拉框 -->
  <Teleport to="body">
    <div v-if="imageDropdownOpen" class="fixed inset-0 z-[5]" @click="imageDropdownOpen = false" />
  </Teleport>
</template>
