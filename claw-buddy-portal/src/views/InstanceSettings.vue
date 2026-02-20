<script setup lang="ts">
import { ref, onMounted, inject, type ComputedRef } from 'vue'
import { Loader2, Brain, Key, Trash2, Plus, RefreshCw, Circle, AlertTriangle, HardDrive } from 'lucide-vue-next'
import api from '@/services/api'

const instanceId = inject<ComputedRef<string>>('instanceId')!
const loading = ref(true)
const restarting = ref(false)
const error = ref('')
const successMsg = ref('')

const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  gemini: 'Google Gemini',
  openrouter: 'OpenRouter',
  'minimax-openai': 'Minimax-OpenAI',
  'minimax-anthropic': 'Minimax-Anthropic',
}

interface ProviderEntry {
  provider: string
  base_url: string
  is_proxy: boolean
  key_source: string | null
  key_label: string | null
  api_key_masked: string | null
}

interface PersonalKey {
  id: string
  provider: string
  api_key_masked: string
  base_url: string | null
  is_active: boolean
}

const dataSource = ref('')
const nfsError = ref('')
const providers = ref<ProviderEntry[]>([])
const personalKeys = ref<PersonalKey[]>([])

const newKeyProvider = ref('')
const newKeyValue = ref('')
const newKeyBaseUrl = ref('')
const addingKey = ref(false)

function keySourceLabel(entry: ProviderEntry): string {
  if (entry.key_source === 'org') return entry.key_label ? `组织 Key (${entry.key_label})` : '组织 Key'
  if (entry.key_source === 'personal') return '个人 Key'
  return '未知来源'
}

async function fetchOpenClawProviders() {
  loading.value = true
  error.value = ''
  nfsError.value = ''
  try {
    const [provRes, personalRes] = await Promise.all([
      api.get(`/instances/${instanceId.value}/openclaw-providers`),
      api.get('/users/me/llm-keys'),
    ])

    personalKeys.value = personalRes.data.data ?? []

    const data = provRes.data.data
    dataSource.value = data.data_source ?? ''
    providers.value = data.providers ?? []
  } catch (e: any) {
    const status = e?.response?.status
    const msg = e?.response?.data?.message || ''
    if (status === 503 && (msg.includes('NFS') || msg.includes('nfs') || msg.includes('mount') || msg.includes('挂载'))) {
      nfsError.value = msg
    } else {
      error.value = msg || '加载配置失败'
    }
  } finally {
    loading.value = false
  }
}

async function restartOpenClaw() {
  if (!confirm('OpenClaw 会在完成当前任务后重启，确认重启？')) return
  restarting.value = true
  error.value = ''
  successMsg.value = ''
  try {
    const res = await api.post(`/instances/${instanceId.value}/restart-openclaw`)
    const result = res.data.data
    if (result?.status === 'ok') {
      successMsg.value = 'OpenClaw 已重启完成'
      await fetchOpenClawProviders()
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

onMounted(fetchOpenClawProviders)
</script>

<template>
  <div>
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

      <!-- 大模型配置（从 NFS 存储读取） -->
      <div class="space-y-4">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <Brain class="w-4 h-4 text-violet-400" />
            <h2 class="text-sm font-medium">大模型 Provider 配置</h2>
          </div>
          <button
            v-if="!nfsError"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-border text-xs hover:bg-card transition-colors"
            :disabled="restarting"
            @click="fetchOpenClawProviders"
          >
            <RefreshCw class="w-3 h-3" :class="{ 'animate-spin': restarting }" />
            刷新
          </button>
        </div>

        <p v-if="dataSource === 'nfs' && !nfsError" class="text-xs text-muted-foreground">
          读取自 NFS 存储
        </p>

        <!-- NFS 不可用 -->
        <div v-if="nfsError" class="flex flex-col items-center gap-3 py-10 text-center">
          <HardDrive class="w-8 h-8 text-destructive/60" />
          <p class="text-sm text-destructive">NFS 存储不可用</p>
          <p class="text-xs text-muted-foreground max-w-sm">{{ nfsError }}</p>
        </div>

        <!-- 无 Provider -->
        <div v-else-if="providers.length === 0" class="flex flex-col items-center gap-3 py-10 text-center">
          <AlertTriangle class="w-8 h-8 text-muted-foreground" />
          <p class="text-sm text-muted-foreground">当前实例未配置任何大模型 Provider</p>
        </div>

        <!-- Provider 列表 -->
        <div v-else class="space-y-3">
          <div
            v-for="entry in providers"
            :key="entry.provider"
            class="rounded-lg border border-border bg-card p-4 space-y-2"
          >
            <div class="flex items-center justify-between">
              <div class="font-medium text-sm">{{ PROVIDER_LABELS[entry.provider] || entry.provider }}</div>
              <span
                class="flex items-center gap-1 text-xs"
                :class="entry.is_proxy ? 'text-green-400' : 'text-amber-400'"
              >
                <Circle class="w-2 h-2 fill-current" />
                {{ entry.is_proxy ? '经由 ClawBuddy 代理' : '直连' }}
              </span>
            </div>

            <div class="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <div>
                <span class="text-muted-foreground">Key 来源</span>
                <span class="ml-2">{{ keySourceLabel(entry) }}</span>
              </div>
              <div v-if="entry.api_key_masked">
                <span class="text-muted-foreground">Key</span>
                <span class="ml-2 font-mono">{{ entry.api_key_masked }}</span>
              </div>
              <div class="col-span-2">
                <span class="text-muted-foreground">Base URL</span>
                <span class="ml-2 font-mono break-all">{{ entry.base_url }}</span>
              </div>
            </div>
          </div>
        </div>
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
            <input
              v-model="newKeyProvider"
              type="text"
              placeholder="Provider (如 openai)"
              class="px-3 py-1.5 rounded-md bg-background border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
            />
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
