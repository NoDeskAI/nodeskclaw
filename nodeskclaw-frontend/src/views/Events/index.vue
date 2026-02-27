<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { AlertTriangle, Info, RefreshCw, Wifi, WifiOff } from 'lucide-vue-next'
import { fetchEventSource } from '@microsoft/fetch-event-source'
import { API_BASE } from '@/services/api'
import { useClusterStore } from '@/stores/cluster'
import { useInstanceStore } from '@/stores/instance'
import { resolveApiErrorMessage } from '@/i18n/error'

interface EventItem {
  id: string
  type: string
  event_type: string
  reason: string
  message: string
  involved: string | null
  involved_kind: string | null
  namespace: string | null
  count: number | null
  last_timestamp: string | null
  first_timestamp: string | null
}

const clusterStore = useClusterStore()
const instanceStore = useInstanceStore()
const { t, locale } = useI18n()
const events = ref<EventItem[]>([])
const connected = ref(false)
const loading = ref(true)
const loadError = ref('')
let abortController: AbortController | null = null
let eventCounter = 0
let sseRetryCount = 0

const SSE_BASE_RETRY_MS = 1000
const SSE_MAX_RETRY_MS = 30000
const SSE_MAX_RETRY_COUNT = 8

// Filters
const filterType = ref('ALL')
const filterInstance = ref('ALL')

const currentClusterId = computed(() => clusterStore.currentClusterId)

async function initializeEventsPage() {
  loading.value = true
  loadError.value = ''
  try {
    await instanceStore.fetchInstances()
    connectSSE()
  } catch (error) {
    connected.value = false
    loadError.value = resolveApiErrorMessage(error, t('eventsPage.loadFailed'))
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void initializeEventsPage()
})

watch(currentClusterId, () => {
  if (loading.value || loadError.value) return
  connectSSE()
})

function connectSSE() {
  if (abortController) {
    abortController.abort()
  }

  if (!currentClusterId.value) {
    connected.value = false
    return
  }

  abortController = new AbortController()
  sseRetryCount = 0
  const token = localStorage.getItem('token')

  fetchEventSource(`${API_BASE}/events/stream?cluster_id=${currentClusterId.value}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
    signal: abortController.signal,
    onopen: async () => {
      sseRetryCount = 0
      connected.value = true
    },
    onmessage: (ev) => {
      if (ev.event === 'k8s_event') {
        try {
          const data = JSON.parse(ev.data)
          eventCounter++
          const item: EventItem = {
            id: `evt-${eventCounter}`,
            type: data.type,
            event_type: data.event_type || 'Normal',
            reason: data.reason || '',
            message: data.message || '',
            involved: data.involved,
            involved_kind: data.involved_kind,
            namespace: data.namespace,
            count: data.count,
            last_timestamp: data.last_timestamp,
            first_timestamp: data.first_timestamp,
          }
          events.value.unshift(item)
          if (events.value.length > 500) {
            events.value = events.value.slice(0, 500)
          }
        } catch {
          // ignore parse error
        }
      }
    },
    onerror: () => {
      connected.value = false
      sseRetryCount += 1
      if (sseRetryCount > SSE_MAX_RETRY_COUNT) {
        throw new Error('events_sse_retry_exhausted')
      }
      return Math.min(SSE_BASE_RETRY_MS * (2 ** (sseRetryCount - 1)), SSE_MAX_RETRY_MS)
    },
    onclose: () => {
      connected.value = false
    },
  })
}

onUnmounted(() => {
  abortController?.abort()
  sseRetryCount = 0
})

const filteredEvents = computed(() => {
  let result = events.value

  if (filterType.value !== 'ALL') {
    result = result.filter((e) => e.event_type === filterType.value)
  }

  if (filterInstance.value !== 'ALL') {
    result = result.filter(
      (e) => e.involved?.includes(filterInstance.value) || e.namespace?.includes(filterInstance.value)
    )
  }

  return result
})

function formatTime(ts: string | null): string {
  if (!ts) return '-'
  const d = new Date(ts)
  return d.toLocaleTimeString(locale.value === 'zh-CN' ? 'zh-CN' : 'en-US', { hour12: false })
}
</script>

<template>
  <div class="p-6 space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-bold">{{ t('eventsPage.title') }}</h1>
      <div class="flex items-center gap-2">
        <Badge :variant="connected ? 'default' : 'destructive'" class="flex items-center gap-1">
          <Wifi v-if="connected" class="w-3 h-3" />
          <WifiOff v-else class="w-3 h-3" />
          {{ connected ? t('eventsPage.connected') : t('eventsPage.disconnected') }}
        </Badge>
        <Button variant="outline" size="sm" @click="connectSSE">
          <RefreshCw class="w-3 h-3 mr-1" />
          {{ t('eventsPage.reconnect') }}
        </Button>
      </div>
    </div>

    <div v-if="loading" class="text-muted-foreground text-center py-12">{{ t('eventsPage.loading') }}</div>
    <div v-else-if="loadError" class="py-12 flex flex-col items-center gap-4">
      <p class="text-sm text-destructive text-center">{{ loadError }}</p>
      <Button variant="outline" @click="initializeEventsPage">
        {{ t('eventsPage.retry') }}
      </Button>
    </div>

    <template v-else>
      <!-- Filters -->
      <div class="flex items-center gap-3 flex-wrap">
        <div class="flex items-center gap-2">
          <span class="text-xs text-muted-foreground">{{ t('eventsPage.instanceLabel') }}</span>
          <Select v-model="filterInstance">
            <SelectTrigger class="w-[180px] h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">{{ t('eventsPage.all') }}</SelectItem>
              <SelectItem v-for="inst in instanceStore.instances" :key="inst.id" :value="inst.name">
                {{ inst.name }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-xs text-muted-foreground">{{ t('eventsPage.typeLabel') }}</span>
          <Select v-model="filterType">
            <SelectTrigger class="w-[120px] h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">{{ t('eventsPage.all') }}</SelectItem>
              <SelectItem value="Normal">{{ t('eventsPage.typeNormal') }}</SelectItem>
              <SelectItem value="Warning">{{ t('eventsPage.typeWarning') }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Badge variant="secondary" class="text-xs">
          {{ t('eventsPage.eventCount', { count: filteredEvents.length }) }}
        </Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{{ t('eventsPage.realtimeStream') }}</CardTitle>
        </CardHeader>
        <CardContent>
          <div v-if="!currentClusterId" class="text-center py-12">
            <Info class="w-8 h-8 text-muted-foreground mx-auto mb-3" />
            <p class="text-sm text-muted-foreground">{{ t('eventsPage.selectClusterFirst') }}</p>
          </div>
          <div v-else-if="filteredEvents.length === 0" class="text-center py-12">
            <Info class="w-8 h-8 text-muted-foreground mx-auto mb-3" />
            <p class="text-sm text-muted-foreground">
              {{ t('eventsPage.waitingEvents') }}
            </p>
          </div>
          <div v-else class="space-y-2">
            <div
              v-for="event in filteredEvents"
              :key="event.id"
              class="flex items-start gap-3 rounded-md px-4 py-3 animate-fade-in-up"
              :class="event.event_type === 'Warning'
                ? 'bg-yellow-500/5 border-l-2 border-l-[#fbbf24]'
                : 'bg-muted/30 border-l-2 border-l-white/8'"
            >
              <AlertTriangle
                v-if="event.event_type === 'Warning'"
                class="w-4 h-4 text-[#fbbf24] mt-0.5 shrink-0"
              />
              <Info v-else class="w-4 h-4 text-blue-400 mt-0.5 shrink-0" />
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2">
                  <span class="text-sm font-medium">{{ event.reason }}</span>
                  <Badge variant="secondary" class="text-xs">
                    {{ event.involved_kind ? `${event.involved_kind}/` : '' }}{{ event.involved || t('eventsPage.system') }}
                  </Badge>
                  <Badge v-if="event.namespace" variant="outline" class="text-xs">
                    {{ event.namespace }}
                  </Badge>
                  <span v-if="event.count && event.count > 1" class="text-xs text-muted-foreground">
                    x{{ event.count }}
                  </span>
                </div>
                <p class="text-xs text-muted-foreground mt-1 break-all">{{ event.message }}</p>
                <p class="text-xs text-muted-foreground/60 mt-1">
                  {{ formatTime(event.last_timestamp || event.first_timestamp) }}
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </template>
  </div>
</template>

<style scoped>
@keyframes fade-in-up {
  from {
    opacity: 0;
    transform: translateY(-8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.animate-fade-in-up {
  animation: fade-in-up 0.2s ease-out;
}
</style>
