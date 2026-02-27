import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'

export interface PortalUser {
  id: string
  name: string
  email: string | null
  phone: string | null
  avatar_url: string | null
  is_super_admin: boolean
  current_org_id: string | null
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('portal_token'))
  const refreshToken = ref<string | null>(localStorage.getItem('portal_refresh_token'))
  const user = ref<PortalUser | null>(null)

  const isLoggedIn = computed(() => !!token.value)

  function setTokens(access: string, refresh: string) {
    token.value = access
    refreshToken.value = refresh
    localStorage.setItem('portal_token', access)
    localStorage.setItem('portal_refresh_token', refresh)
  }

  function clearAuth() {
    token.value = null
    refreshToken.value = null
    user.value = null
    localStorage.removeItem('portal_token')
    localStorage.removeItem('portal_refresh_token')
  }

  async function feishuLogin(code: string) {
    const redirect_uri = window.location.origin + '/login'
    const res = await api.post('/auth/feishu/callback', { code, redirect_uri })
    const data = res.data.data
    setTokens(data.access_token, data.refresh_token)
    user.value = data.user
    return data
  }

  async function fetchUser() {
    try {
      const res = await api.get('/auth/me')
      user.value = res.data.data
    } catch {
      clearAuth()
    }
  }

  async function logout() {
    try {
      await api.post('/auth/logout')
    } finally {
      clearAuth()
    }
  }

  async function emailRegister(email: string, password: string, name: string) {
    const res = await api.post('/auth/register', { email, password, name })
    const data = res.data.data
    setTokens(data.access_token, data.refresh_token)
    user.value = data.user
    return data
  }

  async function emailLogin(email: string, password: string) {
    const res = await api.post('/auth/login', { email, password })
    const data = res.data.data
    setTokens(data.access_token, data.refresh_token)
    user.value = data.user
    return data
  }

  async function sendSmsCode(phone: string) {
    const res = await api.post('/auth/sms/send', { phone })
    return res.data
  }

  async function smsLogin(phone: string, code: string) {
    const res = await api.post('/auth/sms/login', { phone, code })
    const data = res.data.data
    setTokens(data.access_token, data.refresh_token)
    user.value = data.user
    return data
  }

  return {
    token, refreshToken, user, isLoggedIn,
    setTokens, clearAuth,
    feishuLogin, emailRegister, emailLogin, sendSmsCode, smsLogin,
    fetchUser, logout,
  }
})
