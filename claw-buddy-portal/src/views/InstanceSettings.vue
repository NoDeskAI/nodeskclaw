<script setup lang="ts">
import { ref, computed, onMounted, inject, type ComputedRef, type Ref } from 'vue'
import { Loader2, Brain, Key, Trash2, Plus, RefreshCw, Circle, AlertTriangle, HardDrive, Save, ChevronDown, Check } from 'lucide-vue-next'
import api from '@/services/api'

const instanceId = inject<ComputedRef<string>>('instanceId')!
const instanceOrgId = inject<Ref<string | null>>('instanceOrgId')!

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
  'minimax-openai': 'Minimax-OpenAI',
  'minimax-anthropic': 'Minimax-Anthropic',
}

// ── Types ──

interface AvailableOrgKey {
  id: string
  provider: string
  label: string
  api_key_masked: string
  is_active: boolean
}

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
  orgKeyId: string
  personalKeyNew: string
  personalKeyMasked: string
  hasExistingPersonalKey: boolean
}

// ── State ──

const providerConfigs = ref<ProviderConfig[]>([])
const availableOrgKeys = ref<AvailableOrgKey[]>([])
const personalKeys = ref<PersonalKey[]>([])
const newProviderOpen = ref(false)

const unusedProviders = computed(() =>
  PROVIDERS.filter(p => !providerConfigs.value.some(c => c.provider === p))
)

function orgKeysForProvider(provider: string) {
  return availableOrgKeys.value.filter(k => k.provider === provider)
}

function personalKeyForProvider(provider: string) {
  return personalKeys.value.find(k => k.provider === provider)
}

// ── Data loading ──

async function loadAll() {
  loading.value = true
  error.value = ''
  nfsError.value = ''
  successMsg.value = ''

  const orgId = instanceOrgId.value

  try {
    const requests: Promise<any>[] = [
      api.get(`/instances/${instanceId.value}/openclaw-providers`),
      api.get('/users/me/llm-keys'),
    ]
    if (orgId) {
      requests.push(
        api.get(`/users/me/llm-configs?org_id=${orgId}`),
        api.get(`/orgs/${orgId}/available-llm-keys`),
      )
    }

    const results = await Promise.allSettled(requests)

    // NFS providers
    const nfsResult = results[0]
    if (nfsResult.status === 'fulfilled') {
      const data = nfsResult.value.data.data
      dataSource.value = data.data_source ?? ''
    } else {
      const e = nfsResult.reason
      const status = e?.response?.status
      const msg = e?.response?.data?.message || ''
      if (status === 503 && (msg.includes('NFS') || msg.includes('nfs') || msg.includes('mount') || msg.includes('挂载'))) {
        nfsError.value = msg
      }
    }

    // Personal keys
    if (results[1].status === 'fulfilled') {
      personalKeys.value = results[1].value.data.data ?? []
    }

    // User LLM configs (DB)
    const dbConfigs: { provider: string; key_source: string; org_llm_key_id: string | null }[] = []
    if (results[2]?.status === 'fulfilled') {
      dbConfigs.push(...(results[2].value.data.data ?? []))
    }

    // Available org keys
    if (results[3]?.status === 'fulfilled') {
      availableOrgKeys.value = results[3].value.data.data ?? []
    }

    // Build editable provider configs from DB configs
    const configs: ProviderConfig[] = []
    for (const c of dbConfigs) {
      const pk = personalKeyForProvider(c.provider)
      configs.push({
        provider: c.provider,
        keySource: (c.key_source === 'org' || c.key_source === 'personal') ? c.key_source : 'personal',
        orgKeyId: c.org_llm_key_id ?? '',
        personalKeyNew: '',
        personalKeyMasked: pk?.api_key_masked ?? '',
        hasExistingPersonalKey: !!pk,
      })
    }

    // If DB has no configs but NFS has providers, populate from NFS
    if (configs.length === 0 && nfsResult.status === 'fulfilled') {
      const nfsProviders = nfsResult.value.data.data?.providers ?? []
      for (const np of nfsProviders) {
        const pk = personalKeyForProvider(np.provider)
        configs.push({
          provider: np.provider,
          keySource: np.key_source === 'org' ? 'org' : 'personal',
          orgKeyId: '',
          personalKeyNew: '',
          personalKeyMasked: pk?.api_key_masked ?? np.api_key_masked ?? '',
          hasExistingPersonalKey: !!pk,
        })
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
  const hasOrgKeys = orgKeysForProvider(provider).length > 0
  const pk = personalKeyForProvider(provider)
  providerConfigs.value.push({
    provider,
    keySource: hasOrgKeys ? 'org' : 'personal',
    orgKeyId: '',
    personalKeyNew: '',
    personalKeyMasked: pk?.api_key_masked ?? '',
    hasExistingPersonalKey: !!pk,
  })
  newProviderOpen.value = false
  dirty.value = true
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
    } else if (cfg.keySource === 'org') {
      if (!cfg.orgKeyId) {
        return `${label}: 请选择组织 Key`
      }
    }
  }
  return null
}

// ── Save ──

async function handleSave() {
  const validationError = validateConfigs()
  if (validationError) {
    error.value = validationError
    return
  }

  const orgId = instanceOrgId.value
  if (!orgId) {
    error.value = '实例未关联组织，无法保存配置'
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

    // 2. Save LLM configs
    await api.put('/users/me/llm-configs', {
      org_id: orgId,
      configs: providerConfigs.value.map(c => ({
        provider: c.provider,
        key_source: c.keySource,
        org_llm_key_id: c.keySource === 'org' ? c.orgKeyId || null : null,
      })),
    })

    // 3. Restart OpenClaw
    restarting.value = true
    const res = await api.post(`/instances/${instanceId.value}/restart-openclaw`)
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
    // Refresh personal keys list
    const pkRes = await api.get('/users/me/llm-keys')
    personalKeys.value = pkRes.data.data ?? []
  } catch (e: any) {
    error.value = e?.response?.data?.message || '保存失败'
  } finally {
    saving.value = false
    restarting.value = false
  }
}

onMounted(loadAll)
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
            :disabled="saving || restarting || !dirty"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs transition-colors"
            :class="dirty
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
              <div v-if="orgKeysForProvider(cfg.provider).length > 0" class="flex gap-4 text-sm">
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
                <label class="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="radio"
                    :name="`ks-${cfg.provider}`"
                    value="org"
                    v-model="cfg.keySource"
                    class="accent-primary"
                    @change="markDirty"
                  />
                  组织 Key
                </label>
              </div>

              <!-- Org key selector -->
              <select
                v-if="cfg.keySource === 'org'"
                v-model="cfg.orgKeyId"
                class="w-full px-3 py-1.5 rounded-md bg-background border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
                @change="markDirty"
              >
                <option value="" disabled>选择组织 Key</option>
                <option
                  v-for="k in orgKeysForProvider(cfg.provider)"
                  :key="k.id"
                  :value="k.id"
                >
                  {{ k.label }} ({{ k.api_key_masked }})
                </option>
              </select>

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
                    :placeholder="cfg.hasExistingPersonalKey ? '输入新 Key 以替换' : '粘贴你的 API Key'"
                    class="w-full pl-9 pr-3 py-1.5 rounded-md bg-background border border-border text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary/50"
                    @input="markDirty"
                  />
                </div>
              </div>
            </div>
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

        <!-- Save button (bottom, for when there are configs) -->
        <div v-if="providerConfigs.length > 0 && dirty" class="pt-2">
          <button
            :disabled="saving || restarting"
            class="w-full py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            @click="handleSave"
          >
            <Loader2 v-if="saving || restarting" class="w-4 h-4 animate-spin" />
            <Save v-else class="w-4 h-4" />
            {{ restarting ? '重启中...' : saving ? '保存中...' : '保存配置并重启 OpenClaw' }}
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
