/**
 * 全局 SSE 连接管理：订阅集群事件、健康状态等，供 Dashboard ActivityFeed 和底栏使用。
 */
import { ref, computed } from 'vue'
import { fetchEventSource } from '@microsoft/fetch-event-source'
import { API_BASE } from '@/services/api'
import type { FeedEvent } from '@/types/activity'

const feedEvents = ref<FeedEvent[]>([])
const sseConnected = ref(false)
const clusterConnected = ref<boolean | null>(null)
let abortController: AbortController | null = null
let eventCounter = 0

function startGlobalSSE(clusterId: string) {
  stopGlobalSSE()

  if (!clusterId) {
    sseConnected.value = false
    return
  }

  abortController = new AbortController()
  const token = localStorage.getItem('token')

  fetchEventSource(`${API_BASE}/events/stream?cluster_id=${clusterId}`, {
    headers: { Authorization: `Bearer ${token}` },
    signal: abortController.signal,
    onopen: async () => {
      sseConnected.value = true
      clusterConnected.value = true
    },
    onmessage: (ev) => {
      if (ev.event === 'k8s_event') {
        try {
          const data = JSON.parse(ev.data)
          eventCounter++
          const feedType = data.event_type === 'Warning' ? 'warning' : 'info'
          const item: FeedEvent = {
            id: `feed-${eventCounter}`,
            time: data.last_timestamp
              ? new Date(data.last_timestamp).toLocaleTimeString('zh-CN', { hour12: false })
              : new Date().toLocaleTimeString('zh-CN', { hour12: false }),
            message: `${data.involved || 'system'} ${data.reason}: ${data.message || ''}`.slice(0, 120),
            type: feedType,
          }
          feedEvents.value.unshift(item)
          if (feedEvents.value.length > 50) {
            feedEvents.value = feedEvents.value.slice(0, 50)
          }
        } catch {
          // ignore
        }
      }
    },
    onerror: () => {
      sseConnected.value = false
      clusterConnected.value = false
    },
    onclose: () => {
      sseConnected.value = false
    },
  })
}

function stopGlobalSSE() {
  abortController?.abort()
  abortController = null
  sseConnected.value = false
}

export function useGlobalSSE() {
  return {
    feedEvents: computed(() => feedEvents.value),
    sseConnected: computed(() => sseConnected.value),
    clusterConnected: computed(() => clusterConnected.value),
    startGlobalSSE,
    stopGlobalSSE,
  }
}
