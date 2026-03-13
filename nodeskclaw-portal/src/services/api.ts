import axios from 'axios'
import { getCurrentLocale } from '@/i18n'
import { useToast } from '@/composables/useToast'
import { i18n } from '@/i18n'

let lastBackendWarningAt = 0
const BACKEND_WARNING_COOLDOWN = 15_000
let isRefreshing = false
let pendingRequests: Array<(token: string) => void> = []

export function getToken(): string | null {
  return localStorage.getItem('portal_token')
}

export function getRefreshToken(): string | null {
  return localStorage.getItem('portal_refresh_token')
}

export function setTokens(access: string, refresh: string) {
  localStorage.setItem('portal_token', access)
  localStorage.setItem('portal_refresh_token', refresh)
}

export function clearTokens() {
  localStorage.removeItem('portal_token')
  localStorage.removeItem('portal_refresh_token')
}

function notifyBackendUnavailable(status?: number) {
  const now = Date.now()
  if (now - lastBackendWarningAt < BACKEND_WARNING_COOLDOWN) return
  lastBackendWarningAt = now

  const { t } = i18n.global
  const toast = useToast()
  const key =
    status && status >= 502 && status <= 504
      ? 'errors.system.backend_starting'
      : 'errors.system.backend_unreachable'
  toast.warning(t(key), { duration: 6000 })
}

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  config.headers['Accept-Language'] = getCurrentLocale()
  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error.response?.status
    const originalRequest = error.config

    if (!error.response || error.code === 'ERR_NETWORK' || error.code === 'ECONNABORTED') {
      notifyBackendUnavailable()
    } else if (status >= 502 && status <= 504) {
      notifyBackendUnavailable(status)
    }

    if (status === 401 && !originalRequest._retry) {
      const url = originalRequest?.url || ''
      if (url.includes('/auth/')) {
        return Promise.reject(error)
      }

      const refreshTokenValue = getRefreshToken()
      if (refreshTokenValue) {
        if (isRefreshing) {
          return new Promise((resolve) => {
            pendingRequests.push((newToken: string) => {
              originalRequest.headers.Authorization = `Bearer ${newToken}`
              resolve(api(originalRequest))
            })
          })
        }

        originalRequest._retry = true
        isRefreshing = true

        try {
          const res = await axios.post('/api/v1/auth/refresh', {
            refresh_token: refreshTokenValue,
          })
          const data = res.data?.data
          if (data?.access_token) {
            setTokens(data.access_token, data.refresh_token || refreshTokenValue)
            originalRequest.headers.Authorization = `Bearer ${data.access_token}`
            pendingRequests.forEach((cb) => cb(data.access_token))
            pendingRequests = []
            return api(originalRequest)
          }
        } catch {
          // refresh failed, fall through to logout
        } finally {
          isRefreshing = false
        }
      }

      clearTokens()
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }

    if (status === 403) {
      const detail = error.response?.data?.detail
      if (detail?.error_code === 40350 && window.location.pathname !== '/force-change-password') {
        window.location.href = '/force-change-password'
      }
    }

    return Promise.reject(error)
  },
)

export default api
