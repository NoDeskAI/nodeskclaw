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
let retryCount = 0

const SSE_BASE_RETRY_MS = 1000
const SSE_MAX_RETRY_MS = 30000
const SSE_MAX_RETRY_COUNT = 8

function startGlobalSSE(clusterId: string) {
  stopGlobalSSE()

  if (!clusterId) {
    sseConnected.value = false
    return
  }

  abortController = new AbortController()
  retryCount = 0
  const token = localStorage.getItem('token')

  fetchEventSource(`${API_BASE}/events/stream?cluster_id=${clusterId}`, {
    headers: { Authorization: `Bearer ${token}` },
    signal: abortController.signal,
    onopen: async () => {
      retryCount = 0
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
      retryCount += 1
      if (retryCount > SSE_MAX_RETRY_COUNT) {
        throw new Error('global_sse_retry_exhausted')
      }
      return Math.min(SSE_BASE_RETRY_MS * (2 ** (retryCount - 1)), SSE_MAX_RETRY_MS)
    },
    onclose: () => {
      sseConnected.value = false
      clusterConnected.value = false
    },
  })
}

function stopGlobalSSE() {
  abortController?.abort()
  abortController = null
  retryCount = 0
  sseConnected.value = false
  clusterConnected.value = null
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
