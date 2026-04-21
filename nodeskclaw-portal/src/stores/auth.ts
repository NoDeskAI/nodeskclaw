import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'

export interface OAuthConnectionInfo {
  provider: string
  provider_user_id: string
}

export interface PortalUser {
  id: string
  name: string
  email: string | null
  phone: string | null
  username: string | null
  avatar_url: string | null
  is_super_admin: boolean
  has_password: boolean
  must_change_password: boolean
  current_org_id: string | null
  portal_org_role: string | null
  oauth_connections: OAuthConnectionInfo[]
}

export interface FeatureInfo {
  id: string
  name: string
  description?: string
  enabled: boolean
}

export interface SystemInfo {
  edition: 'ce' | 'ee'
  version: string
  features: FeatureInfo[]
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('portal_token'))
  const refreshToken = ref<string | null>(localStorage.getItem('portal_refresh_token'))
  const user = ref<PortalUser | null>(null)
  const systemInfo = ref<SystemInfo | null>(null)

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

  async function fetchSystemInfo() {
    try {
      const res = await api.get('/system/info')
      systemInfo.value = res.data
    } catch {
      systemInfo.value = { edition: 'ce', version: '0.0.0', features: [] }
    }
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

  async function accountLogin(account: string, password: string) {
    const res = await api.post('/auth/account-login', { account, password })
    const data = res.data.data
    setTokens(data.access_token, data.refresh_token)
    user.value = data.user
    return data
  }

  async function sendVerificationCode(account: string) {
    const res = await api.post('/auth/verification-code/send', { account })
    return res.data
  }

  async function verificationCodeLogin(account: string, code: string) {
    const res = await api.post('/auth/verification-code/login', { account, code })
    const data = res.data.data
    setTokens(data.access_token, data.refresh_token)
    user.value = data.user
    return data
  }

  return {
    token, refreshToken, user, systemInfo, isLoggedIn,
    setTokens, clearAuth,
    emailLogin, sendSmsCode, smsLogin,
    accountLogin, sendVerificationCode, verificationCodeLogin,
    fetchSystemInfo, fetchUser, logout,
  }
})
