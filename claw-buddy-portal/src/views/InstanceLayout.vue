<script setup lang="ts">
import { ref, onMounted, computed, provide } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, Circle, Loader2, LayoutDashboard, Settings, Dna, History } from 'lucide-vue-next'
import api from '@/services/api'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const instanceId = computed(() => route.params.id as string)

interface InstanceBasic {
  id: string
  name: string
  status: string
  org_id: string | null
}

const instance = ref<InstanceBasic | null>(null)
const loading = ref(true)

const statusColors: Record<string, string> = {
  running: 'text-green-400',
  learning: 'text-blue-400',
  deploying: 'text-yellow-400',
  restarting: 'text-amber-400',
  failed: 'text-red-400',
}

function getStatusLabel(status: string): string {
  const key = `status.${status}`
  return t(key) === key ? status : t(key)
}

async function fetchBasic() {
  loading.value = true
  try {
    const res = await api.get(`/instances/${instanceId.value}`)
    instance.value = res.data.data
  } catch {
    instance.value = null
  } finally {
    loading.value = false
  }
}

const instanceOrgId = computed(() => instance.value?.org_id ?? null)

provide('instanceId', instanceId)
provide('instanceOrgId', instanceOrgId)
provide('instanceBasic', instance)
provide('refreshInstanceBasic', fetchBasic)

onMounted(fetchBasic)

const navItems = computed(() => [
  { name: 'InstanceDetail', label: t('common.overview'), icon: LayoutDashboard },
  { name: 'InstanceGenes', label: t('common.genes'), icon: Dna },
  { name: 'EvolutionLog', label: t('common.evolutionLog'), icon: History },
  { name: 'InstanceSettings', label: t('common.settings'), icon: Settings },
])
</script>

<template>
  <div class="flex flex-col h-[calc(100vh-3.5rem)] max-w-4xl mx-auto px-6">
    <!-- Header (固定) -->
    <div class="shrink-0 flex items-center gap-3 pt-8 pb-4">
      <button class="text-muted-foreground hover:text-foreground transition-colors" @click="router.push('/instances')">
        <ArrowLeft class="w-5 h-5" />
      </button>
      <template v-if="loading">
        <Loader2 class="w-4 h-4 animate-spin text-muted-foreground" />
      </template>
      <template v-else-if="instance">
        <h1 class="text-xl font-bold">{{ instance.name }}</h1>
        <span class="flex items-center gap-1 text-xs" :class="statusColors[instance.status] || 'text-zinc-400'">
          <Circle class="w-2 h-2 fill-current" />
          {{ getStatusLabel(instance.status) }}
        </span>
      </template>
    </div>

    <!-- Body: sidebar + content -->
    <div class="flex gap-6 flex-1 min-h-0 pb-8">
      <!-- Left nav (固定) -->
      <nav class="w-40 shrink-0 space-y-1">
        <router-link
          v-for="item in navItems"
          :key="item.name"
          :to="{ name: item.name, params: { id: instanceId } }"
          class="flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors"
          :class="route.name === item.name
            ? 'bg-primary/10 text-primary font-medium'
            : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'"
        >
          <component :is="item.icon" class="w-4 h-4" />
          {{ item.label }}
        </router-link>
      </nav>

      <!-- Content (可滚动) -->
      <div class="flex-1 min-w-0 overflow-y-auto pr-3">
        <div class="pb-4">
          <router-view />
        </div>
      </div>
    </div>
  </div>
</template>

