<script setup lang="ts">
import { ref, computed, onMounted, inject, type ComputedRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { Circle, FileText, X, Loader2 } from 'lucide-vue-next'
import api from '@/services/api'
import { useToast } from '@/composables/useToast'
import { Button } from '@/components/ui/button'

const { t } = useI18n()
const toast = useToast()
const instanceId = inject<ComputedRef<string>>('instanceId')!

interface PodItem {
  name: string
  status: string
  ready: boolean
  restart_count: number
}

interface RuntimeData {
  pods: PodItem[]
  compute_provider?: string
  health_status?: string
}

const data = ref<RuntimeData | null>(null)
const loading = ref(true)
const logsVisible = ref(false)
const logsContent = ref('')
const logsLoading = ref(false)

const entityLabel = computed(() => t('instanceRuntime.runtimeInstance'))

async function fetchData() {
  loading.value = true
  try {
    const res = await api.get(`/instances/${instanceId.value}`)
    data.value = res.data.data
  } catch {
    data.value = null
  } finally {
    loading.value = false
  }
}

async function viewLogs(podName: string) {
  if (logsVisible.value) {
    logsVisible.value = false
    return
  }
  logsLoading.value = true
  logsContent.value = ''
  try {
    const res = await api.get(`/instances/${instanceId.value}/pods/${podName}/logs`, { params: { tail: 100 } })
    logsContent.value = res.data?.logs || res.data || ''
    logsVisible.value = true
  } catch {
    toast.error(t('instanceRuntime.logsLoadFailed'))
  } finally {
    logsLoading.value = false
  }
}

onMounted(fetchData)
</script>

<template>
  <div class="space-y-4">
    <h2 class="text-base font-semibold">{{ t('instanceRuntime.title') }}</h2>

    <div v-if="loading" class="flex items-center justify-center py-12">
      <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
    </div>

    <template v-else-if="data">
      <div v-if="data.pods?.length" class="space-y-4">
        <div class="p-4 rounded-xl border border-border bg-card">
          <h3 class="text-sm font-medium mb-3">{{ entityLabel }}</h3>
          <div class="space-y-2">
            <div
              v-for="pod in data.pods"
              :key="pod.name"
              class="flex items-center justify-between text-sm p-2 rounded-md bg-muted/30"
            >
              <div class="flex items-center gap-2">
                <Circle
                  class="w-2 h-2 fill-current"
                  :class="data.health_status === 'unhealthy' ? 'text-orange-400' : (pod.ready ? 'text-green-400' : 'text-yellow-400')"
                />
                <span class="font-mono text-xs">{{ pod.name }}</span>
                <span
                  v-if="pod.restart_count >= 1"
                  class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-orange-500/10 text-orange-400"
                >
                  {{ t('instanceRuntime.restartCount', { count: pod.restart_count }) }}
                </span>
              </div>
              <Button variant="unstyled" size="unstyled"
                class="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                @click="viewLogs(pod.name)"
              >
                <FileText class="w-3 h-3" />
                {{ t('instanceRuntime.runtimeLogs') }}
              </Button>
            </div>
          </div>

          <div v-if="logsVisible" class="mt-3 border border-border rounded-lg overflow-hidden">
            <div class="flex items-center justify-between px-3 py-1.5 bg-muted/50 border-b border-border">
              <span class="text-xs font-medium">{{ t('instanceRuntime.runtimeLogs') }}</span>
              <Button variant="unstyled" size="unstyled" class="text-muted-foreground hover:text-foreground" @click="logsVisible = false">
                <X class="w-3.5 h-3.5" />
              </Button>
            </div>
            <pre class="p-3 text-xs font-mono leading-relaxed overflow-auto max-h-64 bg-black/30 text-foreground">{{ logsContent || '...' }}</pre>
          </div>
        </div>
      </div>

      <div v-else class="p-8 text-center text-muted-foreground text-sm">
        {{ t('instanceRuntime.noPods') }}
      </div>
    </template>
  </div>
</template>
