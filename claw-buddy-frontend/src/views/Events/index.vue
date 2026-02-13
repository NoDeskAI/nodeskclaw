<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
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
const events = ref<EventItem[]>([])
const connected = ref(false)
let abortController: AbortController | null = null
let eventCounter = 0

// Filters
const filterType = ref('ALL')
const filterInstance = ref('ALL')

const currentClusterId = computed(() => clusterStore.currentClusterId)

// Load instances for filter
onMounted(async () => {
  await instanceStore.fetchInstances()
  connectSSE()
})

watch(currentClusterId, () => {
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
  const token = localStorage.getItem('token')

  fetchEventSource(`${API_BASE}/events/stream?cluster_id=${currentClusterId.value}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
    signal: abortController.signal,
    onopen: async () => {
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
    },
    onclose: () => {
      connected.value = false
    },
  })
}

onUnmounted(() => {
  abortController?.abort()
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
  return d.toLocaleTimeString('zh-CN', { hour12: false })
}
</script>

<template>
  <div class="p-6 space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-bold">事件中心</h1>
      <div class="flex items-center gap-2">
        <Badge :variant="connected ? 'default' : 'destructive'" class="flex items-center gap-1">
          <Wifi v-if="connected" class="w-3 h-3" />
          <WifiOff v-else class="w-3 h-3" />
          {{ connected ? '已连接' : '断开' }}
        </Badge>
        <Button variant="outline" size="sm" @click="connectSSE">
          <RefreshCw class="w-3 h-3 mr-1" />
          重连
        </Button>
      </div>
    </div>

    <!-- Filters -->
    <div class="flex items-center gap-3 flex-wrap">
      <div class="flex items-center gap-2">
        <span class="text-xs text-muted-foreground">实例:</span>
        <Select v-model="filterInstance">
          <SelectTrigger class="w-[180px] h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">全部</SelectItem>
            <SelectItem v-for="inst in instanceStore.instances" :key="inst.id" :value="inst.name">
              {{ inst.name }}
            </SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xs text-muted-foreground">类型:</span>
        <Select v-model="filterType">
          <SelectTrigger class="w-[120px] h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">全部</SelectItem>
            <SelectItem value="Normal">Normal</SelectItem>
            <SelectItem value="Warning">Warning</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <Badge variant="secondary" class="text-xs">
        {{ filteredEvents.length }} 条事件
      </Badge>
    </div>

    <Card>
      <CardHeader>
        <CardTitle>实时事件流</CardTitle>
      </CardHeader>
      <CardContent>
        <div v-if="!currentClusterId" class="text-center py-12">
          <Info class="w-8 h-8 text-muted-foreground mx-auto mb-3" />
          <p class="text-sm text-muted-foreground">请先选择一个集群</p>
        </div>
        <div v-else-if="filteredEvents.length === 0" class="text-center py-12">
          <Info class="w-8 h-8 text-muted-foreground mx-auto mb-3" />
          <p class="text-sm text-muted-foreground">
            等待事件... 部署或操作实例后将自动接收事件通知
          </p>
        </div>
        <div v-else class="space-y-2">
          <div
            v-for="event in filteredEvents"
            :key="event.id"
            class="flex items-start gap-3 rounded-md px-4 py-3 animate-fade-in-up"
            :class="event.event_type === 'Warning'
              ? 'bg-yellow-500/5 border-l-2 border-l-[#fbbf24]'
              : 'bg-muted/30 border-l-2 border-l-white/[0.08]'"
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
                  {{ event.involved_kind ? `${event.involved_kind}/` : '' }}{{ event.involved || 'system' }}
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
