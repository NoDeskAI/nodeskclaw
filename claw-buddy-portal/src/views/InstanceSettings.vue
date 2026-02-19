<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Loader2, Brain, Key, Save, Trash2, Plus, RefreshCw } from 'lucide-vue-next'
import api from '@/services/api'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const instanceId = computed(() => route.params.id as string)
const instanceName = ref('')
const loading = ref(true)
const saving = ref(false)
const restarting = ref(false)
const error = ref('')
const successMsg = ref('')

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
}

interface PersonalKey {
  id: string
  provider: string
  api_key_masked: string
  base_url: string | null
  is_active: boolean
}

const PROVIDERS = ['openai', 'anthropic', 'gemini', 'openrouter'] as const
const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  gemini: 'Google Gemini',
  openrouter: 'OpenRouter',
}

const availableOrgKeys = ref<AvailableKey[]>([])
const llmConfigs = ref<LlmConfigEntry[]>([])
const personalKeys = ref<PersonalKey[]>([])

const newKeyProvider = ref('')
const newKeyValue = ref('')
const newKeyBaseUrl = ref('')
const addingKey = ref(false)

function orgKeysForProvider(provider: string) {
  return availableOrgKeys.value.filter(k => k.provider === provider)
}

async function fetchAll() {
  loading.value = true
  const orgId = authStore.user?.current_org_id
  if (!orgId) return

  try {
    const [instanceRes, keysRes, configsRes, personalRes] = await Promise.all([
      api.get(`/instances/${instanceId.value}/llm-config`),
      api.get(`/orgs/${orgId}/available-llm-keys`),
      api.get('/users/me/llm-configs', { params: { org_id: orgId } }),
      api.get('/users/me/llm-keys'),
    ])

    availableOrgKeys.value = keysRes.data.data ?? []
    personalKeys.value = personalRes.data.data ?? []

    const existing: Record<string, any> = {}
    for (const c of (configsRes.data.data ?? [])) {
      existing[c.provider] = c
    }

    llmConfigs.value = PROVIDERS.map(p => {
      const cfg = existing[p]
      return {
        provider: p,
        keySource: cfg?.key_source ?? 'none',
        orgKeyId: cfg?.org_llm_key_id ?? '',
      }
    })

    // Fetch instance name from the LLM config endpoint data or the route
    const instanceDetail = instanceRes.data.data
    if (Array.isArray(instanceDetail) && instanceDetail.length > 0) {
      // configs come from instance, name from route or separate call
    }
  } catch {
    error.value = '加载配置失败'
  } finally {
    loading.value = false
  }
}

async function fetchInstanceName() {
  try {
    const res = await api.get(`/instances/${instanceId.value}`)
    instanceName.value = res.data.data?.name ?? ''
  } catch {
    // ignore
  }
}

async function saveConfigs() {
  const orgId = authStore.user?.current_org_id
  if (!orgId) return

  saving.value = true
  error.value = ''
  successMsg.value = ''

  try {
    const configs = llmConfigs.value
      .filter(c => c.keySource !== 'none')
      .map(c => ({
        provider: c.provider,
        key_source: c.keySource,
        org_llm_key_id: c.keySource === 'org' ? c.orgKeyId || undefined : undefined,
      }))

    const res = await api.put('/users/me/llm-configs', {
      org_id: orgId,
      configs,
    })

    const result = res.data.data
    if (result?.needs_restart && result.affected_instances?.length > 0) {
      const names = result.affected_instances.map((i: any) => i.name).join(', ')
      if (confirm(`配置已保存。以下实例需要重启 OpenClaw 以加载新 Provider，OpenClaw 会在完成当前任务后重启：\n\n${names}\n\n确认重启？`)) {
        await restartOpenClaw()
      } else {
        successMsg.value = '配置已保存（未重启）'
      }
    } else {
      successMsg.value = '配置已保存'
    }
  } catch (e: any) {
    error.value = e?.response?.data?.message || '保存失败'
  } finally {
    saving.value = false
  }
}

async function restartOpenClaw() {
  restarting.value = true
  try {
    const res = await api.post(`/instances/${instanceId.value}/restart-openclaw`)
    const result = res.data.data
    if (result?.status === 'ok') {
      successMsg.value = 'OpenClaw 已重启完成'
    } else if (result?.status === 'timeout') {
      error.value = result.message || '重启超时'
    } else {
      error.value = result?.message || '重启失败'
    }
  } catch (e: any) {
    error.value = e?.response?.data?.message || '重启请求失败'
  } finally {
    restarting.value = false
  }
}

async function addPersonalKey() {
  if (!newKeyProvider.value || !newKeyValue.value) return
  addingKey.value = true
  try {
    await api.post('/users/me/llm-keys', {
      provider: newKeyProvider.value,
      api_key: newKeyValue.value,
      base_url: newKeyBaseUrl.value || undefined,
    })
    newKeyProvider.value = ''
    newKeyValue.value = ''
    newKeyBaseUrl.value = ''
    const res = await api.get('/users/me/llm-keys')
    personalKeys.value = res.data.data ?? []
  } catch (e: any) {
    error.value = e?.response?.data?.message || '添加失败'
  } finally {
    addingKey.value = false
  }
}

async function deletePersonalKey(provider: string) {
  if (!confirm(`确认删除 ${PROVIDER_LABELS[provider] || provider} 的个人 Key？`)) return
  try {
    await api.delete(`/users/me/llm-keys/${provider}`)
    personalKeys.value = personalKeys.value.filter(k => k.provider !== provider)
  } catch (e: any) {
    error.value = e?.response?.data?.message || '删除失败'
  }
}

onMounted(() => {
  fetchInstanceName()
  fetchAll()
})
</script>

<template>
  <div class="max-w-2xl mx-auto px-6 py-8">
    <div class="flex items-center gap-3 mb-8">
      <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" @click="router.push(`/instances/${instanceId}`)">
        <ArrowLeft class="w-5 h-5" />
      </button>
      <div>
        <h1 class="text-xl font-bold">{{ instanceName || '实例' }} 设置</h1>
        <p class="text-sm text-muted-foreground mt-1">管理大模型配置和 API Key</p>
      </div>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <div v-else class="space-y-8">
      <!-- 重启中提示 -->
      <div v-if="restarting" class="flex items-center gap-3 p-4 rounded-lg bg-amber-500/10 border border-amber-500/20">
        <RefreshCw class="w-5 h-5 text-amber-500 animate-spin" />
        <span class="text-sm">OpenClaw 正在完成当前任务并重启...</span>
      </div>

      <!-- 消息提示 -->
      <p v-if="error" class="text-sm text-destructive">{{ error }}</p>
      <p v-if="successMsg" class="text-sm text-green-500">{{ successMsg }}</p>

      <!-- 大模型配置 -->
      <div class="space-y-4">
        <div class="flex items-center gap-2">
          <Brain class="w-4 h-4 text-violet-400" />
          <h2 class="text-sm font-medium">大模型配置</h2>
        </div>
        <p class="text-xs text-muted-foreground">
          Key 选择为用户级别设置，更改会影响你在该组织下的所有实例
        </p>

        <div class="space-y-3">
          <div
            v-for="cfg in llmConfigs"
            :key="cfg.provider"
            class="rounded-lg border border-border bg-card p-4 space-y-3"
          >
            <div class="font-medium text-sm">{{ PROVIDER_LABELS[cfg.provider] || cfg.provider }}</div>

            <div class="space-y-2">
              <label class="flex items-center gap-2 text-sm cursor-pointer">
                <input type="radio" :name="`llm-${cfg.provider}`" value="none" v-model="cfg.keySource" class="accent-primary" />
                <span class="text-muted-foreground">不使用</span>
              </label>

              <label v-if="orgKeysForProvider(cfg.provider).length > 0" class="flex items-center gap-2 text-sm cursor-pointer">
                <input type="radio" :name="`llm-${cfg.provider}`" value="org" v-model="cfg.keySource" class="accent-primary" />
                <span>使用组织 Key</span>
              </label>
              <select
                v-if="cfg.keySource === 'org' && orgKeysForProvider(cfg.provider).length > 0"
                v-model="cfg.orgKeyId"
                class="ml-6 w-[calc(100%-1.5rem)] px-3 py-1.5 rounded-md bg-background border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
              >
                <option value="" disabled>选择 Key</option>
                <option v-for="k in orgKeysForProvider(cfg.provider)" :key="k.id" :value="k.id">
                  {{ k.label }} ({{ k.api_key_masked }})
                </option>
              </select>

              <label class="flex items-center gap-2 text-sm cursor-pointer">
                <input type="radio" :name="`llm-${cfg.provider}`" value="personal" v-model="cfg.keySource" class="accent-primary" />
                <span>使用个人 Key</span>
                <span v-if="personalKeys.find(k => k.provider === cfg.provider)" class="text-xs text-muted-foreground">
                  ({{ personalKeys.find(k => k.provider === cfg.provider)?.api_key_masked }})
                </span>
              </label>
            </div>
          </div>
        </div>

        <button
          :disabled="saving"
          class="w-full py-2.5 px-4 rounded-lg bg-primary text-primary-foreground font-medium text-sm hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          @click="saveConfigs"
        >
          <Loader2 v-if="saving" class="w-4 h-4 animate-spin" />
          <Save v-else class="w-4 h-4" />
          {{ saving ? '保存中...' : '保存配置' }}
        </button>
      </div>

      <!-- 个人 Key 管理 -->
      <div class="space-y-4">
        <div class="flex items-center gap-2">
          <Key class="w-4 h-4 text-amber-400" />
          <h2 class="text-sm font-medium">个人 Key 管理</h2>
        </div>

        <div v-if="personalKeys.length > 0" class="rounded-lg border border-border overflow-hidden">
          <table class="w-full text-sm">
            <thead class="bg-muted/50">
              <tr>
                <th class="text-left px-4 py-2 font-medium">Provider</th>
                <th class="text-left px-4 py-2 font-medium">Key</th>
                <th class="text-left px-4 py-2 font-medium">Base URL</th>
                <th class="px-4 py-2 w-16"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="k in personalKeys" :key="k.id" class="border-t border-border">
                <td class="px-4 py-2">{{ PROVIDER_LABELS[k.provider] || k.provider }}</td>
                <td class="px-4 py-2 font-mono text-xs">{{ k.api_key_masked }}</td>
                <td class="px-4 py-2 text-xs text-muted-foreground">{{ k.base_url || '(默认)' }}</td>
                <td class="px-4 py-2">
                  <button class="p-1 rounded hover:bg-destructive/10 text-destructive transition-colors" @click="deletePersonalKey(k.provider)">
                    <Trash2 class="w-3.5 h-3.5" />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="text-xs text-muted-foreground">暂无个人 Key</p>

        <!-- 添加个人 Key -->
        <div class="rounded-lg border border-border bg-card p-4 space-y-3">
          <div class="text-sm font-medium flex items-center gap-1.5">
            <Plus class="w-3.5 h-3.5" />
            添加个人 Key
          </div>
          <div class="grid grid-cols-2 gap-3">
            <select
              v-model="newKeyProvider"
              class="px-3 py-1.5 rounded-md bg-background border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
            >
              <option value="" disabled>选择 Provider</option>
              <option v-for="p in PROVIDERS" :key="p" :value="p">{{ PROVIDER_LABELS[p] || p }}</option>
            </select>
            <input
              v-model="newKeyBaseUrl"
              type="text"
              placeholder="Base URL (可选)"
              class="px-3 py-1.5 rounded-md bg-background border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
            />
          </div>
          <input
            v-model="newKeyValue"
            type="password"
            placeholder="API Key"
            class="w-full px-3 py-1.5 rounded-md bg-background border border-border text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary/50"
          />
          <button
            :disabled="!newKeyProvider || !newKeyValue || addingKey"
            class="px-4 py-1.5 rounded-md bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-1.5"
            @click="addPersonalKey"
          >
            <Loader2 v-if="addingKey" class="w-3.5 h-3.5 animate-spin" />
            <Plus v-else class="w-3.5 h-3.5" />
            {{ addingKey ? '添加中...' : '添加' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
