/**
 * Token 过期告警 composable -- 定时轮询当前集群的 /health 端点，
 * 根据 token_warning 字段返回告警级别。
 */
import { ref, onUnmounted } from 'vue'
import api from '@/services/api'

export type TokenWarningLevel = null | 'warning' | 'expired'

const tokenWarning = ref<TokenWarningLevel>(null)
const tokenExpiresAt = ref<string | null>(null)
let intervalId: ReturnType<typeof setInterval> | null = null

async function checkTokenHealth(clusterId: string) {
  try {
    const res = await api.get(`/clusters/${clusterId}/health`)
    const data = res.data.data
    tokenWarning.value = data.token_warning ?? null
    tokenExpiresAt.value = data.token_expires_at ?? null
  } catch {
    // health endpoint unavailable, skip
  }
}

function startTokenAlert(clusterId: string | null | undefined) {
  stopTokenAlert()
  if (!clusterId) return
  // Immediate check
  checkTokenHealth(clusterId)
  // Poll every 5 minutes
  intervalId = setInterval(() => checkTokenHealth(clusterId), 5 * 60 * 1000)
}

function stopTokenAlert() {
  if (intervalId) {
    clearInterval(intervalId)
    intervalId = null
  }
  tokenWarning.value = null
  tokenExpiresAt.value = null
}

export function useTokenAlert() {
  onUnmounted(() => {
    // Don't stop on unmount -- it's global
  })

  return {
    tokenWarning,
    tokenExpiresAt,
    startTokenAlert,
    stopTokenAlert,
  }
}
