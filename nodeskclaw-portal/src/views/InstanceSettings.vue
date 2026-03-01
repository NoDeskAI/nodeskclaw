<script setup lang="ts">
import { ref, computed, watch, inject, type ComputedRef, type Ref } from 'vue'
import { Loader2, Brain, Key, Trash2, Plus, RefreshCw, HardDrive, Save, ChevronDown, Check } from 'lucide-vue-next'
import ModelSelect from '@/components/shared/ModelSelect.vue'
import type { ModelItem } from '@/components/shared/ModelSelect.vue'
import api from '@/services/api'

const instanceId = inject<ComputedRef<string>>('instanceId')!
const instanceOrgId = inject<Ref<string | null>>('instanceOrgId')!  // kept for model catalog requests

const loading = ref(true)
const saving = ref(false)
const restarting = ref(false)
const error = ref('')
const successMsg = ref('')
const nfsError = ref('')
const dataSource = ref('')
const dirty = ref(false)

// ── Constants ──

const PROVIDERS = ['openai', 'anthropic', 'gemini', 'openrouter', 'minimax-openai', 'minimax-anthropic'] as const
const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  gemini: 'Google Gemini',
  openrouter: 'OpenRouter',
  'minimax-openai': 'MiniMax-OpenAI (CN)',
  'minimax-anthropic': 'MiniMax-Anthropic (CN)',
}

// ── Types ──

interface PersonalKey {
  id: string
  provider: string
  api_key_masked: string
  base_url: string | null
  is_active: boolean
}

interface ProviderConfig {
  provider: string
  keySource: 'org' | 'personal'
  personalKeyNew: string
  personalKeyMasked: string
  hasExistingPersonalKey: boolean
  selectedModel: ModelItem | null
}

const BUILTIN_PROVIDERS = new Set(['openai', 'anthropic', 'gemini', 'openrouter'])
const WORKING_PLAN_PROVIDERS = new Set(['minimax-openai', 'minimax-anthropic'])

// ── State ──

const providerConfigs = ref<ProviderConfig[]>([])
const personalKeys = ref<PersonalKey[]>([])
const newProviderOpen = ref(false)

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
    const [configsResult, keysResult] = await Promise.allSettled([
      api.get(`/instances/${instanceId.value}/llm-configs`),
      api.get('/users/me/llm-keys'),
    ])

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

    const podConfigs: { provider: string; key_source: string; selected_models?: any[]; personal_key_masked?: string }[] =
      configsResult.status === 'fulfilled' ? (configsResult.value.data.data ?? []) : []

    const configs: ProviderConfig[] = []
    for (const c of podConfigs) {
      const pk = personalKeyForProvider(c.provider)
      configs.push({
        provider: c.provider,
        keySource: (c.key_source === 'org' || c.key_source === 'personal') ? c.key_source : 'org',
        personalKeyNew: '',
        personalKeyMasked: pk?.api_key_masked ?? c.personal_key_masked ?? '',
        hasExistingPersonalKey: !!pk,
        selectedModel: (c.selected_models ?? [])[0] ?? null,
      })
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
  providerConfigs.value.push({
    provider,
    keySource: WORKING_PLAN_PROVIDERS.has(provider) ? 'org' : 'personal',
    personalKeyNew: '',
    personalKeyMasked: pk?.api_key_masked ?? '',
    hasExistingPersonalKey: !!pk,
    selectedModel: null,
  })
  newProviderOpen.value = false
  dirty.value = true
}

async function handleFetchModels(provider: string, callback: (models: ModelItem[], error?: string) => void) {
  const cfg = providerConfigs.value.find(c => c.provider === provider)
  const params: Record<string, string> = {}
  if (cfg?.keySource === 'personal' && cfg.personalKeyNew) {
    params.api_key = cfg.personalKeyNew
  }
  if (instanceOrgId.value) {
    params.org_id = instanceOrgId.value
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
  providerConfigs.value.splice(idx, 1)
  dirty.value = true
}

function markDirty() {
  dirty.value = true
}

// ── Validation ──

function validateConfigs(): string | null {
  for (const cfg of providerConfigs.value) {
    const label = PROVIDER_LABELS[cfg.provider] || cfg.provider
    if (cfg.keySource === 'personal') {
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
    // 1. Upsert personal keys
    for (const cfg of providerConfigs.value) {
      if (cfg.keySource === 'personal' && cfg.personalKeyNew) {
        await api.post('/users/me/llm-keys', {
          provider: cfg.provider,
          api_key: cfg.personalKeyNew,
        })
        cfg.personalKeyMasked = cfg.personalKeyNew.length > 8
          ? cfg.personalKeyNew.slice(0, 6) + '***' + cfg.personalKeyNew.slice(-3)
          : cfg.personalKeyNew.slice(0, 2) + '***'
        cfg.personalKeyNew = ''
        cfg.hasExistingPersonalKey = true
      }
    }

    // 2. Write configs directly to Pod file
    await api.put(`/instances/${instanceId.value}/llm-configs`, {
      configs: providerConfigs.value.map(c => ({
        provider: c.provider,
        key_source: c.keySource,
        selected_models: c.selectedModel ? [c.selectedModel] : undefined,
      })),
    })

    // 3. Restart OpenClaw
    restarting.value = true
    const res = await api.post(`/instances/${instanceId.value}/restart-openclaw`, null, { timeout: 120000 })
    const result = res.data.data
    if (result?.status === 'ok') {
      successMsg.value = '配置已保存，OpenClaw 已重启'
    } else if (result?.status === 'timeout') {
      successMsg.value = '配置已保存，但 OpenClaw 重启超时，请检查实例状态'
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
</script>

<template>
  <div>
    <div v-if="loading" class="flex items-center justify-center py-20">
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
            v-if="providerConfigs.length > 0"
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
        <span class="text-xs">OpenClaw 正在完成当前任务并重启...</span>
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
            当前实例未配置大模型 Provider，选择一个开始配置
          </p>
          <div class="grid grid-cols-2 gap-2">
            <button
              v-for="p in unusedProviders"
              :key="p"
              class="px-4 py-3 rounded-lg border border-border bg-card text-sm text-left hover:border-primary/50 hover:bg-primary/5 transition-colors cursor-pointer"
              @click="addProvider(p)"
            >
              {{ PROVIDER_LABELS[p] || p }}
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
              <span class="font-medium text-sm">{{ PROVIDER_LABELS[cfg.provider] || cfg.provider }}</span>
              <button
                class="text-muted-foreground hover:text-destructive transition-colors"
                @click="removeProvider(idx)"
              >
                <Trash2 class="w-4 h-4" />
              </button>
            </div>

            <!-- Key source selection -->
            <div class="space-y-2">
              <div class="flex gap-4 text-sm">
                <span class="relative group">
                  <label
                    class="flex items-center gap-1.5"
                    :class="WORKING_PLAN_PROVIDERS.has(cfg.provider) ? 'cursor-pointer' : 'cursor-not-allowed opacity-50'"
                  >
                    <input
                      type="radio"
                      :name="`ks-${cfg.provider}`"
                      value="org"
                      v-model="cfg.keySource"
                      class="accent-primary"
                      :disabled="!WORKING_PLAN_PROVIDERS.has(cfg.provider)"
                      @change="markDirty"
                    />
                    Working Plan
                  </label>
                  <span
                    v-if="!WORKING_PLAN_PROVIDERS.has(cfg.provider)"
                    class="pointer-events-none absolute z-50 top-full left-1/2 -translate-x-1/2 mt-1.5 whitespace-nowrap rounded bg-popover px-2 py-1 text-xs text-popover-foreground shadow-md border border-border invisible group-hover:visible"
                  >
                    该 Provider 暂未开放 Working Plan
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
                  个人 Key
                </label>
              </div>

              <!-- Working Plan hint -->
              <p v-if="cfg.keySource === 'org'" class="text-xs text-muted-foreground pl-0.5">
                使用组织统一配置的 Key，无需自行输入
              </p>

              <!-- Personal key -->
              <div v-if="cfg.keySource === 'personal'" class="space-y-1.5">
                <div v-if="cfg.hasExistingPersonalKey" class="flex items-center gap-2 text-xs">
                  <Check class="w-3 h-3 text-green-400" />
                  <span class="text-muted-foreground">当前 Key:</span>
                  <span class="font-mono">{{ cfg.personalKeyMasked }}</span>
                </div>
                <div class="relative">
                  <Key class="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                  <input
                    v-model="cfg.personalKeyNew"
                    type="password"
                    :placeholder="cfg.hasExistingPersonalKey ? '输入新 Key 以替换' : '输入 API Key'"
                    class="w-full pl-9 pr-3 py-1.5 rounded-md bg-background border border-border text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary/50"
                    @input="markDirty"
                  />
                </div>
              </div>
            </div>

            <!-- Model selection -->
            <ModelSelect
              :provider="cfg.provider"
              v-model="cfg.selectedModel"
              @fetch-models="handleFetchModels"
              @update:model-value="markDirty"
            />
            <p v-if="!BUILTIN_PROVIDERS.has(cfg.provider) && !cfg.selectedModel" class="text-[10px] text-amber-500">
              自定义 Provider 需要选择一个模型
            </p>
          </div>

          <!-- Add provider -->
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
                {{ PROVIDER_LABELS[p] || p }}
              </button>
            </div>
          </div>
        </div>

      </template>
    </div>

    <!-- Close dropdown overlay -->
    <Teleport to="body">
      <div v-if="newProviderOpen" class="fixed inset-0 z-5" @click="newProviderOpen = false" />
    </Teleport>
  </div>
</template>
