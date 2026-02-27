import axios from 'axios'
import { getCurrentLocale } from '@/i18n'

export const API_BASE = '/api/v1'

const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

const AUTH_REDIRECT_COOLDOWN_MS = 2000
let lastAuthRedirectAt = 0

function redirectToLoginOnce() {
  if (typeof window === 'undefined') return
  const now = Date.now()
  if (now - lastAuthRedirectAt < AUTH_REDIRECT_COOLDOWN_MS) return
  lastAuthRedirectAt = now
  if (window.location.pathname !== '/login') {
    window.location.href = '/login'
  }
}

// 请求拦截：附加 JWT Token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  config.headers['Accept-Language'] = getCurrentLocale()
  return config
})

// 响应拦截：统一错误处理
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const requestUrl = String(error.config?.url ?? '')
      const isAuthEndpoint = requestUrl.includes('/auth/')
      localStorage.removeItem('token')
      localStorage.removeItem('refresh_token')
      if (!isAuthEndpoint) {
        redirectToLoginOnce()
      }
    }
    return Promise.reject(error)
  },
)

export default api
