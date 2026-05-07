<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ArrowRight, Loader2, Rocket, Database, ChevronDown, RefreshCw, AlertCircle, Check, Brain, Key, Trash2, Plus, Star, X, Cpu, HardDrive, Zap, CheckCircle, XCircle, Server } from 'lucide-vue-next'
import ModelSelect from '@/components/shared/ModelSelect.vue'
import BaseUrlInput, { stripProtocol } from '@/components/shared/BaseUrlInput.vue'
import type { ModelItem } from '@/components/shared/ModelSelect.vue'
import { pinyin } from 'pinyin-pro'
import api from '@/services/api'
import { resolveApiErrorMessage } from '@/i18n/error'
import { useAuthStore } from '@/stores/auth'
import { useOrgStore } from '@/stores/org'
import { useI18n } from 'vue-i18n'
import { useEdition } from '@/composables/useFeature'
import { getRuntimeCaps } from '@/utils/runtimeCapabilities'
import { buildDefaultSpecPresets } from '@/utils/instanceFlow'
import {
  PROVIDERS, PROVIDER_LABELS, PROVIDER_DEFAULT_URLS,
  BUILTIN_PROVIDERS, ALL_KNOWN_PROVIDERS,
  isCodexProvider, DEFAULT_CODEX_MODEL, defaultModelForProvider,
} from '@/utils/llmProviders'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const orgStore = useOrgStore()
const { isEE } = useEdition()

const K8S_NAME_MAX = 63
const NS_PREFIX_BASE = 'nodeskclaw-'.length + 1
const DEPLOY_NAME_MAX = 35

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
const errorKey = ref('')
const currentStep = ref(1)

// ── Engine selector ──
interface EngineItem {
  runtime_id: string
  display_name: string
  display_description: string
  display_tags: string[]
  display_powered_by: string
  order: number
  available: boolean
}
const engines = ref<EngineItem[]>([])
const selectedRuntime = ref('openclaw')

// ── Template ──
import { useGeneStore } from '@/stores/gene'
import type { TemplateInfo } from '@/stores/gene'

const geneStore = useGeneStore()
const selectedTemplate = ref<TemplateInfo | null>(null)

const nameHasEdgeSpaces = computed(() => name.value.length > 0 && name.value !== name.value.trim())

const orgSlugLen = computed(() => orgStore.currentOrg?.slug?.length ?? 9)
const maxSlugInput = computed(() => {
  const nsMax = K8S_NAME_MAX - NS_PREFIX_BASE - orgSlugLen.value
  return Math.min(nsMax, DEPLOY_NAME_MAX) - 1 - randomSuffix.length
})
const slugTooLong = computed(() => fullSlug.value.length > 0 && (
  fullSlug.value.length + NS_PREFIX_BASE + orgSlugLen.value > K8S_NAME_MAX ||
  fullSlug.value.length > DEPLOY_NAME_MAX
))

const canGoNext = computed(() =>
  !!name.value.trim() && !nameHasEdgeSpaces.value
  && !!slug.value && slugValid.value && !slugConflict.value && !slugChecking.value && !slugTooLong.value
  && !!selectedImage.value && !!selectedCluster.value
)

// ── LLM config ──
interface LlmConfigEntry {
  provider: string
  keySource: 'org' | 'personal'
  personalKey: string
  baseUrl: string
  apiType: string
  isCustom: boolean
  showBaseUrl: boolean
  selectedModel: ModelItem | null
  skipSslVerify: boolean
}

const llmConfigs = ref<LlmConfigEntry[]>([])
const newProvider = ref('')
const customSlug = ref('')
const customSlugError = ref('')
const showCustomForm = ref(false)

const unusedProviders = computed(() =>
  PROVIDERS.filter(p => !llmConfigs.value.some(c => c.provider === p))
)

function addProvider(p: string) {
  if (!p) return
  const orgDetail = orgProviderDetails.value[p]
  llmConfigs.value.push({
    provider: p,
    keySource: isCodexProvider(p) ? 'personal' : (isOrgKeyAvailable(p) ? 'org' : 'personal'),
    personalKey: '',
    baseUrl: '',
    apiType: '',
    isCustom: false,
    showBaseUrl: false,
    selectedModel: defaultModelForProvider(p),
    skipSslVerify: orgDetail?.skip_ssl_verify ?? false,
  })
}

async function loadStorageClasses(clusterId: string) {
  const scRes = await api.get('/storage-classes', {
    params: {
      scope: 'all',
      cluster_id: clusterId,
    },
  })
  const items = (scRes.data.data ?? []) as StorageClassItem[]
  storageClasses.value = items
  const enabled = items.filter(sc => sc.enabled)
  const def = enabled.find(sc => sc.is_default) ?? enabled[0]
  selectedStorageClass.value = def?.name ?? null
}

function addCustomProvider() {
  const slug = customSlug.value.trim()
  if (!slug) return
  if (!/^[a-z][a-z0-9-]*[a-z0-9]$/.test(slug) || slug.length < 2 || slug.length > 32) {
    customSlugError.value = t('llm.providerSlugInvalid')
    return
  }
  if (ALL_KNOWN_PROVIDERS.has(slug) || llmConfigs.value.some(c => c.provider === slug)) {
    customSlugError.value = t('llm.providerSlugConflict')
    return
  }
  llmConfigs.value.push({
    provider: slug,
    keySource: 'personal',
    personalKey: '',
    baseUrl: '',
    apiType: 'openai-completions',
    isCustom: true,
    showBaseUrl: true,
    selectedModel: null,
    skipSslVerify: false,
  })
  customSlug.value = ''
  customSlugError.value = ''
  showCustomForm.value = false
}

function addOrgCustomProvider(orgProvider: any) {
  llmConfigs.value.push({
    provider: orgProvider.provider,
    keySource: 'org',
    personalKey: '',
    baseUrl: orgProvider.base_url || '',
    apiType: orgProvider.api_type || 'openai-completions',
    isCustom: true,
    showBaseUrl: true,
    selectedModel: null,
    skipSslVerify: orgProvider.skip_ssl_verify ?? false,
  })
}

const orgKeyProviders = ref<Set<string>>(new Set())
const orgAllowedModels = ref<Record<string, string[] | null>>({})
const orgProviderDetails = ref<Record<string, any>>({})

const isOrgKeyAvailable = (provider: string) =>
  orgKeyProviders.value.has(provider)

const orgCustomProviders = computed(() =>
  Object.values(orgProviderDetails.value)
    .filter((p: any) => !ALL_KNOWN_PROVIDERS.has(p.provider))
    .filter((p: any) => !llmConfigs.value.some(c => c.provider === p.provider)),
)

const orgKeyLabel = computed(() => isEE.value ? 'Working Plan' : t('llm.teamKey'))

async function handleFetchModels(provider: string, callback: (models: ModelItem[], error?: string) => void) {
  const cfg = llmConfigs.value.find(c => c.provider === provider)
  const params: Record<string, any> = {}
  if (cfg?.keySource === 'personal' && cfg.personalKey) {
    params.api_key = cfg.personalKey
  }
  if (cfg?.baseUrl) {
    params.base_url = cfg.baseUrl
  }
  if (cfg?.apiType) {
    params.api_type = cfg.apiType
  }
  if (cfg?.skipSslVerify) {
    params.skip_ssl_verify = true
  }
  if (authStore.user?.current_org_id) {
    params.org_id = authStore.user.current_org_id
  }
  try {
    const res = await api.get(`/llm/providers/${provider}/models`, { params })
    const msg = res.data?.message ?? ''
    let models: ModelItem[] = res.data.data?.models ?? []
    const allowed = orgAllowedModels.value[provider]
    if (allowed && allowed.length > 0) {
      const allowedSet = new Set(allowed)
      models = models.filter(m => allowedSet.has(m.id))
    }
    callback(models, msg || undefined)
  } catch (e: any) {
    callback([], e?.response?.data?.message ?? t('llm.fetchModelsFailed'))
  }
}

function removeProvider(idx: number) {
  llmConfigs.value.splice(idx, 1)
  delete testResults.value[idx]
}

const testingProvider = ref<number | null>(null)
const testResults = ref<Record<number, { ok: boolean; message: string; tested_model?: string | null; latency_ms?: number | null; error_detail?: string | null }>>({})

async function handleTestKey(idx: number) {
  const cfg = llmConfigs.value[idx]
  if (!cfg?.personalKey) return
  testingProvider.value = idx
  delete testResults.value[idx]
  try {
    const res = await api.post('/llm/test-connection', {
      provider: cfg.provider,
      api_key: cfg.personalKey,
      base_url: cfg.baseUrl || undefined,
      api_type: cfg.apiType || undefined,
      skip_ssl_verify: cfg.skipSslVerify,
      model: cfg.selectedModel?.id || undefined,
    })
    testResults.value[idx] = res.data.data
  } catch (e: any) {
    testResults.value[idx] = { ok: false, message: resolveApiErrorMessage(e) || t('llm.testKeyFailed') }
  } finally {
    testingProvider.value = null
  }
}

const storageAnchors = [20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200]
const storageLabels = [20, 60, 100, 150, 200]

interface EngineVersionItem {
  id: string
  image_tag: string
  version: string
  is_default: boolean
  release_notes: string | null
}
const engineVersions = ref<EngineVersionItem[]>([])
const imageTags = computed(() => engineVersions.value.map(v => v.image_tag))
const clusters = ref<{ id: string; name: string; compute_provider: string }[]>([])
const selectedCluster = ref('')
const clusterDropdownOpen = ref(false)
const loadingInit = ref(true)
const loadingTags = ref(false)
const imageDropdownOpen = ref(false)

interface StorageClassItem {
  name: string
  provisioner: string
  is_default: boolean
  enabled: boolean
}
const storageClasses = ref<StorageClassItem[]>([])
const selectedStorageClass = ref<string | null>(null)
const scDropdownOpen = ref(false)
const pvcAccessMode = ref<string>('ReadWriteOnce')

const selectedClusterObj = computed(() => clusters.value.find(c => c.id === selectedCluster.value))
const isK8sCluster = computed(() => selectedClusterObj.value?.compute_provider === 'k8s')
const enabledStorageClasses = computed(() => storageClasses.value.filter(sc => sc.enabled))
const showStorageClassSelector = computed(() => isK8sCluster.value)

interface SpecPreset {
  key: string
  label: string
  desc: string
  cpu: number
  memory: number
  storage: number
  cpu_request: string
  cpu_limit: string
  mem_request: string
  mem_limit: string
  quota_cpu: string
  quota_mem: string
}

const specPresets = ref<SpecPreset[]>(buildDefaultSpecPresets(t))
const presetsLoading = ref(true)

function selectSpec(key: string) {
  selectedSpec.value = key
  const found = specPresets.value.find(s => s.key === key)
  storageGi.value = found?.storage ?? 40
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
    const res = await api.get('/engine-versions', { params: { runtime: selectedRuntime.value } })
    const versions = (res.data.data ?? []) as EngineVersionItem[]
    engineVersions.value = versions
    if (versions.length > 0 && !selectedImage.value) {
      const defaultVersion = versions.find(v => v.is_default)
      selectedImage.value = defaultVersion?.image_tag ?? versions[0].image_tag ?? ''
    }
  } catch {
    engineVersions.value = []
  } finally {
    loadingTags.value = false
  }
}

function selectImage(tag: string) {
  selectedImage.value = tag
  imageDropdownOpen.value = false
}

function toSlug(input: string, maxLen?: number): string {
  const segments = input.match(/[\u4e00-\u9fa5]+|[^\u4e00-\u9fa5]+/g) || []
  const parts: string[] = []
  for (const seg of segments) {
    if (/[\u4e00-\u9fa5]/.test(seg)) {
      parts.push(...pinyin(seg, { toneType: 'none', type: 'array' }))
    } else {
      parts.push(seg.trim())
    }
  }
  let result = parts
    .filter(Boolean)
    .join('-')
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replace(/([A-Z]+)([A-Z][a-z])/g, '$1-$2')
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, '-')
    .replace(/-{2,}/g, '-')
    .replace(/^-|-$/g, '')
  if (maxLen && maxLen > 0 && result.length > maxLen) {
    result = result.slice(0, maxLen)
    const lastDash = result.lastIndexOf('-')
    if (lastDash > maxLen / 2) result = result.slice(0, lastDash)
    result = result.replace(/-+$/, '')
  }
  return result
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
        slugError.value = data.reason || t('createInstance.slugConflict')
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
    slug.value = toSlug(val, maxSlugInput.value)
    debouncedSlugCheck()
  }
})

watch(slug, () => {
  debouncedSlugCheck()
})

watch(selectedRuntime, () => {
  selectedImage.value = ''
  imageDropdownOpen.value = false
  fetchImageTags()
})

watch(selectedCluster, (id) => {
  const cluster = clusters.value.find(c => c.id === id)
  if (cluster?.compute_provider === 'k8s') {
    loadStorageClasses(id).catch(() => {})
  } else {
    storageClasses.value = []
    selectedStorageClass.value = null
  }
})

onMounted(async () => {
  try {
    const orgId = authStore.user?.current_org_id
    const fetches: Promise<any>[] = [
      api.get('/clusters'),
      api.get('/engines'),
    ]
    if (orgId) {
      fetches.push(api.get(`/orgs/${orgId}/model-providers/available`).catch(() => ({ data: { data: [] } })))
    }
    const [clustersRes, enginesRes, orgKeysRes] = await Promise.all(fetches)
    if (orgKeysRes) {
      const keys = orgKeysRes.data.data ?? []
      orgKeyProviders.value = new Set(keys.map((k: any) => k.provider))
      for (const k of keys) {
        orgAllowedModels.value[k.provider] = k.allowed_models ?? null
        orgProviderDetails.value[k.provider] = k
      }
    }
    engines.value = (enginesRes.data.data ?? []) as EngineItem[]
    if (engines.value.length > 0 && !engines.value.find(e => e.runtime_id === selectedRuntime.value)) {
      selectedRuntime.value = engines.value[0].runtime_id
    }
    clusters.value = (clustersRes.data.data ?? []).filter((c: any) => c.status === 'connected')
    const qCluster = route.query.cluster as string | undefined
    const matchedCluster = qCluster ? clusters.value.find(c => c.id === qCluster) : null
    selectedCluster.value = matchedCluster?.id ?? clusters.value[0]?.id ?? ''
    await fetchImageTags()

    try {
      const presetRes = await api.get('/spec-presets')
      const items = presetRes.data?.data
      if (Array.isArray(items) && items.length > 0) {
        specPresets.value = items
      }
    } catch {
      // API unavailable (old backend / network) — keep defaults
    } finally {
      presetsLoading.value = false
    }
    selectedSpec.value = specPresets.value[0]?.key ?? 'small'
    storageGi.value = specPresets.value[0]?.storage ?? 20
  } catch {
    // ignore init errors
  } finally {
    loadingInit.value = false
    presetsLoading.value = false
  }

  const qTemplateId = route.query.template_id as string | undefined
  if (qTemplateId) {
    try {
      await geneStore.fetchTemplate(qTemplateId)
      if (geneStore.currentTemplate) {
        selectedTemplate.value = geneStore.currentTemplate
      }
    } catch {
      // ignore
    }
  }
})

const runtimeHasLlm = computed(() => getRuntimeCaps(selectedRuntime.value).llmConfig)

function providerLabel(provider: string) {
  return PROVIDER_LABELS[provider] || provider
}

function getLlmDeployBlockReason(): string | null {
  if (!runtimeHasLlm.value) return null
  for (const c of llmConfigs.value) {
    const label = providerLabel(c.provider)
    if (c.isCustom) {
      if (!c.baseUrl?.trim()) {
        return t('createInstance.llmBlockCustomBaseUrl', { label })
      }
      if (c.keySource === 'personal' && !c.personalKey?.trim()) {
        return t('createInstance.llmBlockPersonalKey', { label })
      }
      if (!c.selectedModel) {
        return t('createInstance.llmBlockModel', { label })
      }
      continue
    }
    if (isCodexProvider(c.provider)) {
      if (!c.selectedModel) {
        return t('createInstance.llmBlockModel', { label })
      }
      continue
    }
    if (c.keySource === 'personal' && !c.personalKey?.trim()) {
      return t('createInstance.llmBlockPersonalKey', { label })
    }
    if (!c.selectedModel) {
      return t('createInstance.llmBlockModel', { label })
    }
  }
  return null
}

const llmReady = computed(() => getLlmDeployBlockReason() === null)

const canDeploy = computed(() =>
  !!name.value.trim() && !!slug.value && slugValid.value && !slugConflict.value && !slugChecking.value && !slugTooLong.value
  && !!selectedImage.value && !!selectedCluster.value && clusters.value.length > 0 && !deploying.value
)

function validateLlmConfigsBeforeDeploy(): string | null {
  return getLlmDeployBlockReason()
}

async function handleDeploy() {
  if (!name.value.trim()) {
    error.value = t('createInstance.nameRequired')
    return
  }
  if (!selectedImage.value) {
    error.value = t('createInstance.imageRequired')
    return
  }
  if (!selectedCluster.value || clusters.value.length === 0) {
    error.value = t('createInstance.noClusterError')
    return
  }
  const llmError = validateLlmConfigsBeforeDeploy()
  if (llmError) {
    error.value = llmError
    return
  }

  deploying.value = true
  error.value = ''

  const res_spec = specPresets.value.find(s => s.key === selectedSpec.value) ?? specPresets.value[0]

  try {
    for (const cfg of llmConfigs.value) {
      if (cfg.keySource === 'personal' && (cfg.personalKey || isCodexProvider(cfg.provider))) {
        await api.post('/users/me/llm-keys', {
          provider: cfg.provider,
          api_key: isCodexProvider(cfg.provider) ? undefined : cfg.personalKey,
          base_url: isCodexProvider(cfg.provider) ? null : (cfg.baseUrl || null),
          api_type: cfg.isCustom ? cfg.apiType : null,
          skip_ssl_verify: cfg.skipSslVerify,
        })
      }
    }

    const activeLlm = llmConfigs.value.map(c => {
      const selectedModel = c.selectedModel ?? defaultModelForProvider(c.provider)
      return {
        provider: c.provider,
        key_source: c.keySource,
        selected_models: selectedModel ? [selectedModel] : undefined,
        base_url: isCodexProvider(c.provider) ? null : (c.baseUrl || null),
        api_type: c.isCustom ? c.apiType : null,
      }
    })

    const res = await api.post('/deploy', {
      name: name.value.trim(),
      slug: fullSlug.value,
      cluster_id: selectedCluster.value,
      image_version: selectedImage.value,
      replicas: 1,
      cpu_request: res_spec.cpu_request,
      cpu_limit: res_spec.cpu_limit,
      mem_request: res_spec.mem_request,
      mem_limit: res_spec.mem_limit,
      quota_cpu: res_spec.quota_cpu,
      quota_mem: res_spec.quota_mem,
      storage_class: selectedStorageClass.value || undefined,
      storage_size: `${storageGi.value}Gi`,
      pvc_access_mode: pvcAccessMode.value,
      runtime: selectedRuntime.value,
      description: description.value || undefined,
      llm_configs: activeLlm.length > 0 ? activeLlm : undefined,
      template_id: selectedTemplate.value?.id || undefined,
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
    errorKey.value = e?.response?.data?.message_key || ''
    error.value = resolveApiErrorMessage(e, t('deployProgress.failedTitle'))
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
        <h1 class="text-xl font-bold">{{ t('createInstance.pageTitle') }}</h1>
        <p class="text-sm text-muted-foreground mt-0.5">{{ t('createInstance.pageSubtitle') }}</p>
      </div>
    </div>

    <!-- 无集群警告 -->
    <div
      v-if="!loadingInit && clusters.length === 0"
      class="flex items-center gap-3 p-4 rounded-lg border border-amber-500/30 bg-amber-500/5 mb-6"
    >
      <AlertCircle class="w-5 h-5 text-amber-500 shrink-0" />
      <div class="flex-1 text-sm">
        <span class="font-medium">{{ t('createInstance.noClusterTitle') }}</span>
        <span class="text-muted-foreground ml-1">
          {{ isEE ? t('createInstance.noClusterDescEE') : t('createInstance.noClusterDesc') }}
        </span>
      </div>
      <button
        v-if="!isEE"
        class="shrink-0 px-3 py-1.5 rounded-md bg-amber-500/10 text-amber-500 text-xs font-medium hover:bg-amber-500/20 transition-colors"
        @click="router.push('/org-settings/clusters')"
      >
        {{ t('createInstance.goSetupCluster') }}
      </button>
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
        {{ t('createInstance.stepBasicInfo') }}
      </button>
      <template v-if="runtimeHasLlm">
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
          {{ t('createInstance.stepLlmConfig') }}
        </button>
      </template>
    </div>

    <div v-if="loadingInit" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <template v-else>
      <!-- ══ Step 1: 基本信息 ══ -->
      <div v-if="currentStep === 1" class="space-y-8">
        <!-- 模板提示条 -->
        <div v-if="selectedTemplate" class="flex items-center gap-2 px-4 py-2.5 rounded-lg border border-primary/30 bg-primary/5 text-sm">
          <span class="text-primary font-medium">{{ t('template.creatingFrom', { name: selectedTemplate.name }) }}</span>
        </div>

        <!-- 名称 -->
        <div class="space-y-2">
          <label class="text-sm font-medium">{{ t('createInstance.nameLabel') }}</label>
          <input
            v-model="name"
            type="text"
            :placeholder="t('createInstance.namePlaceholder')"
            class="w-full px-4 py-2.5 rounded-lg bg-card border text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary transition-colors"
            :class="nameHasEdgeSpaces ? 'border-destructive' : 'border-border'"
          />
          <p v-if="nameHasEdgeSpaces" class="text-xs text-destructive flex items-center gap-1">
            <AlertCircle class="w-3 h-3" />
            {{ t('createInstance.nameTrimError') }}
          </p>
        </div>

        <!-- AI 员工标识 (slug) -->
        <div class="space-y-2">
          <div class="flex items-center gap-2">
            <label class="text-sm font-medium">{{ t('createInstance.slugLabel') }}</label>
            <span v-if="slug && !slugManuallyEdited" class="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">{{ t('createInstance.slugAutoGenerated') }}</span>
          </div>
          <div class="flex items-center gap-0">
            <div class="flex-1">
              <input
                v-model="slug"
                type="text"
                :placeholder="t('createInstance.slugPlaceholder')"
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
            {{ t('createInstance.slugRule') }}
          </p>
          <p v-else-if="slugTooLong" class="text-xs text-destructive flex items-center gap-1">
            <AlertCircle class="w-3 h-3" />
            {{ t('validation.instance.slug_too_long') }}
          </p>
          <p v-else class="text-xs text-muted-foreground">
            {{ t('createInstance.slugHint') }}
          </p>
        </div>

        <!-- 目标集群选择（多集群时显示） -->
        <div v-if="clusters.length > 1" class="space-y-2">
          <div class="flex items-center gap-2">
            <Server class="w-4 h-4 text-emerald-400" />
            <label class="text-sm font-medium">{{ t('createInstance.clusterLabel') }}</label>
          </div>
          <p class="text-xs text-muted-foreground">{{ t('createInstance.clusterHint') }}</p>
          <div class="relative">
            <button
              class="w-full flex items-center justify-between px-4 py-2.5 rounded-lg bg-card border border-border text-sm hover:border-primary/50 transition-colors text-left"
              @click="clusterDropdownOpen = !clusterDropdownOpen"
            >
              <span>{{ selectedClusterObj?.name || t('createInstance.clusterLabel') }}</span>
              <ChevronDown class="w-4 h-4 text-muted-foreground transition-transform" :class="clusterDropdownOpen ? 'rotate-180' : ''" />
            </button>
            <div
              v-if="clusterDropdownOpen"
              class="absolute z-10 mt-1 w-full max-h-48 overflow-y-auto rounded-lg border border-border bg-popover shadow-lg"
            >
              <button
                v-for="c in clusters"
                :key="c.id"
                class="w-full px-4 py-2.5 text-left text-sm hover:bg-accent transition-colors flex items-center justify-between"
                :class="c.id === selectedCluster ? 'text-primary bg-primary/5' : 'text-foreground'"
                @click="selectedCluster = c.id; clusterDropdownOpen = false"
              >
                <span>{{ c.name }}</span>
                <Check v-if="c.id === selectedCluster" class="w-4 h-4 text-primary shrink-0" />
              </button>
            </div>
          </div>
        </div>

        <!-- 工作引擎选择 -->
        <div class="space-y-3">
          <div class="flex items-center gap-2">
            <Cpu class="w-4 h-4 text-blue-400" />
            <label class="text-sm font-medium">{{ t('engine.title') }}</label>
          </div>
          <p class="text-xs text-muted-foreground">{{ t('engine.subtitle') }}</p>
          <div class="grid gap-3 items-start" :class="engines.length >= 3 ? 'grid-cols-3' : `grid-cols-${engines.length}`">
            <div
              v-for="eng in engines"
              :key="eng.runtime_id"
              :class="[
                'relative p-4 rounded-xl border text-left transition-all cursor-pointer',
                selectedRuntime === eng.runtime_id
                  ? 'border-primary bg-primary/5 ring-1 ring-primary/30'
                  : 'border-border bg-card hover:border-primary/20',
              ]"
              @click="selectedRuntime = eng.runtime_id"
            >
              <Check
                v-if="selectedRuntime === eng.runtime_id"
                class="absolute top-2.5 right-2.5 w-4 h-4 text-primary"
              />
              <div class="flex items-center gap-1.5">
                <span class="font-medium text-sm">{{ eng.display_name }}</span>
                <span
                  v-for="tag in eng.display_tags"
                  :key="tag"
                  class="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary"
                >{{ tag }}</span>
                <span
                  v-if="!eng.available"
                  class="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground"
                >{{ t('engine.comingSoon') }}</span>
              </div>
              <div class="text-xs text-muted-foreground mt-1.5 leading-relaxed">{{ eng.display_description }}</div>
              <div class="text-[10px] text-muted-foreground/60 mt-2">{{ t('engine.poweredBy') }} {{ eng.display_powered_by }}</div>

              <div v-if="selectedRuntime === eng.runtime_id" class="border-t border-border mt-3 pt-3" @click.stop>
                <div class="flex items-center justify-between mb-1.5">
                  <span class="text-xs font-medium text-muted-foreground">{{ t('engine.imageVersion') }}</span>
                  <button
                    class="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                    :disabled="loadingTags"
                    @click="fetchImageTags"
                  >
                    <RefreshCw class="w-3 h-3" :class="loadingTags ? 'animate-spin' : ''" />
                    {{ t('engine.refresh') }}
                  </button>
                </div>
                <div v-if="imageTags.length > 0" class="relative">
                  <button
                    class="w-full flex items-center justify-between px-3 py-2 rounded-lg bg-card border border-border text-sm hover:border-primary/50 transition-colors text-left"
                    @click="imageDropdownOpen = !imageDropdownOpen"
                  >
                    <span class="font-mono text-xs">{{ selectedImage || t('engine.selectVersion') }}</span>
                    <ChevronDown class="w-3.5 h-3.5 text-muted-foreground transition-transform" :class="imageDropdownOpen ? 'rotate-180' : ''" />
                  </button>
                  <div
                    v-if="imageDropdownOpen"
                    class="absolute z-10 mt-1 w-full max-h-48 overflow-y-auto rounded-lg border border-border bg-card shadow-lg"
                  >
                    <button
                      v-for="ev in engineVersions"
                      :key="ev.id"
                      class="w-full px-3 py-1.5 text-left text-xs font-mono hover:bg-accent transition-colors"
                      :class="ev.image_tag === selectedImage ? 'text-primary bg-primary/5' : 'text-foreground'"
                      @click="selectImage(ev.image_tag)"
                    >
                      {{ ev.image_tag }}
                      <span v-if="ev.is_default" class="ml-2 text-[10px] font-sans text-muted-foreground">({{ t('engine.defaultTag') }})</span>
                    </button>
                  </div>
                </div>
                <div v-else>
                  <p class="text-xs text-muted-foreground py-2">
                    {{ t('engine.noVersionsPublished') }}
                    <button
                      v-if="authStore.systemInfo?.edition !== 'ee'"
                      class="text-primary hover:underline ml-1"
                      @click="router.push({ name: 'OrgSettingsEngineVersions' })"
                    >{{ t('engine.goToVersionSettings') }}</button>
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 规格选择 -->
        <div class="space-y-3">
          <label class="text-sm font-medium">{{ t('createInstance.specLabel') }}</label>
          <div class="grid grid-cols-3 gap-3">
            <button
              v-for="spec in specPresets"
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
                <span>{{ spec.cpu }} {{ t('orgSettings.specsCpuUnit') }}</span>
                <span>{{ spec.memory }} GB</span>
              </div>
            </button>
          </div>
        </div>

        <!-- 存储空间 -->
        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <label class="text-sm font-medium flex items-center gap-1.5">
              <Database class="w-4 h-4 text-orange-400" />
              {{ t('createInstance.storageLabel') }}
            </label>
            <span class="text-sm text-muted-foreground">{{ t('createInstance.storageCurrent') }}<span class="font-medium text-foreground">{{ storageGi }}Gi</span></span>
          </div>

          <!-- StorageClass 选择器（K8s 集群始终显示） -->
          <div v-if="showStorageClassSelector" class="space-y-1.5">
            <div v-if="storageClasses.length === 0" class="flex items-start gap-1.5 text-xs text-amber-500">
              <AlertCircle class="w-3.5 h-3.5 shrink-0 mt-0.5" />
              <span>{{ t('engine.storageClassNone') }}</span>
            </div>
            <template v-else>
              <div v-if="enabledStorageClasses.length === 0" class="flex items-start gap-1.5 text-xs text-amber-500">
                <AlertCircle class="w-3.5 h-3.5 shrink-0 mt-0.5" />
                <span>{{ t('engine.storageClassNoneEnabled') }}</span>
              </div>
              <div class="relative">
                <div class="flex items-center gap-2">
                  <HardDrive class="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                  <span class="text-xs text-muted-foreground">{{ t('engine.storageClass') }}:</span>
                  <button
                    class="flex items-center gap-1 px-2 py-1 rounded-md border border-border bg-card text-xs font-mono hover:border-primary/40 transition-colors"
                    @click.stop="scDropdownOpen = !scDropdownOpen"
                  >
                    <span :class="selectedStorageClass ? '' : 'text-muted-foreground'">{{ selectedStorageClass || t('engine.storageClassPlaceholder') }}</span>
                    <span v-if="storageClasses.find(sc => sc.name === selectedStorageClass)?.is_default" class="text-muted-foreground">{{ t('engine.storageClassDefault') }}</span>
                    <ChevronDown class="w-3 h-3 text-muted-foreground" />
                  </button>
                </div>
                <div
                  v-if="scDropdownOpen"
                  class="absolute left-0 top-full mt-1 z-20 w-72 max-h-48 overflow-y-auto rounded-lg border border-border bg-popover shadow-lg"
                >
                  <button
                    v-for="sc in storageClasses"
                    :key="sc.name"
                    class="w-full text-left px-3 py-2 text-xs transition-colors flex items-center justify-between"
                    :class="[
                      sc.name === selectedStorageClass ? 'bg-accent/50' : '',
                      sc.enabled ? 'hover:bg-accent' : 'opacity-50 cursor-not-allowed',
                    ]"
                    :disabled="!sc.enabled"
                    @click="sc.enabled && (selectedStorageClass = sc.name, scDropdownOpen = false)"
                  >
                    <span class="flex flex-col">
                      <span class="font-mono">{{ sc.name }}<span v-if="sc.is_default" class="ml-1 text-muted-foreground">{{ t('engine.storageClassDefault') }}</span></span>
                      <span class="text-muted-foreground text-[10px]">{{ sc.provisioner }}</span>
                    </span>
                    <Check v-if="sc.name === selectedStorageClass" class="w-3.5 h-3.5 text-primary shrink-0" />
                    <span v-else-if="!sc.enabled" class="text-[10px] text-muted-foreground">{{ t('engine.storageClassDisabled') }}</span>
                  </button>
                </div>
              </div>
            </template>
          </div>

          <!-- PVC Access Mode 选择器（K8s 集群显示） -->
          <div v-if="showStorageClassSelector" class="space-y-1.5">
            <div class="flex items-center gap-2">
              <HardDrive class="w-3.5 h-3.5 text-muted-foreground shrink-0" />
              <span class="text-xs text-muted-foreground">{{ t('engine.pvcAccessMode') }}:</span>
            </div>
            <div class="flex gap-2">
              <button
                v-for="mode in ([
                  { value: 'ReadWriteOnce', label: t('engine.pvcAccessModeRWO'), desc: t('engine.pvcAccessModeRWODesc') },
                  { value: 'ReadWriteMany', label: t('engine.pvcAccessModeRWX'), desc: t('engine.pvcAccessModeRWXDesc') },
                ] as const)"
                :key="mode.value"
                class="flex-1 px-3 py-2 rounded-lg border text-left text-xs transition-colors"
                :class="pvcAccessMode === mode.value
                  ? 'border-primary bg-primary/5'
                  : 'border-border bg-card hover:border-primary/40'"
                @click="pvcAccessMode = mode.value"
              >
                <span class="font-medium" :class="pvcAccessMode === mode.value ? 'text-primary' : ''">{{ mode.label }}</span>
                <span class="block text-[10px] text-muted-foreground mt-0.5">{{ mode.desc }}</span>
              </button>
            </div>
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

        <!-- 下一步 / 直接部署 -->
        <div class="pt-4">
          <button
            v-if="runtimeHasLlm"
            :disabled="!canGoNext"
            class="w-full py-3 px-4 rounded-lg bg-primary text-primary-foreground font-medium text-sm hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            @click="currentStep = 2"
          >
            {{ t('createInstance.nextStep') }}
            <ArrowRight class="w-4 h-4" />
          </button>
          <button
            v-else
            :disabled="!canDeploy"
            class="w-full py-3 px-4 rounded-lg bg-primary text-primary-foreground font-medium text-sm hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            @click="handleDeploy"
          >
            <Loader2 v-if="deploying" class="w-4 h-4 animate-spin" />
            <Rocket v-else class="w-4 h-4" />
            {{ deploying ? t('createInstance.deploying') : t('createInstance.deployButton') }}
          </button>
        </div>
      </div>

      <!-- ══ Step 2: 大模型配置 ══ -->
      <div v-if="runtimeHasLlm && currentStep === 2" class="space-y-6">
        <div class="space-y-3">
          <div class="flex items-center gap-2">
            <Brain class="w-4 h-4 text-violet-400" />
            <label class="text-sm font-medium">{{ t('createInstance.stepLlmConfig') }}</label>
          </div>
          <p class="text-xs text-muted-foreground">
            {{ t('llm.providerOptionalHint') }}
          </p>

            <!-- 已添加的 Provider -->
            <div v-for="(cfg, idx) in llmConfigs" :key="cfg.provider" class="rounded-lg border border-border bg-card p-4 space-y-3">
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <span class="font-medium text-sm">{{ PROVIDER_LABELS[cfg.provider] || cfg.provider }}</span>
                  <span v-if="cfg.isCustom" class="text-[10px] px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-400">{{ t('llm.customProvider') }}</span>
                  <span v-else-if="cfg.keySource === 'org' && isOrgKeyAvailable(cfg.provider)" class="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-500">
                    {{ orgKeyLabel }}
                  </span>
                </div>
                <button class="text-muted-foreground hover:text-destructive transition-colors" @click="removeProvider(idx)">
                  <Trash2 class="w-4 h-4" />
                </button>
              </div>

              <!-- API type selector (custom only) -->
              <div v-if="cfg.isCustom" class="flex gap-4 text-sm">
                <label class="text-xs text-muted-foreground">{{ t('llm.apiType') }}:</label>
                <template v-if="cfg.keySource === 'org'">
                  <span class="text-xs">{{ cfg.apiType === 'anthropic-messages' ? t('llm.apiTypeAnthropic') : t('llm.apiTypeOpenai') }}</span>
                </template>
                <template v-else>
                  <label class="flex items-center gap-1.5 cursor-pointer text-xs">
                    <input type="radio" :name="`apitype-${cfg.provider}`" value="openai-completions" v-model="cfg.apiType" class="accent-primary" />
                    {{ t('llm.apiTypeOpenai') }}
                  </label>
                  <label class="flex items-center gap-1.5 cursor-pointer text-xs">
                    <input type="radio" :name="`apitype-${cfg.provider}`" value="anthropic-messages" v-model="cfg.apiType" class="accent-primary" />
                    {{ t('llm.apiTypeAnthropic') }}
                  </label>
                </template>
              </div>

              <div class="space-y-2">
                <div v-if="(!cfg.isCustom || isOrgKeyAvailable(cfg.provider)) && !isCodexProvider(cfg.provider)" class="flex gap-4 text-sm">
                  <span class="relative group">
                    <label
                      class="flex items-center gap-1.5"
                      :class="isOrgKeyAvailable(cfg.provider) ? 'cursor-pointer' : 'cursor-not-allowed opacity-50'"
                    >
                      <input type="radio" :name="`llm-${cfg.provider}`" value="org" v-model="cfg.keySource" class="accent-primary" :disabled="!isOrgKeyAvailable(cfg.provider)" />
                      {{ orgKeyLabel }}
                    </label>
                    <span
                      v-if="!isOrgKeyAvailable(cfg.provider)"
                      class="pointer-events-none absolute z-50 top-full left-0 mt-1.5 whitespace-nowrap rounded bg-popover px-2 py-1 text-xs text-popover-foreground shadow-md border border-border invisible group-hover:visible"
                    >
                      {{ t('llm.orgKeyNotConfigured') }}
                    </span>
                  </span>
                  <label class="flex items-center gap-1.5 cursor-pointer">
                    <input type="radio" :name="`llm-${cfg.provider}`" value="personal" v-model="cfg.keySource" class="accent-primary" />
                    {{ t('llm.personalKey') }}
                  </label>
                </div>

                <p v-else-if="isCodexProvider(cfg.provider)" class="text-xs text-muted-foreground pl-0.5">
                  {{ t('llm.codexCliHint') }}
                </p>

                <p v-if="cfg.keySource === 'org' && (!cfg.isCustom || isOrgKeyAvailable(cfg.provider))" class="text-xs text-muted-foreground pl-0.5">
                  {{ t('llm.orgKeyHint') }}
                </p>

                <div v-if="cfg.keySource === 'personal'" class="space-y-2">
                  <div v-if="isCodexProvider(cfg.provider)" class="rounded-md border border-border bg-background px-3 py-2 text-xs text-muted-foreground">
                    {{ t('llm.codexCliRuntimeHint') }}
                  </div>
                  <template v-else>
                    <div class="flex items-center gap-2">
                      <div class="relative flex-1">
                        <Key class="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                        <input
                          v-model="cfg.personalKey"
                          type="password"
                          :placeholder="t('createInstance.apiKeyPlaceholder')"
                          class="w-full pl-9 pr-3 py-1.5 rounded-md bg-background border border-border text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary/50"
                        />
                      </div>
                      <button
                        v-if="cfg.personalKey"
                        class="shrink-0 flex items-center gap-1 px-2 py-1.5 rounded-md border border-border text-xs hover:bg-muted transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        :disabled="testingProvider === idx"
                        @click="handleTestKey(idx)"
                      >
                        <Loader2 v-if="testingProvider === idx" class="w-3.5 h-3.5 animate-spin" />
                        <Zap v-else class="w-3.5 h-3.5" />
                        {{ t('llm.testKey') }}
                      </button>
                      <span v-if="testResults[idx]?.ok" class="shrink-0 flex items-center gap-1 text-xs text-green-500">
                        <CheckCircle class="w-3.5 h-3.5" />
                        {{ testResults[idx].tested_model ? t('llm.testConnectionModel', { model: testResults[idx].tested_model }) : t('llm.testKeyAvailable') }}
                        <template v-if="testResults[idx].latency_ms != null"> / {{ testResults[idx].latency_ms }}ms</template>
                      </span>
                      <span v-else-if="testResults[idx] && !testResults[idx].ok" class="shrink-0 flex items-center gap-1 text-xs text-destructive">
                        <XCircle class="w-3.5 h-3.5 shrink-0" />
                        {{ t('llm.testKeyFailed') }}
                      </span>
                    </div>
                    <div v-if="testResults[idx] && !testResults[idx]?.ok" class="mt-1 px-2 py-1.5 rounded bg-destructive/5 text-xs text-destructive">
                      {{ testResults[idx].message }}
                    </div>

                    <div v-if="cfg.isCustom || cfg.showBaseUrl">
                      <BaseUrlInput
                        v-model="cfg.baseUrl"
                        :placeholder="cfg.isCustom ? t('llm.baseUrlPlaceholder') : t('llm.defaultBaseUrl', { url: stripProtocol(PROVIDER_DEFAULT_URLS[cfg.provider] || '') })"
                        :show-clear="!cfg.isCustom"
                        @clear="cfg.baseUrl = ''; cfg.showBaseUrl = false"
                      />
                      <label v-if="cfg.baseUrl" class="flex items-center gap-2 mt-1.5 cursor-pointer">
                        <input type="checkbox" v-model="cfg.skipSslVerify" class="accent-primary" />
                        <span class="text-xs">{{ t('orgSettings.llmKeysSkipSslVerify') }}</span>
                        <span class="text-xs text-muted-foreground">{{ t('orgSettings.llmKeysSkipSslVerifyHint') }}</span>
                      </label>
                    </div>
                    <button
                      v-if="!cfg.isCustom && !cfg.showBaseUrl"
                      class="text-xs text-muted-foreground hover:text-foreground transition-colors"
                      @click="cfg.showBaseUrl = true"
                    >
                      {{ t('llm.customBaseUrl') }}
                    </button>
                  </template>
                </div>
              </div>

              <!-- Model selection -->
              <ModelSelect
                :provider="cfg.provider"
                v-model="cfg.selectedModel"
                allow-manual-input
                @fetch-models="handleFetchModels"
              />
              <p v-if="!cfg.selectedModel" class="text-[10px] text-amber-500">
                {{ t('llm.modelRequired') }}
              </p>
            </div>

            <!-- 选择 Provider -->
            <div v-if="unusedProviders.length > 0" class="space-y-2">
              <div class="grid grid-cols-2 gap-2">
                <button
                  v-for="p in unusedProviders"
                  :key="p"
                  class="px-4 py-3 rounded-lg border border-border bg-card text-sm text-left hover:border-primary/50 hover:bg-primary/5 transition-colors"
                  @click="addProvider(p)"
                >
                  <div class="flex items-center gap-1.5">
                    {{ PROVIDER_LABELS[p] || p }}
                    <span v-if="orgKeyProviders.has(p)" class="inline-flex items-center gap-0.5 text-[10px] text-amber-500">
                      <Star class="w-3 h-3 fill-amber-500 text-amber-500" />
                      {{ orgKeyLabel }}
                    </span>
                  </div>
                </button>
                <button
                  v-for="ocp in orgCustomProviders"
                  :key="ocp.provider"
                  class="px-4 py-3 rounded-lg border border-border bg-card text-sm text-left hover:border-primary/50 hover:bg-primary/5 transition-colors"
                  @click="addOrgCustomProvider(ocp)"
                >
                  <div class="flex items-center gap-1.5">
                    {{ ocp.label || ocp.provider }}
                    <span class="inline-flex items-center gap-0.5 text-[10px] text-amber-500">
                      <Star class="w-3 h-3 fill-amber-500 text-amber-500" />
                      {{ orgKeyLabel }}
                    </span>
                  </div>
                </button>
                <button
                  class="px-4 py-3 rounded-lg border border-dashed border-violet-400/50 bg-card text-sm text-left hover:border-violet-400 hover:bg-violet-500/5 transition-colors text-violet-400"
                  @click="showCustomForm = true"
                >
                  <div class="flex items-center gap-1.5">
                    <Plus class="w-3.5 h-3.5" />
                    {{ t('llm.addCustomProvider') }}
                  </div>
                </button>
              </div>
            </div>

            <!-- 自定义 Provider 表单 -->
            <div v-if="showCustomForm" class="rounded-lg border border-violet-400/30 bg-violet-500/5 p-4 space-y-3">
              <div class="flex items-center justify-between">
                <span class="font-medium text-sm text-violet-400">{{ t('llm.customProvider') }}</span>
                <button class="text-muted-foreground hover:text-foreground text-xs" @click="showCustomForm = false; customSlug = ''; customSlugError = ''">
                  {{ t('common.cancel') }}
                </button>
              </div>
              <div class="space-y-1.5">
                <label class="text-xs text-muted-foreground">{{ t('llm.providerSlug') }}</label>
                <input
                  v-model="customSlug"
                  type="text"
                  maxlength="32"
                  :placeholder="t('llm.providerSlugPlaceholder')"
                  class="w-full px-3 py-1.5 rounded-md bg-background border border-border text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary/50"
                  @keydown.enter="addCustomProvider"
                />
                <p v-if="customSlugError" class="text-[10px] text-destructive">{{ customSlugError }}</p>
                <p v-else class="text-[10px] text-muted-foreground">{{ t('llm.providerSlugHint') }}</p>
              </div>
              <button
                class="px-4 py-1.5 rounded-md bg-violet-500/10 text-violet-400 text-sm hover:bg-violet-500/20 transition-colors"
                :disabled="!customSlug.trim()"
                @click="addCustomProvider"
              >
                {{ t('common.add') }}
              </button>
            </div>
        </div>

        <!-- 部署 -->
        <div class="pt-4 space-y-3">
          <div v-if="error" class="flex items-start gap-2.5 p-3 rounded-lg bg-destructive/10 border border-destructive/20">
            <AlertCircle class="w-4 h-4 text-destructive shrink-0 mt-0.5" />
            <div class="flex-1 space-y-1.5">
              <p class="text-sm text-destructive leading-relaxed">{{ error }}</p>
              <template v-if="errorKey === 'errors.deploy.ingress_base_domain_required'">
                <p class="text-xs text-muted-foreground leading-relaxed">
                  {{ t('errors.deploy.ingress_base_domain_hint') }}
                </p>
                <router-link
                  v-if="authStore.user?.portal_org_role === 'admin'"
                  to="/org-settings/network"
                  class="text-xs text-primary hover:underline"
                >
                  {{ t('errors.deploy.ingress_base_domain_go_configure') }}
                </router-link>
              </template>
            </div>
          </div>
          <button
            :disabled="!canDeploy"
            class="w-full py-3 px-4 rounded-lg bg-primary text-primary-foreground font-medium text-sm hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            @click="handleDeploy"
          >
            <Loader2 v-if="deploying" class="w-4 h-4 animate-spin" />
            <Rocket v-else class="w-4 h-4" />
            {{ deploying ? t('createInstance.deploying') : t('createInstance.deployNow') }}
          </button>
        </div>
      </div>
    </template>
  </div>

  <!-- 点击外部关闭下拉框 -->
  <Teleport to="body">
    <div v-if="imageDropdownOpen || scDropdownOpen || clusterDropdownOpen" class="fixed inset-0 z-5" @click="imageDropdownOpen = false; scDropdownOpen = false; clusterDropdownOpen = false" />
  </Teleport>
</template>
