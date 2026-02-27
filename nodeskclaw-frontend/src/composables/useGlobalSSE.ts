/**
 * 全局 SSE 连接管理：订阅集群事件、健康状态等，供 Dashboard ActivityFeed 和底栏使用。
 *
 * 重连策略：指数退避 + 无限重试，确保 SSE 在后端重启、网络抖动后自动恢复。
 * 每次重连时重新读取 localStorage token，避免 token 刷新后 SSE 仍用旧凭证。
 */
import { ref, computed } from 'vue'
import { fetchEventSource, EventStreamContentType } from '@microsoft/fetch-event-source'
import { API_BASE } from '@/services/api'
import type { FeedEvent } from '@/types/activity'

const feedEvents = ref<FeedEvent[]>([])
const sseConnected = ref(false)
const sseConnecting = ref(false)
const clusterConnected = ref<boolean | null>(null)
let abortController: AbortController | null = null
let eventCounter = 0
let retryCount = 0
let currentClusterId: string | null = null

const SSE_BASE_RETRY_MS = 2000
const SSE_MAX_RETRY_MS = 60000

class FatalSSEError extends Error {}

function startGlobalSSE(clusterId: string) {
  if (currentClusterId === clusterId && (sseConnected.value || sseConnecting.value)) {
    return
  }

  stopGlobalSSE()

  if (!clusterId) {
    return
  }

  currentClusterId = clusterId
  abortController = new AbortController()
  retryCount = 0
  sseConnecting.value = true

  fetchEventSource(`${API_BASE}/events/stream?cluster_id=${clusterId}`, {
    signal: abortController.signal,
    openWhenHidden: true,
    headers: {
      get Authorization() {
        const token = localStorage.getItem('token')
        return token ? `Bearer ${token}` : ''
      },
    } as Record<string, string>,

    async onopen(response) {
      if (response.ok && response.headers.get('content-type')?.startsWith(EventStreamContentType)) {
        retryCount = 0
        sseConnected.value = true
        sseConnecting.value = false
        clusterConnected.value = true
        return
      }
      if (response.status === 401 || response.status === 403) {
        throw new FatalSSEError(`SSE auth failed: ${response.status}`)
      }
      throw new Error(`SSE open failed: ${response.status}`)
    },

    onmessage(ev) {
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
          // ignore malformed event
        }
      }
    },

    onerror(err) {
      sseConnected.value = false
      clusterConnected.value = false
      sseConnecting.value = true

      if (err instanceof FatalSSEError) {
        sseConnecting.value = false
        throw err
      }

      retryCount += 1
      return Math.min(SSE_BASE_RETRY_MS * (2 ** (retryCount - 1)), SSE_MAX_RETRY_MS)
    },

    onclose() {
      sseConnected.value = false
      clusterConnected.value = false
      sseConnecting.value = true
    },
  })
}

function stopGlobalSSE() {
  abortController?.abort()
  abortController = null
  currentClusterId = null
  retryCount = 0
  sseConnected.value = false
  sseConnecting.value = false
  clusterConnected.value = null
}

export function useGlobalSSE() {
  return {
    feedEvents: computed(() => feedEvents.value),
    sseConnected: computed(() => sseConnected.value),
    sseConnecting: computed(() => sseConnecting.value),
    clusterConnected: computed(() => clusterConnected.value),
    startGlobalSSE,
    stopGlobalSSE,
  }
}
