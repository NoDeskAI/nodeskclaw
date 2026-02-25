<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, ArrowRight, Loader2, Rocket, Database, ChevronDown, RefreshCw, AlertCircle, Check, Brain, Key, Trash2 } from 'lucide-vue-next'
import ModelSelect from '@/components/shared/ModelSelect.vue'
import type { ModelItem } from '@/components/shared/ModelSelect.vue'
import { pinyin } from 'pinyin-pro'
import api from '@/services/api'
import { resolveApiErrorMessage } from '@/i18n/error'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const name = ref('')
const slug = ref('')
const randomSuffix = Math.random().toString(36).slice(2, 8)
const fullSlug = computed(() => slug.value ? `${slug.value}-${randomSuffix}` : '')
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
const currentStep = ref(1)

const nameHasEdgeSpaces = computed(() => name.value.length > 0 && name.value !== name.value.trim())

const canGoNext = computed(() =>
  !!name.value.trim() && !nameHasEdgeSpaces.value
  && !!slug.value && slugValid.value && !slugConflict.value && !slugChecking.value
  && !!selectedImage.value && clusters.value.length > 0
)

// ── LLM config ──
interface LlmConfigEntry {
  provider: string
  keySource: 'org' | 'personal'
  personalKey: string
  selectedModel: ModelItem | null
}

const PROVIDERS = ['openai', 'anthropic', 'gemini', 'openrouter', 'minimax-openai', 'minimax-anthropic'] as const
const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  gemini: 'Google Gemini',
  openrouter: 'OpenRouter',
  'minimax-openai': 'MiniMax-OpenAI (CN)',
  'minimax-anthropic': 'MiniMax-Anthropic (CN)',
}

const llmConfigs = ref<LlmConfigEntry[]>([])
const llmSkipped = ref(false)
const newProvider = ref('')

const unusedProviders = computed(() =>
  PROVIDERS.filter(p => !llmConfigs.value.some(c => c.provider === p))
)

function addProvider() {
  if (!newProvider.value) return
  llmConfigs.value.push({
    provider: newProvider.value,
    keySource: WORKING_PLAN_PROVIDERS.has(newProvider.value) ? 'org' : 'personal',
    personalKey: '',
    selectedModel: null,
  })
  newProvider.value = ''
}

const BUILTIN_PROVIDERS = new Set(['openai', 'anthropic', 'gemini', 'openrouter'])
const WORKING_PLAN_PROVIDERS = new Set(['minimax-openai', 'minimax-anthropic'])

async function handleFetchModels(provider: string, callback: (models: ModelItem[], error?: string) => void) {
  const cfg = llmConfigs.value.find(c => c.provider === provider)
  const params: Record<string, string> = {}
  if (cfg?.keySource === 'personal' && cfg.personalKey) {
    params.api_key = cfg.personalKey
  }
  if (authStore.user?.current_org_id) {
    params.org_id = authStore.user.current_org_id
  }
  try {
    const res = await api.get(`/llm/providers/${provider}/models`, { params })
    const msg = res.data?.message ?? ''
    callback(res.data.data?.models ?? [], msg || undefined)
  } catch (e: any) {
    callback([], e?.response?.data?.message ?? '拉取模型列表失败')
  }
}

function removeProvider(idx: number) {
  llmConfigs.value.splice(idx, 1)
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
  const segments = input.match(/[\u4e00-\u9fa5]+|[^\u4e00-\u9fa5]+/g) || []
  const parts: string[] = []
  for (const seg of segments) {
    if (/[\u4e00-\u9fa5]/.test(seg)) {
      parts.push(...pinyin(seg, { toneType: 'none', type: 'array' }))
    } else {
      parts.push(seg.trim())
    }
  }
  return parts
    .filter(Boolean)
    .join('-')
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replace(/([A-Z]+)([A-Z][a-z])/g, '$1-$2')
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
      const res = await api.get('/instances/check-slug', { params: { slug: fullSlug.value } })
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
    ])
    clusters.value = (clustersRes.data.data ?? []).filter((c: any) => c.status === 'connected')
  } catch {
    // ignore init errors
  } finally {
    loadingInit.value = false
  }
})

const llmReady = computed(() => {
  if (llmSkipped.value) return true
  if (llmConfigs.value.length === 0) return false
  return llmConfigs.value.every(c =>
    BUILTIN_PROVIDERS.has(c.provider) || !!c.selectedModel
  )
})

const canDeploy = computed(() =>
  !!name.value.trim() && !!slug.value && slugValid.value && !slugConflict.value && !slugChecking.value
  && !!selectedImage.value && clusters.value.length > 0 && !deploying.value
  && llmReady.value
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
    const activeLlm = llmConfigs.value.map(c => ({
      provider: c.provider,
      key_source: c.keySource,
      selected_models: c.selectedModel ? [c.selectedModel] : undefined,
    }))

    const res = await api.post('/deploy', {
      name: name.value.trim(),
      slug: fullSlug.value,
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
    error.value = resolveApiErrorMessage(e, '部署失败')
  } finally {
    deploying.value = false
  }
}
</script>

<template>
  <div class="max-w-2xl mx-auto px-6 py-8">
    <div class="flex items-center gap-3 mb-6">
      <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" @click="currentStep === 1 ? router.push('/instances') : currentStep = 1">
        <ArrowLeft class="w-5 h-5" />
      </button>
      <div>
        <h1 class="text-xl font-bold">创建实例</h1>
        <p class="text-sm text-muted-foreground mt-0.5">只需几步即可部署你的 AI 助手</p>
      </div>
    </div>

    <!-- 步骤指示器 -->
    <div class="flex items-center gap-3 mb-8">
      <button
        class="flex items-center gap-2 text-sm transition-colors"
        :class="currentStep === 1 ? 'text-primary font-medium' : 'text-muted-foreground hover:text-foreground'"
        @click="currentStep = 1"
      >
        <span
          class="w-6 h-6 rounded-full text-xs flex items-center justify-center font-medium transition-colors"
          :class="currentStep >= 1 ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'"
        >1</span>
        基本信息
      </button>
      <div class="flex-1 h-px" :class="currentStep >= 2 ? 'bg-primary' : 'bg-border'" />
      <button
        class="flex items-center gap-2 text-sm transition-colors"
        :class="currentStep === 2 ? 'text-primary font-medium' : 'text-muted-foreground'"
        :disabled="!canGoNext"
        @click="canGoNext && (currentStep = 2)"
      >
        <span
          class="w-6 h-6 rounded-full text-xs flex items-center justify-center font-medium transition-colors"
          :class="currentStep >= 2 ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'"
        >2</span>
        大模型配置
      </button>
    </div>

    <div v-if="loadingInit" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <template v-else>
      <!-- ══ Step 1: 基本信息 ══ -->
      <div v-if="currentStep === 1" class="space-y-8">
        <!-- 名称 -->
        <div class="space-y-2">
          <label class="text-sm font-medium">给你的 AI 助手取个名字</label>
          <input
            v-model="name"
            type="text"
            placeholder="例如：我的AI助手"
            class="w-full px-4 py-2.5 rounded-lg bg-card border text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-colors"
            :class="nameHasEdgeSpaces ? 'border-destructive' : 'border-border'"
          />
          <p v-if="nameHasEdgeSpaces" class="text-xs text-destructive flex items-center gap-1">
            <AlertCircle class="w-3 h-3" />
            名称开头和结尾不能包含空格
          </p>
        </div>

        <!-- 实例标识 + 镜像版本 -->
        <div class="grid grid-cols-2 gap-4">
          <!-- 实例标识 (slug) -->
          <div class="space-y-2">
            <div class="flex items-center gap-2">
              <label class="text-sm font-medium">实例标识</label>
              <span v-if="slug && !slugManuallyEdited" class="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">自动生成</span>
            </div>
            <div class="flex items-center gap-0">
              <div class="flex-1">
                <input
                  v-model="slug"
                  type="text"
                  placeholder="例如：my-assistant"
                  class="w-full px-4 py-2.5 rounded-l-lg bg-card border text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-colors"
                  :class="slugError ? 'border-destructive' : slug && slugValid && !slugConflict ? 'border-green-500' : 'border-border'"
                  @input="slugManuallyEdited = true"
                />
              </div>
              <span class="h-[42px] flex items-center gap-1.5 px-2.5 rounded-r-lg border border-l-0 border-border bg-muted text-sm font-mono text-muted-foreground select-none whitespace-nowrap">
                -{{ randomSuffix }}
                <Loader2 v-if="slugChecking" class="w-4 h-4 animate-spin text-muted-foreground" />
                <Check v-else-if="slug && slugValid && !slugConflict && !slugChecking" class="w-4 h-4 text-green-500" />
              </span>
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
          <div class="flex items-center justify-between">
            <label class="text-sm font-medium flex items-center gap-1.5">
              <Database class="w-4 h-4 text-orange-400" />
              存储空间
            </label>
            <span class="text-sm text-muted-foreground">当前：<span class="font-medium text-foreground">{{ storageGi }}Gi</span></span>
          </div>
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
          </div>
        </div>

        <!-- 下一步 -->
        <div class="pt-4">
          <button
            :disabled="!canGoNext"
            class="w-full py-3 px-4 rounded-lg bg-primary text-primary-foreground font-medium text-sm hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            @click="currentStep = 2"
          >
            下一步
            <ArrowRight class="w-4 h-4" />
          </button>
        </div>
      </div>

      <!-- ══ Step 2: 大模型配置 ══ -->
      <div v-if="currentStep === 2" class="space-y-6">
        <div class="space-y-3">
          <div class="flex items-center gap-2">
            <Brain class="w-4 h-4 text-violet-400" />
            <label class="text-sm font-medium">配置大模型</label>
          </div>
          <p class="text-xs text-muted-foreground">
            OpenClaw 需要至少一个大模型 API Key 才能正常使用
          </p>

          <template v-if="!llmSkipped">
            <!-- 已添加的 Provider -->
            <div v-for="(cfg, idx) in llmConfigs" :key="cfg.provider" class="rounded-lg border border-border bg-card p-4 space-y-3">
              <div class="flex items-center justify-between">
                <span class="font-medium text-sm">{{ PROVIDER_LABELS[cfg.provider] || cfg.provider }}</span>
                <button class="text-muted-foreground hover:text-destructive transition-colors" @click="removeProvider(idx)">
                  <Trash2 class="w-4 h-4" />
                </button>
              </div>

              <div class="space-y-2">
                <div class="flex gap-4 text-sm">
                  <label
                    class="flex items-center gap-1.5"
                    :class="WORKING_PLAN_PROVIDERS.has(cfg.provider) ? 'cursor-pointer' : 'cursor-not-allowed opacity-50'"
                    :title="WORKING_PLAN_PROVIDERS.has(cfg.provider) ? '' : '暂未开放'"
                  >
                    <input type="radio" :name="`llm-${cfg.provider}`" value="org" v-model="cfg.keySource" class="accent-primary" :disabled="!WORKING_PLAN_PROVIDERS.has(cfg.provider)" />
                    Working Plan
                  </label>
                  <label class="flex items-center gap-1.5 cursor-pointer">
                    <input type="radio" :name="`llm-${cfg.provider}`" value="personal" v-model="cfg.keySource" class="accent-primary" />
                    个人 Key
                  </label>
                </div>

                <p v-if="cfg.keySource === 'org'" class="text-xs text-muted-foreground pl-0.5">
                  使用组织统一配置的 Key，无需自行输入
                </p>

                <div v-if="cfg.keySource === 'personal'" class="relative">
                  <Key class="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                  <input
                    v-model="cfg.personalKey"
                    type="password"
                    placeholder="输入 API Key"
                    class="w-full pl-9 pr-3 py-1.5 rounded-md bg-background border border-border text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary/50"
                  />
                </div>
              </div>

              <!-- Model selection -->
              <ModelSelect
                :provider="cfg.provider"
                v-model="cfg.selectedModel"
                @fetch-models="handleFetchModels"
              />
              <p v-if="!BUILTIN_PROVIDERS.has(cfg.provider) && !cfg.selectedModel" class="text-[10px] text-amber-500">
                自定义 Provider 需要选择一个模型
              </p>
            </div>

            <!-- 选择 Provider -->
            <div v-if="llmConfigs.length === 0 && unusedProviders.length > 0" class="space-y-2">
              <p class="text-xs text-muted-foreground">选择你使用的大模型服务商</p>
              <div class="grid grid-cols-2 gap-2">
                <button
                  v-for="p in unusedProviders"
                  :key="p"
                  class="px-4 py-3 rounded-lg border border-border bg-card text-sm text-left hover:border-primary/50 hover:bg-primary/5 transition-colors"
                  @click="newProvider = p; addProvider()"
                >
                  {{ PROVIDER_LABELS[p] || p }}
                </button>
              </div>
            </div>
          </template>

          <p v-else class="text-xs text-muted-foreground italic">
            已跳过大模型配置，创建后可在实例设置中配置
            <button class="text-primary ml-1 not-italic" @click="llmSkipped = false">撤销</button>
          </p>
        </div>

        <!-- 部署 -->
        <div class="pt-4 space-y-3">
          <p v-if="error" class="text-sm text-destructive">{{ error }}</p>
          <button
            :disabled="!canDeploy"
            class="w-full py-3 px-4 rounded-lg bg-primary text-primary-foreground font-medium text-sm hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            @click="handleDeploy"
          >
            <Loader2 v-if="deploying" class="w-4 h-4 animate-spin" />
            <Rocket v-else class="w-4 h-4" />
            {{ deploying ? '部署中...' : '部署' }}
          </button>
          <button
            v-if="!llmSkipped"
            class="w-full py-2.5 px-4 rounded-lg border border-border text-sm text-muted-foreground hover:text-foreground hover:border-foreground/20 transition-colors text-center"
            @click="llmSkipped = true; llmConfigs.splice(0); handleDeploy()"
          >
            跳过，稍后配置大模型
          </button>
        </div>
      </div>
    </template>
  </div>

  <!-- 点击外部关闭下拉框 -->
  <Teleport to="body">
    <div v-if="imageDropdownOpen" class="fixed inset-0 z-5" @click="imageDropdownOpen = false" />
  </Teleport>
</template>
