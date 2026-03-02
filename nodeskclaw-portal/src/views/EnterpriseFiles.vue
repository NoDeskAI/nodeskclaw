<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { FolderOpen, Loader2, Server, RefreshCw } from 'lucide-vue-next'
import api from '@/services/api'
import { resolveApiErrorMessage } from '@/i18n/error'

interface AgentInfo {
  instance_id: string
  name: string
  slug: string
  agent_label: string | null
  agent_theme_color: string | null
  status: string
  is_browsable: boolean
}

const router = useRouter()
const { t } = useI18n()
const loading = ref(true)
const agents = ref<AgentInfo[]>([])
const error = ref('')

const statusConfig: Record<string, { color: string; bg: string }> = {
  running: { color: 'text-emerald-400', bg: 'bg-emerald-400' },
  learning: { color: 'text-blue-400', bg: 'bg-blue-400' },
  creating: { color: 'text-blue-400', bg: 'bg-blue-400' },
  pending: { color: 'text-yellow-400', bg: 'bg-yellow-400' },
  deploying: { color: 'text-blue-400', bg: 'bg-blue-400' },
  updating: { color: 'text-amber-400', bg: 'bg-amber-400' },
  failed: { color: 'text-red-400', bg: 'bg-red-400' },
  deleting: { color: 'text-gray-400', bg: 'bg-gray-400' },
}

function getStatus(status: string) {
  return statusConfig[status] ?? { color: 'text-gray-400', bg: 'bg-gray-400' }
}

function getStatusLabel(status: string) {
  const key = `status.${status}`
  const translated = t(key)
  return translated === key ? status : translated
}

const browsableCount = computed(() => agents.value.filter(a => a.is_browsable).length)

async function fetchAgents() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/enterprise-files/agents')
    agents.value = data.data ?? []
  } catch (e: unknown) {
    error.value = resolveApiErrorMessage(e)
  } finally {
    loading.value = false
  }
}

function enterAgent(agent: AgentInfo) {
  if (!agent.is_browsable) return
  router.push(`/enterprise-files/${agent.instance_id}`)
}

onMounted(fetchAgents)
</script>

<template>
  <div class="max-w-5xl mx-auto px-6 py-8">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold">{{ t('enterpriseFiles.title') }}</h1>
        <p class="text-sm text-muted-foreground mt-1">
          {{ t('enterpriseFiles.subtitle') }}
          <span v-if="!loading && agents.length" class="ml-2 text-xs">
            {{ browsableCount }}/{{ agents.length }} {{ t('enterpriseFiles.browsable') }}
          </span>
        </p>
      </div>
      <button
        class="flex items-center gap-2 px-3 py-2 rounded-lg border border-border text-sm text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
        @click="fetchAgents"
      >
        <RefreshCw class="w-4 h-4" />
      </button>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <div v-else-if="error" class="text-center py-20 space-y-4">
      <div class="w-16 h-16 rounded-2xl bg-red-500/10 flex items-center justify-center mx-auto">
        <Server class="w-8 h-8 text-red-400" />
      </div>
      <p class="text-sm text-red-400">{{ error }}</p>
      <button
        class="mt-2 px-4 py-2 rounded-lg border border-border text-sm hover:bg-accent transition-colors"
        @click="fetchAgents"
      >
        {{ t('instanceList.retry') }}
      </button>
    </div>

    <div v-else-if="agents.length === 0" class="text-center py-20 space-y-4">
      <div class="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto">
        <FolderOpen class="w-8 h-8 text-primary" />
      </div>
      <h3 class="text-lg font-semibold">{{ t('enterpriseFiles.noAgents') }}</h3>
    </div>

    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <div
        v-for="agent in agents"
        :key="agent.instance_id"
        class="rounded-xl border border-border p-4 transition-colors"
        :class="agent.is_browsable
          ? 'hover:border-primary cursor-pointer'
          : 'opacity-50'"
        @click="enterAgent(agent)"
      >
        <div class="flex items-start gap-3">
          <div
            class="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
            :style="agent.agent_theme_color
              ? { backgroundColor: agent.agent_theme_color + '20', color: agent.agent_theme_color }
              : {}"
            :class="!agent.agent_theme_color ? 'bg-primary/10 text-primary' : ''"
          >
            <Server class="w-5 h-5" />
          </div>
          <div class="min-w-0 flex-1">
            <h3 class="font-medium truncate">{{ agent.name }}</h3>
            <span
              v-if="agent.agent_label"
              class="inline-block mt-1 px-2 py-0.5 rounded text-xs bg-muted text-muted-foreground"
            >
              {{ agent.agent_label }}
            </span>
          </div>
        </div>
        <div class="flex items-center justify-between mt-3">
          <span class="inline-flex items-center gap-1.5 text-xs">
            <span
              class="w-2 h-2 rounded-full"
              :class="getStatus(agent.status).bg"
            />
            <span :class="getStatus(agent.status).color">
              {{ getStatusLabel(agent.status) }}
            </span>
          </span>
          <span v-if="!agent.is_browsable" class="text-xs text-muted-foreground">
            {{ t('enterpriseFiles.notRunning') }}
          </span>
          <span v-else class="text-xs text-primary">
            {{ t('enterpriseFiles.enterBrowse') }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
