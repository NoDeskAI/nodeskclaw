<script setup lang="ts">
import { ref, computed, watch, inject, type ComputedRef, type Ref } from 'vue'
import { Loader2, Brain, Key, Trash2, Plus, RefreshCw, HardDrive, Save, ChevronDown, Check, Star, X, AlertTriangle, Zap, CheckCircle, XCircle } from 'lucide-vue-next'
import BaseUrlInput, { stripProtocol } from '@/components/shared/BaseUrlInput.vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
import ModelSelect from '@/components/shared/ModelSelect.vue'
import type { ModelItem } from '@/components/shared/ModelSelect.vue'
import api from '@/services/api'
import { resolveApiErrorMessage } from '@/i18n/error'
import { getRuntimeCaps } from '@/utils/runtimeCapabilities'
import {
  PROVIDERS, PROVIDER_LABELS, PROVIDER_DEFAULT_URLS,
  BUILTIN_PROVIDERS, ALL_KNOWN_PROVIDERS,
  isCodexProvider, defaultModelForProvider,
} from '@/utils/llmProviders'
import { useEdition } from '@/composables/useFeature'

const instanceId = inject<ComputedRef<string>>('instanceId')!
const instanceRuntime = inject<ComputedRef<string>>('instanceRuntime', computed(() => 'openclaw'))
const runtimeSupported = computed(() => getRuntimeCaps(instanceRuntime.value).llmConfig)
const instanceOrgId = inject<Ref<string | null>>('instanceOrgId')!
const myInstanceRole = inject<Ref<string | null>>('myInstanceRole', ref(null))
const ROLE_LEVEL: Record<string, number> = { viewer: 10, user: 20, editor: 30, admin: 40 }
const canEdit = computed(() => (ROLE_LEVEL[myInstanceRole.value ?? ''] ?? 0) >= ROLE_LEVEL.editor)

const loading = ref(true)
const saving = ref(false)
const restarting = ref(false)
const error = ref('')
const successMsg = ref('')
const nfsError = ref('')
const dataSource = ref('')
const dirty = ref(false)

// ── Types ──

interface PersonalKey {
  id: string
  provider: string
  api_key_masked: string
  base_url: string | null
  api_type: string | null
  is_active: boolean
  skip_ssl_verify?: boolean
}

interface ProviderConfig {
  provider: string
  keySource: 'org' | 'personal'
  personalKeyNew: string
  personalKeyMasked: string
  hasExistingPersonalKey: boolean
  baseUrl: string
  apiType: string
  isCustom: boolean
  showBaseUrl: boolean
  selectedModel: ModelItem | null
  skipSslVerify: boolean
}

const { isEE } = useEdition()

const orgKeyProviders = ref<Set<string>>(new Set())
const orgAllowedModels = ref<Record<string, string[] | null>>({})
const orgProviderDetails = ref<Record<string, any>>({})

const isOrgKeyAvailable = (provider: string) =>
  orgKeyProviders.value.has(provider)

const orgCustomProviders = computed(() =>
  Object.values(orgProviderDetails.value)
    .filter((p: any) => !ALL_KNOWN_PROVIDERS.has(p.provider))
    .filter((p: any) => !providerConfigs.value.some(c => c.provider === p.provider)),
)

const orgKeyLabel = computed(() => isEE.value ? 'Working Plan' : t('llm.teamKey'))

// ── State ──

const providerConfigs = ref<ProviderConfig[]>([])
const personalKeys = ref<PersonalKey[]>([])
const newProviderOpen = ref(false)
const showCustomForm = ref(false)
const customSlug = ref('')
const customSlugError = ref('')

const unusedProviders = computed(() =>
  PROVIDERS.filter(p => !providerConfigs.value.some(c => c.provider === p))
)

function personalKeyForProvider(provider: string) {
  return personalKeys.value.find(k => k.provider === provider)
}

// ── Data loading ──

async function loadAll() {
  loading.value = true
  error.value = ''
  nfsError.value = ''
  successMsg.value = ''

  try {
    const orgKeysPromise = instanceOrgId.value
      ? api.get(`/orgs/${instanceOrgId.value}/model-providers/available`).catch(() => ({ data: { data: [] } }))
      : Promise.resolve({ data: { data: [] } })
    const [configsResult, keysResult, orgKeysResult] = await Promise.allSettled([
      api.get(`/instances/${instanceId.value}/provider-configs`),
      api.get('/users/me/llm-keys'),
      orgKeysPromise,
    ])
    if (orgKeysResult.status === 'fulfilled') {
      const keys = orgKeysResult.value.data.data ?? []
      orgKeyProviders.value = new Set(keys.map((k: any) => k.provider))
      for (const k of keys) {
        orgAllowedModels.value[k.provider] = k.allowed_models ?? null
        orgProviderDetails.value[k.provider] = k
      }
    }

    if (configsResult.status === 'fulfilled') {
      dataSource.value = 'pod'
    } else {
      const e = configsResult.reason
      const status = e?.response?.status
      const msg = e?.response?.data?.message || ''
      if (status === 503 && (msg.includes('NFS') || msg.includes('nfs') || msg.includes('mount') || msg.includes('挂载'))) {
        nfsError.value = msg
      }
    }

    if (keysResult.status === 'fulfilled') {
      personalKeys.value = keysResult.value.data.data ?? []
    }

    const podConfigs: {
      provider: string; key_source: string; selected_models?: any[];
      personal_key_masked?: string; base_url?: string | null; api_type?: string | null;
    }[] = configsResult.status === 'fulfilled' ? (configsResult.value.data.data ?? []) : []

    const configs: ProviderConfig[] = []
    for (const c of podConfigs) {
      const pk = personalKeyForProvider(c.provider)
      const isCustom = !ALL_KNOWN_PROVIDERS.has(c.provider)
      const orgDetail = orgProviderDetails.value[c.provider]
      configs.push({
        provider: c.provider,
        keySource: isCodexProvider(c.provider)
          ? 'personal'
          : ((c.key_source === 'org' || c.key_source === 'personal') ? c.key_source : 'org'),
        personalKeyNew: '',
        personalKeyMasked: pk?.api_key_masked ?? c.personal_key_masked ?? '',
        hasExistingPersonalKey: !!pk,
        baseUrl: c.base_url ?? pk?.base_url ?? '',
        apiType: c.api_type ?? pk?.api_type ?? (isCustom ? 'openai-completions' : ''),
        isCustom,
        showBaseUrl: isCustom || !!(c.base_url || pk?.base_url),
        selectedModel: (c.selected_models ?? [])[0] ?? defaultModelForProvider(c.provider),
        skipSslVerify: pk?.skip_ssl_verify ?? orgDetail?.skip_ssl_verify ?? false,
      })
    }

    for (const c of configs) {
      if (c.keySource === 'org' && !isOrgKeyAvailable(c.provider)) {
        c.keySource = 'personal'
      }
    }
    providerConfigs.value = configs
    dirty.value = false
  } catch (e: any) {
    error.value = e?.response?.data?.message || '加载配置失败'
  } finally {
    loading.value = false
  }
}

// ── Provider management ──

function addProvider(provider: string) {
  if (providerConfigs.value.some(c => c.provider === provider)) return
  const pk = personalKeyForProvider(provider)
  const orgDetail = orgProviderDetails.value[provider]
  const isCustom = !ALL_KNOWN_PROVIDERS.has(provider)
  providerConfigs.value.push({
    provider,
    keySource: isCodexProvider(provider)
      ? 'personal'
      : (isCustom ? 'personal' : (isOrgKeyAvailable(provider) ? 'org' : 'personal')),
    personalKeyNew: '',
    personalKeyMasked: pk?.api_key_masked ?? '',
    hasExistingPersonalKey: !!pk,
    baseUrl: pk?.base_url ?? '',
    apiType: pk?.api_type ?? (isCustom ? 'openai-completions' : ''),
    isCustom,
    showBaseUrl: isCustom || !!pk?.base_url,
    selectedModel: defaultModelForProvider(provider),
    skipSslVerify: pk?.skip_ssl_verify ?? orgDetail?.skip_ssl_verify ?? false,
  })
  newProviderOpen.value = false
  dirty.value = true
}

function addCustomProvider() {
  const slug = customSlug.value.trim()
  if (!slug) return
  if (!/^[a-z][a-z0-9-]*[a-z0-9]$/.test(slug) || slug.length < 2 || slug.length > 32) {
    customSlugError.value = t('llm.providerSlugInvalid')
    return
  }
  if (ALL_KNOWN_PROVIDERS.has(slug) || providerConfigs.value.some(c => c.provider === slug)) {
    customSlugError.value = t('llm.providerSlugConflict')
    return
  }
  providerConfigs.value.push({
    provider: slug,
    keySource: 'personal',
    personalKeyNew: '',
    personalKeyMasked: '',
    hasExistingPersonalKey: false,
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
  providerConfigs.value.push({
    provider: orgProvider.provider,
    keySource: 'org',
    personalKeyNew: '',
    personalKeyMasked: '',
    hasExistingPersonalKey: false,
    baseUrl: orgProvider.base_url || '',
    apiType: orgProvider.api_type || 'openai-completions',
    isCustom: true,
    showBaseUrl: true,
    selectedModel: null,
    skipSslVerify: orgProvider.skip_ssl_verify ?? false,
  })
  dirty.value = true
  dirty.value = true
}

async function handleFetchModels(provider: string, callback: (models: ModelItem[], error?: string) => void) {
  const cfg = providerConfigs.value.find(c => c.provider === provider)
  const params: Record<string, any> = {}
  if (cfg?.keySource === 'personal' && cfg.personalKeyNew) {
    params.api_key = cfg.personalKeyNew
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
  if (instanceOrgId.value) {
    params.org_id = instanceOrgId.value
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
  providerConfigs.value.splice(idx, 1)
  delete testResults.value[idx]
  dirty.value = true
}

const testingProvider = ref<number | null>(null)
const testResults = ref<Record<number, { ok: boolean; message: string; tested_model?: string | null; latency_ms?: number | null; error_detail?: string | null }>>({})

async function handleTestKey(idx: number) {
  const cfg = providerConfigs.value[idx]
  const key = cfg?.personalKeyNew
  if (!key) return
  testingProvider.value = idx
  delete testResults.value[idx]
  try {
    const res = await api.post('/llm/test-connection', {
      provider: cfg.provider,
      api_key: key,
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

function markDirty() {
  dirty.value = true
}

// ── Validation ──

function validateConfigs(): string | null {
  for (const cfg of providerConfigs.value) {
    const label = PROVIDER_LABELS[cfg.provider] || cfg.provider
    if (cfg.isCustom && !cfg.baseUrl) {
      return `${label}: Base URL ${t('common.noData')}`
    }
    if (cfg.keySource === 'personal' && !isCodexProvider(cfg.provider)) {
      if (!cfg.personalKeyNew && !cfg.hasExistingPersonalKey) {
        return `${label}: 请输入个人 API Key`
      }
    }
    if (!cfg.selectedModel) {
      return `${label}: 请选择一个模型`
    }
  }
  return null
}

const canSave = computed(() => {
  if (!dirty.value || providerConfigs.value.length === 0) return false
  return providerConfigs.value.every(c => !!c.selectedModel)
})

// ── Save ──

async function handleSave() {
  const validationError = validateConfigs()
  if (validationError) {
    error.value = validationError
    return
  }

  saving.value = true
  error.value = ''
  successMsg.value = ''

  try {
    // 1. Upsert personal keys (new key, or base_url/api_type update for existing key)
    for (const cfg of providerConfigs.value) {
      if (cfg.keySource !== 'personal') continue
      const needsUpsert = isCodexProvider(cfg.provider) || cfg.personalKeyNew || cfg.baseUrl || cfg.isCustom
      if (!needsUpsert) continue
      await api.post('/users/me/llm-keys', {
        provider: cfg.provider,
        api_key: isCodexProvider(cfg.provider) ? undefined : (cfg.personalKeyNew || undefined),
        base_url: isCodexProvider(cfg.provider) ? null : (cfg.baseUrl || null),
        api_type: cfg.isCustom ? cfg.apiType : null,
        skip_ssl_verify: cfg.skipSslVerify,
      })
      if (cfg.personalKeyNew) {
        cfg.personalKeyMasked = cfg.personalKeyNew.length > 8
          ? cfg.personalKeyNew.slice(0, 6) + '***' + cfg.personalKeyNew.slice(-3)
          : cfg.personalKeyNew.slice(0, 2) + '***'
        cfg.personalKeyNew = ''
      } else if (isCodexProvider(cfg.provider)) {
        cfg.personalKeyMasked = t('llm.codexCliLabel')
      }
      cfg.hasExistingPersonalKey = true
    }

    // 2. Write configs to DB + Pod (may return pending if Pod is not running)
    const writeRes = await api.put(`/instances/${instanceId.value}/provider-configs`, {
      configs: providerConfigs.value.map(c => {
        const selectedModel = c.selectedModel ?? defaultModelForProvider(c.provider)
        return {
          provider: c.provider,
          key_source: c.keySource,
          selected_models: selectedModel ? [selectedModel] : undefined,
          base_url: isCodexProvider(c.provider) ? null : (c.baseUrl || null),
          api_type: c.isCustom ? c.apiType : null,
        }
      }),
    })

    const isPending = writeRes.data.data?.pending === true
    if (isPending) {
      successMsg.value = t('llm.savePendingRestart')
    }

    // 3. Restart runtime (force-reconfig if pending)
    restarting.value = true
    const res = await api.post(`/instances/${instanceId.value}/restart-runtime`, null, { timeout: 120000 })
    const result = res.data.data
    if (result?.status === 'ok') {
      successMsg.value = isPending
        ? t('llm.savePendingRestart')
        : '配置已保存，DeskClaw 已重启'
    } else if (result?.status === 'timeout') {
      successMsg.value = '配置已保存，但 DeskClaw 重启超时，请检查AI 员工状态'
    } else {
      successMsg.value = '配置已保存'
      if (result?.message) {
        error.value = result.message
      }
    }

    dirty.value = false
    const pkRes = await api.get('/users/me/llm-keys')
    personalKeys.value = pkRes.data.data ?? []
  } catch (e: any) {
    error.value = e?.response?.data?.message || '保存失败'
  } finally {
    saving.value = false
    restarting.value = false
  }
}

watch(() => instanceId.value, (val) => {
  if (val) loadAll()
}, { immediate: true })

watch(() => instanceOrgId.value, (newVal, oldVal) => {
  if (newVal && !oldVal && instanceId.value) {
    loadAll()
  }
})
</script>

<template>
  <div>
    <div v-if="!runtimeSupported" class="flex flex-col items-center justify-center py-20 text-muted-foreground gap-3">
      <AlertTriangle class="w-10 h-10 opacity-50" />
      <p class="text-sm">{{ t('instanceSettings.unsupportedRuntime') }}</p>
    </div>

    <div v-else-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <div v-else class="space-y-6">
      <!-- Header -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <Brain class="w-4 h-4 text-violet-400" />
          <h2 class="text-sm font-medium">大模型配置</h2>
          <span v-if="dataSource === 'nfs' && !nfsError" class="text-[10px] text-muted-foreground bg-muted/50 px-1.5 py-0.5 rounded">
            NFS
          </span>
        </div>
        <div class="flex items-center gap-2">
          <button
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-border text-xs hover:bg-card transition-colors"
            :disabled="saving || restarting"
            @click="loadAll"
          >
            <RefreshCw class="w-3 h-3" />
            刷新
          </button>
          <button
            v-if="providerConfigs.length > 0 && canEdit"
            :disabled="saving || restarting || !canSave"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs transition-colors"
            :class="canSave
              ? 'bg-primary text-primary-foreground hover:bg-primary/90'
              : 'bg-muted text-muted-foreground'"
            @click="handleSave"
          >
            <Loader2 v-if="saving || restarting" class="w-3 h-3 animate-spin" />
            <Save v-else class="w-3 h-3" />
            {{ restarting ? '重启中...' : saving ? '保存中...' : '保存并重启' }}
          </button>
        </div>
      </div>

      <!-- Status messages -->
      <div v-if="restarting" class="flex items-center gap-3 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20">
        <RefreshCw class="w-4 h-4 text-amber-500 animate-spin" />
        <span class="text-xs">DeskClaw 正在完成当前任务并重启...</span>
      </div>
      <p v-if="error" class="text-sm text-destructive">{{ error }}</p>
      <p v-if="successMsg" class="text-sm text-green-500">{{ successMsg }}</p>

      <!-- NFS error -->
      <div v-if="nfsError" class="flex flex-col items-center gap-3 py-10 text-center">
        <HardDrive class="w-8 h-8 text-destructive/60" />
        <p class="text-sm text-destructive">NFS 存储不可用</p>
        <p class="text-xs text-muted-foreground max-w-sm">{{ nfsError }}</p>
      </div>

      <!-- Provider list -->
      <template v-if="!nfsError">
        <!-- Empty state: provider grid -->
        <div v-if="providerConfigs.length === 0 && !saving" class="space-y-3">
          <p class="text-xs text-muted-foreground">
            当前AI 员工未配置大模型 Provider，选择一个开始配置
          </p>
          <div class="grid grid-cols-2 gap-2">
            <button
              v-for="p in unusedProviders"
              :key="p"
              class="px-4 py-3 rounded-lg border border-border bg-card text-sm text-left hover:border-primary/50 hover:bg-primary/5 transition-colors cursor-pointer"
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
              class="px-4 py-3 rounded-lg border border-border bg-card text-sm text-left hover:border-primary/50 hover:bg-primary/5 transition-colors cursor-pointer"
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
              class="px-4 py-3 rounded-lg border border-dashed border-violet-400/50 bg-card text-sm text-left hover:border-violet-400 hover:bg-violet-500/5 transition-colors text-violet-400 cursor-pointer"
              @click="showCustomForm = true"
            >
              <div class="flex items-center gap-1.5">
                <Plus class="w-3.5 h-3.5" />
                {{ t('llm.addCustomProvider') }}
              </div>
            </button>
          </div>
        </div>

        <!-- Provider cards -->
        <div v-else class="space-y-3">
          <div
            v-for="(cfg, idx) in providerConfigs"
            :key="cfg.provider"
            class="rounded-lg border border-border bg-card p-4 space-y-3"
          >
            <!-- Provider header -->
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="font-medium text-sm">{{ PROVIDER_LABELS[cfg.provider] || cfg.provider }}</span>
                <span v-if="cfg.isCustom" class="text-[10px] px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-400">{{ t('llm.customProvider') }}</span>
                <span v-else-if="cfg.keySource === 'org' && isOrgKeyAvailable(cfg.provider)" class="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-500">
                  {{ orgKeyLabel }}
                </span>
              </div>
              <button
                class="text-muted-foreground hover:text-destructive transition-colors"
                @click="removeProvider(idx)"
              >
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
                  <input type="radio" :name="`apitype-${cfg.provider}`" value="openai-completions" v-model="cfg.apiType" class="accent-primary" @change="markDirty" />
                  {{ t('llm.apiTypeOpenai') }}
                </label>
                <label class="flex items-center gap-1.5 cursor-pointer text-xs">
                  <input type="radio" :name="`apitype-${cfg.provider}`" value="anthropic-messages" v-model="cfg.apiType" class="accent-primary" @change="markDirty" />
                  {{ t('llm.apiTypeAnthropic') }}
                </label>
              </template>
            </div>

            <!-- Key source selection -->
            <div class="space-y-2">
              <div v-if="(!cfg.isCustom || isOrgKeyAvailable(cfg.provider)) && !isCodexProvider(cfg.provider)" class="flex gap-4 text-sm">
                <span class="relative group">
                  <label
                    class="flex items-center gap-1.5"
                    :class="isOrgKeyAvailable(cfg.provider) ? 'cursor-pointer' : 'cursor-not-allowed opacity-50'"
                  >
                    <input
                      type="radio"
                      :name="`ks-${cfg.provider}`"
                      value="org"
                      v-model="cfg.keySource"
                      class="accent-primary"
                      :disabled="!isOrgKeyAvailable(cfg.provider)"
                      @change="markDirty"
                    />
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
                  <input
                    type="radio"
                    :name="`ks-${cfg.provider}`"
                    value="personal"
                    v-model="cfg.keySource"
                    class="accent-primary"
                    @change="markDirty"
                  />
                  {{ t('llm.personalKey') }}
                </label>
              </div>

              <p v-else-if="isCodexProvider(cfg.provider)" class="text-xs text-muted-foreground pl-0.5">
                {{ t('llm.codexCliHint') }}
              </p>

              <p v-if="cfg.keySource === 'org' && (!cfg.isCustom || isOrgKeyAvailable(cfg.provider))" class="text-xs text-muted-foreground pl-0.5">
                {{ t('llm.orgKeyHint') }}
              </p>

              <!-- Personal key -->
              <div v-if="cfg.keySource === 'personal'" class="space-y-1.5">
                <template v-if="isCodexProvider(cfg.provider)">
                  <div v-if="cfg.hasExistingPersonalKey" class="flex items-center gap-2 text-xs">
                    <Check class="w-3 h-3 text-green-400" />
                    <span class="text-muted-foreground">{{ t('llm.codexCliCurrentAuth') }}:</span>
                    <span class="font-mono">{{ cfg.personalKeyMasked }}</span>
                  </div>
                  <div class="rounded-md border border-border bg-background px-3 py-2 text-xs text-muted-foreground">
                    {{ t('llm.codexCliRuntimeHint') }}
                  </div>
                </template>
                <template v-else>
                  <div v-if="cfg.hasExistingPersonalKey" class="flex items-center gap-2 text-xs">
                    <Check class="w-3 h-3 text-green-400" />
                    <span class="text-muted-foreground">当前 Key:</span>
                    <span class="font-mono">{{ cfg.personalKeyMasked }}</span>
                  </div>
                  <div class="flex items-center gap-2">
                    <div class="relative flex-1">
                      <Key class="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                      <input
                        v-model="cfg.personalKeyNew"
                        type="password"
                        :placeholder="cfg.hasExistingPersonalKey ? '输入新 Key 以替换' : '输入 API Key'"
                        class="w-full pl-9 pr-3 py-1.5 rounded-md bg-background border border-border text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary/50"
                        @input="markDirty"
                      />
                    </div>
                    <button
                      v-if="cfg.personalKeyNew"
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
                      @clear="cfg.baseUrl = ''; cfg.showBaseUrl = false; markDirty()"
                      @input="markDirty"
                    />
                    <label v-if="cfg.baseUrl" class="flex items-center gap-2 mt-1.5 cursor-pointer">
                      <input type="checkbox" v-model="cfg.skipSslVerify" class="accent-primary" @change="markDirty" />
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
              @update:model-value="markDirty"
            />
            <p v-if="(cfg.isCustom || isCodexProvider(cfg.provider) || !BUILTIN_PROVIDERS.has(cfg.provider)) && !cfg.selectedModel" class="text-[10px] text-amber-500">
              {{ t('llm.modelRequired') }}
            </p>
          </div>

          <!-- Add provider -->
          <div class="flex gap-2 items-start">
            <div v-if="unusedProviders.length > 0" class="relative">
              <button
                class="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                @click="newProviderOpen = !newProviderOpen"
              >
                <Plus class="w-3.5 h-3.5" />
                添加 Provider
                <ChevronDown class="w-3 h-3 transition-transform" :class="newProviderOpen ? 'rotate-180' : ''" />
              </button>
              <div
                v-if="newProviderOpen"
                class="absolute z-10 mt-1 w-56 rounded-lg border border-border bg-card shadow-lg overflow-hidden"
              >
                <button
                  v-for="p in unusedProviders"
                  :key="p"
                  class="w-full px-4 py-2 text-left text-sm hover:bg-accent transition-colors"
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
              </div>
            </div>
            <div v-for="ocp in orgCustomProviders" :key="ocp.provider" class="inline-flex">
              <button
                class="flex items-center gap-1.5 text-xs text-foreground hover:text-primary transition-colors cursor-pointer"
                @click="addOrgCustomProvider(ocp)"
              >
                <Plus class="w-3.5 h-3.5" />
                {{ ocp.label || ocp.provider }}
                <span class="inline-flex items-center gap-0.5 text-[10px] text-amber-500">
                  <Star class="w-3 h-3 fill-amber-500 text-amber-500" />
                </span>
              </button>
            </div>
            <button
              class="flex items-center gap-1 text-xs text-violet-400 hover:text-violet-300 transition-colors cursor-pointer"
              @click="showCustomForm = true"
            >
              <Plus class="w-3.5 h-3.5" />
              {{ t('llm.addCustomProvider') }}
            </button>
          </div>

        </div>

        <!-- Custom Provider form -->
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

      </template>
    </div>

    <!-- Close dropdown overlay -->
    <Teleport to="body">
      <div v-if="newProviderOpen" class="fixed inset-0 z-5" @click="newProviderOpen = false" />
    </Teleport>
  </div>
</template>
