import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'

export interface OAuthConnectionInfo {
  provider: string
  provider_user_id: string
}

export interface UserInfo {
  id: string
  name: string
  email: string | null
  phone: string | null
  avatar_url: string | null
  role: string
  is_super_admin: boolean
  current_org_id: string | null
  last_login_at: string | null
  oauth_connections: OAuthConnectionInfo[]
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('token'))
  const refreshToken = ref<string | null>(localStorage.getItem('refresh_token'))
  const user = ref<UserInfo | null>(null)

  const isLoggedIn = computed(() => !!token.value)

  function setTokens(access: string, refresh: string) {
    token.value = access
    refreshToken.value = refresh
    localStorage.setItem('token', access)
    localStorage.setItem('refresh_token', refresh)
  }

  function clearAuth() {
    token.value = null
    refreshToken.value = null
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('refresh_token')
  }

  async function oauthLogin(provider: string, code: string) {
    const redirect_uri = window.location.origin + `/login/callback/${provider}`
    const res = await api.post('/auth/oauth/callback', { provider, code, redirect_uri })
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

  return {
    token,
    refreshToken,
    user,
    isLoggedIn,
    setTokens,
    clearAuth,
    oauthLogin,
    fetchUser,
    logout,
  }
})
