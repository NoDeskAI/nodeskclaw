<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useOrgStore } from '@/stores/org'
import { Settings, Loader2, KeyRound, Check, X, Save, Plus, Trash2, ChevronDown, Zap, CheckCircle, XCircle } from 'lucide-vue-next'
import api from '@/services/api'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import { resolveApiErrorMessage } from '@/i18n/error'
import { PROVIDERS, PROVIDER_LABELS, WP_PROVIDERS, ALL_KNOWN_PROVIDERS } from '@/utils/llmProviders'
import { useEdition } from '@/composables/useFeature'
import ModelSelect from '@/components/shared/ModelSelect.vue'
import type { ModelItem } from '@/components/shared/ModelSelect.vue'

const { t } = useI18n()
const orgStore = useOrgStore()
const toast = useToast()
const { confirm } = useConfirm()
const { isEE } = useEdition()

const orgId = computed(() => orgStore.currentOrgId)

interface ModelProvider {
  id: string
  org_id: string
  provider: string
  label: string | null
  api_key_masked: string
  base_url: string | null
  api_type: string | null
  org_token_limit: number | null
  system_token_limit: number | null
  is_active: boolean
  skip_ssl_verify: boolean
  allowed_models?: string[] | null
  usage_total_tokens: number
  created_by: string
}

interface WpModelInfo {
  id: string
  name: string
}

const NON_CODEX_PROVIDERS = PROVIDERS.filter(p => p !== 'codex')
const visibleProviders = computed(() =>
  isEE.value ? NON_CODEX_PROVIDERS.filter(p => !WP_PROVIDERS.has(p)) : NON_CODEX_PROVIDERS,
)
const WP_PROVIDER_LIST = [...WP_PROVIDERS]

const providers = ref<ModelProvider[]>([])
const loading = ref(true)

const showDialog = ref(false)
const dialogProvider = ref('')
const isEditing = ref(false)
const editingId = ref<string | null>(null)
const saving = ref(false)

const form = ref({
  api_key: '',
  base_url: '',
  api_type: '',
  label: '',
  org_token_limit: '',
  system_token_limit: '',
  is_active: true,
  skip_ssl_verify: false,
})

const testModel = ref<ModelItem | null>(null)

const showCustomForm = ref(false)
const customSlug = ref('')
const customSlugError = ref('')

const API_TYPE_OPTIONS = [
  { value: 'openai-completions', label: 'OpenAI Compatible' },
  { value: 'anthropic-messages', label: 'Anthropic Compatible' },
]

function isCustomProvider(providerName: string): boolean {
  return !ALL_KNOWN_PROVIDERS.has(providerName)
}

const customProviders = computed(() =>
  providers.value.filter(p => isCustomProvider(p.provider)),
)

function resetForm() {
  form.value = { api_key: '', base_url: '', api_type: '', label: '', org_token_limit: '', system_token_limit: '', is_active: true, skip_ssl_verify: false }
  testModel.value = null
}

function configuredMap(): Record<string, ModelProvider> {
  const map: Record<string, ModelProvider> = {}
  for (const p of providers.value) {
    map[p.provider] = p
  }
  return map
}

async function fetchProviders() {
  if (!orgId.value) return
  loading.value = true
  try {
    const res = await api.get(`/orgs/${orgId.value}/model-providers`)
    providers.value = res.data.data ?? []
  } catch (e: any) {
    toast.error(resolveApiErrorMessage(e))
  } finally {
    loading.value = false
  }
}

const wpModels = ref<Record<string, WpModelInfo[]>>({})
const wpSelectedModels = ref<Record<string, Set<string>>>({})
const wpSaving = ref<Record<string, boolean>>({})

const wpConfiguredProviders = computed(() => {
  const map = configuredMap()
  return WP_PROVIDER_LIST.filter(p => !!map[p])
})

function initWpSelections() {
  const map = configuredMap()
  for (const p of WP_PROVIDER_LIST) {
    const configured = map[p]
    if (configured?.allowed_models?.length) {
      wpSelectedModels.value[p] = new Set(configured.allowed_models)
    }
  }
}

async function fetchWpModels(provider: string) {
  if (!orgId.value) return
  try {
    const res = await api.get(`/llm/providers/${provider}/models`, {
      params: { org_id: orgId.value },
    })
    wpModels.value[provider] = res.data.data?.models ?? []
  } catch {
    wpModels.value[provider] = []
  }
}

function toggleWpModel(provider: string, modelId: string) {
  if (!wpSelectedModels.value[provider]) {
    wpSelectedModels.value[provider] = new Set()
  }
  const s = wpSelectedModels.value[provider]
  if (s.has(modelId)) {
    s.delete(modelId)
  } else {
    s.add(modelId)
  }
}

async function saveAllowedModels(provider: string) {
  const map = configuredMap()
  const configured = map[provider]
  if (!configured || !orgId.value) return
  wpSaving.value[provider] = true
  try {
    const selected = wpSelectedModels.value[provider]
    const allowed = selected?.size ? [...selected] : null
    await api.patch(`/orgs/${orgId.value}/model-providers/${configured.id}`, {
      allowed_models: allowed,
    })
    toast.success(t('orgSettings.wpModelsSaved'))
    await fetchProviders()
    initWpSelections()
  } catch (e: any) {
    toast.error(resolveApiErrorMessage(e) || t('orgSettings.wpModelsSaveFailed'))
  } finally {
    wpSaving.value[provider] = false
  }
}

function openConfigure(providerName: string) {
  resetForm()
  testResult.value = null
  dialogProvider.value = providerName
  const existing = configuredMap()[providerName]
  if (existing) {
    isEditing.value = true
    editingId.value = existing.id
    form.value = {
      api_key: '',
      base_url: existing.base_url || '',
      api_type: existing.api_type || '',
      label: existing.label || '',
      org_token_limit: existing.org_token_limit?.toString() ?? '',
      system_token_limit: existing.system_token_limit?.toString() ?? '',
      is_active: existing.is_active,
      skip_ssl_verify: existing.skip_ssl_verify ?? false,
    }
    const firstModel = existing.allowed_models?.[0]
    if (firstModel) {
      testModel.value = { id: firstModel, name: firstModel }
    }
  } else {
    isEditing.value = false
    editingId.value = null
    if (isCustomProvider(providerName)) {
      form.value.api_type = 'openai-completions'
    }
  }
  showDialog.value = true
}

function addCustomProvider() {
  const slug = customSlug.value.trim()
  if (!slug) return
  if (!/^[a-z][a-z0-9-]*[a-z0-9]$/.test(slug) || slug.length < 2 || slug.length > 32) {
    customSlugError.value = t('orgSettings.customProviderSlugInvalid')
    return
  }
  if (ALL_KNOWN_PROVIDERS.has(slug)) {
    customSlugError.value = t('orgSettings.customProviderSlugConflict')
    return
  }
  if (providers.value.some(p => p.provider === slug)) {
    customSlugError.value = t('orgSettings.customProviderSlugConflict')
    return
  }
  customSlugError.value = ''
  showCustomForm.value = false
  customSlug.value = ''
  openConfigure(slug)
}

async function handleSave() {
  if (!orgId.value) return
  saving.value = true
  try {
    if (isEditing.value && editingId.value) {
      const payload: Record<string, any> = { is_active: form.value.is_active }
      if (form.value.api_key) payload.api_key = form.value.api_key
      payload.base_url = form.value.base_url || null
      payload.skip_ssl_verify = form.value.skip_ssl_verify
      payload.org_token_limit = form.value.org_token_limit ? Number(form.value.org_token_limit) : null
      payload.system_token_limit = form.value.system_token_limit ? Number(form.value.system_token_limit) : null
      if (isCustomProvider(dialogProvider.value)) {
        payload.api_type = form.value.api_type || null
        payload.label = form.value.label || null
      }
      await api.patch(`/orgs/${orgId.value}/model-providers/${editingId.value}`, payload)
      toast.success(t('orgSettings.llmKeysUpdated'))
    } else {
      const body: Record<string, any> = {
        provider: dialogProvider.value,
        api_key: form.value.api_key,
        base_url: form.value.base_url || undefined,
        skip_ssl_verify: form.value.skip_ssl_verify,
        org_token_limit: form.value.org_token_limit ? Number(form.value.org_token_limit) : undefined,
        system_token_limit: form.value.system_token_limit ? Number(form.value.system_token_limit) : undefined,
      }
      if (isCustomProvider(dialogProvider.value)) {
        body.api_type = form.value.api_type || undefined
        body.label = form.value.label || undefined
      }
      await api.post(`/orgs/${orgId.value}/model-providers`, body)
      toast.success(t('orgSettings.llmKeysCreated'))
    }
    showDialog.value = false
    await fetchProviders()
  } catch (e: any) {
    toast.error(resolveApiErrorMessage(e) || t(isEditing.value ? 'orgSettings.llmKeysUpdateFailed' : 'orgSettings.llmKeysCreateFailed'))
  } finally {
    saving.value = false
  }
}

async function handleDelete(providerName: string) {
  const existing = configuredMap()[providerName]
  if (!existing) return
  const ok = await confirm({
    title: t('common.delete'),
    description: t('orgSettings.llmKeysDeleteConfirm'),
    variant: 'danger',
    confirmText: t('common.delete'),
  })
  if (!ok) return
  try {
    await api.delete(`/orgs/${orgId.value}/model-providers/${existing.id}`)
    toast.success(t('orgSettings.llmKeysDeleted'))
    await fetchProviders()
  } catch (e: any) {
    toast.error(resolveApiErrorMessage(e) || t('orgSettings.llmKeysDeleteFailed'))
  }
}

function formatTokens(n: number | null | undefined): string {
  if (n == null) return t('orgSettings.llmKeysNoLimit')
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return n.toString()
}

function usagePercent(used: number, limit: number | null): number {
  if (!limit || limit === 0) return 0
  return Math.min(100, (used / limit) * 100)
}

function effectiveLimit(p: ModelProvider | undefined | null): number | null {
  if (!p) return null
  return isEE.value ? p.org_token_limit : p.system_token_limit
}

const canSave = computed(() => {
  if (isEditing.value) return true
  if (!form.value.api_key) return false
  if (isCustomProvider(dialogProvider.value) && !form.value.base_url) return false
  return true
})

const testing = ref(false)
const testResult = ref<{ ok: boolean; message: string; tested_model?: string | null; latency_ms?: number | null; error_detail?: string | null } | null>(null)

const canTest = computed(() => {
  if (!isEditing.value && !form.value.api_key) return false
  if (isEditing.value && !form.value.api_key && !orgId.value) return false
  return true
})

async function handleTest() {
  testing.value = true
  testResult.value = null
  try {
    const payload: Record<string, any> = {
      provider: dialogProvider.value,
      base_url: form.value.base_url || undefined,
      api_type: form.value.api_type || undefined,
      skip_ssl_verify: form.value.skip_ssl_verify,
      model: testModel.value?.id || undefined,
    }
    if (form.value.api_key) {
      payload.api_key = form.value.api_key
    } else if (isEditing.value && orgId.value) {
      payload.org_id = orgId.value
    }
    const res = await api.post('/llm/test-connection', payload)
    testResult.value = res.data.data
  } catch (e: any) {
    testResult.value = { ok: false, message: resolveApiErrorMessage(e) || t('orgSettings.llmTestConnectionFailed') }
  } finally {
    testing.value = false
  }
}

async function handleFetchModels(
  provider: string,
  callback: (models: ModelItem[], error?: string) => void,
) {
  const params: Record<string, any> = {}
  if (form.value.api_key) params.api_key = form.value.api_key
  else if (isEditing.value && orgId.value) params.org_id = orgId.value
  if (form.value.base_url) params.base_url = form.value.base_url
  if (form.value.api_type) params.api_type = form.value.api_type
  if (form.value.skip_ssl_verify) params.skip_ssl_verify = true
  try {
    const res = await api.get(`/llm/providers/${provider}/models`, { params })
    callback(res.data.data?.models ?? [])
  } catch {
    callback([], t('orgSettings.llmTestConnectionFailed'))
  }
}

onMounted(async () => {
  if (!orgStore.currentOrg) await orgStore.fetchMyOrg()
  await fetchProviders()
  if (isEE.value) {
    initWpSelections()
    await Promise.all(wpConfiguredProviders.value.map(p => fetchWpModels(p)))
  }
})
</script>

<template>
  <div class="space-y-8">
    <!-- Working Plan section (EE only) -->
    <div v-if="isEE" class="space-y-4">
      <div>
        <h2 class="text-lg font-semibold flex items-center gap-2">
          {{ t('orgSettings.wpTitle') }}
        </h2>
        <p class="text-sm text-muted-foreground mt-1">{{ t('orgSettings.wpDescription') }}</p>
      </div>

      <div v-if="loading" class="flex items-center justify-center py-8">
        <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="wp in WP_PROVIDER_LIST"
          :key="wp"
          class="rounded-lg border border-border bg-card p-4"
        >
          <div class="flex items-center justify-between mb-3">
            <span class="font-medium text-sm">{{ PROVIDER_LABELS[wp] || wp }}</span>
            <span
              v-if="configuredMap()[wp]"
              class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-green-500/10 text-green-500"
            >
              <Check class="w-3 h-3" />
              {{ t('orgSettings.llmKeysConfigured') }}
            </span>
            <span v-else class="text-xs text-muted-foreground">
              {{ t('orgSettings.llmKeysNotConfigured') }}
            </span>
          </div>

          <template v-if="configuredMap()[wp]">
            <div v-if="wpModels[wp]?.length" class="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-3">
              <label
                v-for="model in wpModels[wp]"
                :key="model.id"
                class="flex items-center gap-2 px-3 py-2 rounded-md border border-border hover:bg-muted/50 transition-colors cursor-pointer text-sm"
              >
                <input
                  type="checkbox"
                  :checked="wpSelectedModels[wp]?.has(model.id)"
                  class="accent-primary"
                  @change="toggleWpModel(wp, model.id)"
                />
                {{ model.name }}
              </label>
            </div>
            <div v-else class="flex items-center justify-center py-4">
              <Loader2 class="w-4 h-4 animate-spin text-muted-foreground" />
            </div>
            <div class="flex justify-end">
              <button
                class="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="wpSaving[wp]"
                @click="saveAllowedModels(wp)"
              >
                <Loader2 v-if="wpSaving[wp]" class="w-3.5 h-3.5 animate-spin" />
                <Save v-else class="w-3.5 h-3.5" />
                {{ t('common.save') }}
              </button>
            </div>
          </template>

          <template v-else>
            <p class="text-xs text-muted-foreground/60">{{ t('orgSettings.wpNotConfigured') }}</p>
          </template>
        </div>
      </div>
    </div>

    <!-- CE Model Providers section -->
    <div class="space-y-4">
      <div>
        <h2 class="text-lg font-semibold flex items-center gap-2">
          <KeyRound class="w-5 h-5" />
          {{ t('orgSettings.llmKeysTitle') }}
        </h2>
        <p class="text-sm text-muted-foreground mt-1">
          {{ isEE ? t('orgSettings.llmKeysCeDescription') : t('orgSettings.llmKeysDescription') }}
        </p>
      </div>

      <div v-if="loading" class="flex items-center justify-center py-12">
        <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
      </div>

      <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <div
          v-for="providerName in visibleProviders"
          :key="providerName"
        class="rounded-lg border border-border bg-card p-4 hover:border-primary/30 transition-colors"
      >
        <div class="flex items-center justify-between mb-3">
          <span class="font-medium text-sm">{{ PROVIDER_LABELS[providerName] || providerName }}</span>
          <span
            v-if="configuredMap()[providerName]"
            class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium"
            :class="configuredMap()[providerName].is_active
              ? 'bg-green-500/10 text-green-500'
              : 'bg-muted text-muted-foreground'"
          >
            <Check v-if="configuredMap()[providerName].is_active" class="w-3 h-3" />
            <X v-else class="w-3 h-3" />
            {{ configuredMap()[providerName].is_active ? t('orgSettings.llmKeysConfigured') : t('orgSettings.llmKeysDisabled') }}
          </span>
        </div>

        <template v-if="configuredMap()[providerName]">
          <div class="space-y-2 text-xs text-muted-foreground">
            <div class="font-mono">{{ configuredMap()[providerName].api_key_masked }}</div>
            <div class="flex items-center gap-2">
              <span>{{ formatTokens(configuredMap()[providerName].usage_total_tokens) }} / {{ formatTokens(effectiveLimit(configuredMap()[providerName])) }}</span>
              <div v-if="effectiveLimit(configuredMap()[providerName])" class="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all"
                  :class="usagePercent(configuredMap()[providerName].usage_total_tokens, effectiveLimit(configuredMap()[providerName])) > 90 ? 'bg-destructive' : 'bg-primary'"
                  :style="{ width: usagePercent(configuredMap()[providerName].usage_total_tokens, effectiveLimit(configuredMap()[providerName])) + '%' }"
                />
              </div>
            </div>
          </div>
          <div class="flex items-center gap-2 mt-3">
            <button
              class="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md border border-border text-sm hover:bg-muted transition-colors"
              @click="openConfigure(providerName)"
            >
              <Settings class="w-3.5 h-3.5" />
              {{ t('orgSettings.llmKeysSettings') }}
            </button>
            <button
              class="px-3 py-1.5 rounded-md text-sm text-destructive hover:bg-destructive/10 transition-colors"
              @click="handleDelete(providerName)"
            >
              {{ t('common.delete') }}
            </button>
          </div>
        </template>

        <template v-else>
          <div class="text-xs text-muted-foreground/60 mb-3">{{ t('orgSettings.llmKeysNotConfigured') }}</div>
          <button
            class="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors"
            @click="openConfigure(providerName)"
          >
            {{ t('orgSettings.llmKeysConfigure') }}
          </button>
        </template>
      </div>
    </div>
    </div>

    <!-- Custom Providers section -->
    <div class="space-y-4">
      <div>
        <h2 class="text-lg font-semibold">{{ t('orgSettings.customProviderTitle') }}</h2>
        <p class="text-sm text-muted-foreground mt-1">{{ t('orgSettings.customProviderDescription') }}</p>
      </div>

      <div v-if="!loading" class="space-y-3">
        <div
          v-for="cp in customProviders"
          :key="cp.id"
          class="rounded-lg border border-border bg-card p-4"
        >
          <div class="flex items-center justify-between mb-2">
            <div>
              <span class="font-medium text-sm">{{ cp.label || cp.provider }}</span>
              <span v-if="cp.label" class="text-xs text-muted-foreground ml-2">{{ cp.provider }}</span>
            </div>
            <span
              class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium"
              :class="cp.is_active ? 'bg-green-500/10 text-green-500' : 'bg-muted text-muted-foreground'"
            >
              <Check v-if="cp.is_active" class="w-3 h-3" />
              <X v-else class="w-3 h-3" />
              {{ cp.is_active ? t('orgSettings.llmKeysConfigured') : t('orgSettings.llmKeysDisabled') }}
            </span>
          </div>
          <div class="space-y-1 text-xs text-muted-foreground mb-3">
            <div class="font-mono">{{ cp.api_key_masked }}</div>
            <div v-if="cp.base_url" class="truncate">{{ cp.base_url }}</div>
            <div v-if="cp.api_type" class="inline-flex px-1.5 py-0.5 rounded bg-muted text-muted-foreground text-[10px]">
              {{ API_TYPE_OPTIONS.find(o => o.value === cp.api_type)?.label || cp.api_type }}
            </div>
          </div>
          <div class="flex items-center gap-2">
            <button
              class="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md border border-border text-sm hover:bg-muted transition-colors"
              @click="openConfigure(cp.provider)"
            >
              <Settings class="w-3.5 h-3.5" />
              {{ t('orgSettings.llmKeysSettings') }}
            </button>
            <button
              class="px-3 py-1.5 rounded-md text-sm text-destructive hover:bg-destructive/10 transition-colors"
              @click="handleDelete(cp.provider)"
            >
              <Trash2 class="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <!-- Add custom provider -->
        <div v-if="showCustomForm" class="rounded-lg border border-dashed border-violet-400/50 bg-card p-4 space-y-3">
          <div class="space-y-1.5">
            <label class="text-sm font-medium">{{ t('orgSettings.customProviderSlug') }}</label>
            <input
              v-model="customSlug"
              class="w-full px-3 py-2 rounded-md border border-border bg-background text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary/50"
              :placeholder="t('orgSettings.customProviderSlugHint')"
              @keyup.enter="addCustomProvider"
            />
            <p v-if="customSlugError" class="text-xs text-destructive">{{ customSlugError }}</p>
          </div>
          <div class="flex items-center gap-2">
            <button
              class="px-4 py-1.5 rounded-md bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors"
              @click="addCustomProvider"
            >
              {{ t('common.next') }}
            </button>
            <button
              class="px-4 py-1.5 rounded-md border border-border text-sm hover:bg-muted transition-colors"
              @click="showCustomForm = false; customSlug = ''; customSlugError = ''"
            >
              {{ t('common.cancel') }}
            </button>
          </div>
        </div>

        <button
          v-if="!showCustomForm"
          class="w-full px-4 py-3 rounded-lg border border-dashed border-violet-400/50 bg-card text-sm text-violet-400 hover:border-violet-400 hover:bg-violet-500/5 transition-colors flex items-center justify-center gap-1.5"
          @click="showCustomForm = true"
        >
          <Plus class="w-4 h-4" />
          {{ t('orgSettings.customProviderAdd') }}
        </button>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="showDialog" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="absolute inset-0 bg-black/50" @click="showDialog = false" />
        <div class="relative w-full max-w-md mx-4 rounded-lg border border-border bg-card shadow-lg">
          <div class="px-6 pt-6 pb-4">
            <h3 class="text-lg font-semibold">
              {{ PROVIDER_LABELS[dialogProvider] || dialogProvider }}
              <span class="text-sm font-normal text-muted-foreground ml-2">
                {{ isEditing ? t('orgSettings.llmKeysEditTitle') : t('orgSettings.llmKeysAddTitle') }}
              </span>
            </h3>
          </div>

          <div class="px-6 space-y-4">
            <template v-if="isCustomProvider(dialogProvider)">
              <div class="space-y-1.5">
                <label class="text-sm font-medium">{{ t('orgSettings.customProviderLabel') }}</label>
                <input
                  v-model="form.label"
                  class="w-full px-3 py-2 rounded-md border border-border bg-background text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
                  :placeholder="t('orgSettings.customProviderLabelPlaceholder')"
                />
              </div>
              <div class="space-y-1.5">
                <label class="text-sm font-medium">{{ t('orgSettings.customProviderApiType') }}</label>
                <div class="relative">
                  <select
                    v-model="form.api_type"
                    class="w-full appearance-none px-3 py-2 pr-8 rounded-md border border-border bg-background text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
                  >
                    <option v-for="opt in API_TYPE_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                  </select>
                  <ChevronDown class="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
                </div>
              </div>
            </template>

            <div class="space-y-1.5">
              <label class="text-sm font-medium">{{ t('orgSettings.llmKeysApiKey') }}</label>
              <input
                v-model="form.api_key"
                type="password"
                class="w-full px-3 py-2 rounded-md border border-border bg-background text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary/50"
                :placeholder="isEditing ? t('orgSettings.llmKeysApiKeyEditHint') : t('orgSettings.llmKeysApiKeyPlaceholder')"
              />
            </div>

            <div class="space-y-1.5">
              <label class="text-sm font-medium">
                {{ t('orgSettings.llmKeysBaseUrl') }}
                <span v-if="isCustomProvider(dialogProvider)" class="text-destructive ml-0.5">*</span>
              </label>
              <input
                v-model="form.base_url"
                class="w-full px-3 py-2 rounded-md border border-border bg-background text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary/50"
                :placeholder="isCustomProvider(dialogProvider) ? t('orgSettings.customProviderBaseUrlRequired') : t('orgSettings.llmKeysBaseUrlPlaceholder')"
              />
              <label v-if="form.base_url" class="flex items-center gap-2 mt-1.5 cursor-pointer">
                <input type="checkbox" v-model="form.skip_ssl_verify" class="accent-primary" />
                <span class="text-sm">{{ t('orgSettings.llmKeysSkipSslVerify') }}</span>
                <span class="text-xs text-muted-foreground">{{ t('orgSettings.llmKeysSkipSslVerifyHint') }}</span>
              </label>
            </div>

            <ModelSelect
              :provider="dialogProvider"
              v-model="testModel"
              allow-manual-input
              @fetch-models="handleFetchModels"
            />

            <div class="grid gap-3" :class="isEE ? 'grid-cols-2' : 'grid-cols-1'">
              <div v-if="isEE" class="space-y-1.5">
                <label class="text-sm font-medium">{{ t('orgSettings.llmKeysOrgTokenLimit') }}</label>
                <input
                  v-model="form.org_token_limit"
                  type="number"
                  class="w-full px-3 py-2 rounded-md border border-border bg-background text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
                  :placeholder="t('orgSettings.llmKeysOrgTokenLimitHint')"
                />
              </div>
              <div class="space-y-1.5">
                <label class="text-sm font-medium">{{ isEE ? t('orgSettings.llmKeysSysTokenLimit') : t('orgSettings.llmKeysTokenLimit') }}</label>
                <input
                  v-model="form.system_token_limit"
                  type="number"
                  class="w-full px-3 py-2 rounded-md border border-border bg-background text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
                  :placeholder="isEE ? t('orgSettings.llmKeysSysTokenLimitHint') : t('orgSettings.llmKeysTokenLimitHint')"
                />
              </div>
            </div>

            <div v-if="isEditing" class="flex items-center gap-2">
              <input type="checkbox" id="edit-active" v-model="form.is_active" class="accent-primary" />
              <label for="edit-active" class="text-sm cursor-pointer">{{ t('orgSettings.llmKeysStatusActive') }}</label>
            </div>
          </div>

          <div v-if="testResult" class="mx-6 mt-2 px-3 py-2 rounded-md text-sm" :class="testResult.ok ? 'bg-green-500/10 text-green-600 dark:text-green-400' : 'bg-destructive/10 text-destructive'">
            <div class="flex items-center gap-1.5">
              <CheckCircle v-if="testResult.ok" class="w-4 h-4 shrink-0" />
              <XCircle v-else class="w-4 h-4 shrink-0" />
              <span>{{ testResult.message }}</span>
            </div>
            <div v-if="testResult.ok && (testResult.tested_model || testResult.latency_ms != null)" class="mt-1 text-xs opacity-80 ml-5.5">
              <span v-if="testResult.tested_model">{{ t('orgSettings.testConnectionModel', { model: testResult.tested_model }) }}</span>
              <span v-if="testResult.tested_model && testResult.latency_ms != null" class="mx-1">/</span>
              <span v-if="testResult.latency_ms != null">{{ t('orgSettings.testConnectionLatency', { ms: testResult.latency_ms }) }}</span>
            </div>
            <div v-if="!testResult.ok && testResult.error_detail" class="mt-1.5 text-xs opacity-70 ml-5.5 font-mono break-all">
              {{ testResult.error_detail }}
            </div>
          </div>

          <div class="flex items-center justify-between px-6 py-4 mt-2">
            <button
              class="flex items-center gap-1.5 px-3 py-2 rounded-md border border-border text-sm hover:bg-muted transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="!canTest || testing"
              @click="handleTest"
            >
              <Loader2 v-if="testing" class="w-3.5 h-3.5 animate-spin" />
              <Zap v-else class="w-3.5 h-3.5" />
              {{ testing ? t('orgSettings.llmTestConnectionTesting') : t('orgSettings.llmTestConnection') }}
            </button>
            <div class="flex gap-2">
              <button
                class="px-4 py-2 rounded-md border border-border text-sm hover:bg-muted transition-colors"
                @click="showDialog = false"
              >
                {{ t('common.cancel') }}
              </button>
              <button
                class="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="!canSave || saving"
                @click="handleSave"
              >
                <span v-if="saving" class="flex items-center gap-1.5">
                  <Loader2 class="w-3.5 h-3.5 animate-spin" />
                  {{ t('common.saving') }}
                </span>
                <span v-else>{{ t('common.save') }}</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
